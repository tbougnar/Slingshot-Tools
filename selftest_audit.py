"""Full-code audit: parse every file, walk every call site, wire every module.

Three earlier passes tested behaviour. This one checks the things those cannot
see: names referenced but never defined, names defined but shadowed, calls into
functions that raise, imports that pull the wrong symbol, and workflows whose
steps call scripts that do not exist.
"""
import ast
import builtins
import json
import re
import subprocess
import sys
from testenv import clean_env
from pathlib import Path as _P

HERE = _P(__file__).resolve().parent

R = HERE
problems = []

py_files = sorted(p for p in R.rglob("*.py")
                  if ".git" not in p.parts and "dist" not in p.parts
                  and "paid" not in p.parts and "_internal" not in p.parts)

# Nothing scratch may be committed. A file called _t.py was swept into a
# commit by "git add -A" once, and it stayed in the repository as a dead
# reference after the local copy was deleted: cleanroom_selftest.py copies
# exactly what git tracks, so it would have carried a file that does not exist
# and the audit would have read it as a syntax error on a clean machine.
for _p in sorted(R.glob("_*.py")):
    problems.append((_p.name, "a scratch file must not be committed"))

print(f"scanning {len(py_files)} python files\n")

BUILTINS = set(dir(builtins))

for f in py_files:
    src = f.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src, filename=str(f))
    except SyntaxError as e:
        problems.append((f.name, f"SYNTAX ERROR line {e.lineno}: {e.msg}"))
        continue

    defined, used, imports = set(), set(), {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                used.add(node.id)
            else:
                defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    continue
                nm = (a.asname or a.name).split(".")[0]
                imports[nm] = a.name
                defined.add(nm)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)
        elif isinstance(node, (ast.comprehension,)):
            pass

    # names read but never bound anywhere and not builtins: usually a typo or
    # a deleted definition
    module_level = {n.targets[0].id for n in tree.body
                    if isinstance(n, ast.Assign) and n.targets
                    and isinstance(n.targets[0], ast.Name)}
    missing = {n for n in used
               if n not in defined and n not in BUILTINS
               and n not in module_level and n.isupper() is False
               and n not in ("self", "cls", "__file__", "__name__", "__doc__")}
    # ignore names that could come from a wildcard or a conditional import
    missing -= set(imports)
    if missing:
        problems.append((f.name, f"uses undefined names: {sorted(missing)[:6]}"))

# ---- workflow steps must call scripts that exist ----
wf_dir = R / ".github" / "workflows"
for wf in sorted(wf_dir.glob("*.yml")):
    text = wf.read_text(encoding="utf-8")
    for m in re.finditer(r"run:\s*(?:\|)?\s*([\s\S]{0,400}?)(?=\n\s*-?\s*(?:name:|uses:|run:)|\Z)",
                         text):
        block = m.group(1)
        for call in re.findall(r"\bpython\s+([A-Za-z_][\w./-]*\.py)\b", block):
            if not (R / call).exists():
                problems.append((wf.name, f"calls missing script {call}"))
            if "<<" in call or ">" in call:
                continue

# ---- every script a workflow might invoke exists ----
for f in ("make_app.py", "stage_app.py", "verify_app.py", "pricing.py",
          "learn.py", "selftest.py", "selftest_deep.py", "write_fixbook.py",
          "check_exposure.py", "build_paid_only.py", "publish_paid.py",
          "set_itch_url.py", "build_exe.py", "build_installer_app.py",
          "patcher.py", "app_scanner.py", "qa_loop.py", "providers.py",
          "buglog.py", "tokenmeter.py", "sizeguard.py", "selfheal.py",
          "discord_intro.py", "discord_tally.py", "budget.py",
          "weekly_guard.py", "check_repo_hygiene.py", "update_state.py",
          "update_plan.py", "update_discord.py", "update_weekly.py",
          "app_update.py", "update_trailer_script.py",
          "update_trailer_voice.py", "update_trailer_render.py",
          "update_trailer_mux.py", "update_selftest.py",
          "site_js_selftest.py", "signals.py", "goals.py",
          "improve_daily.py", "growth_selftest.py"):
    if not (R / f).exists():
        problems.append(("-", f"referenced script missing: {f}"))

# ---- the PayPal worker is gone; nothing may reach for it again ----
for gone in ("worker/worker.js", "worker/wrangler.toml", "paid_store.py",
             "verify_live_paypal.py", "site/full.html"):
    if (R / gone).exists():
        problems.append(("-", f"removed but still present: {gone}"))

# Every reference to the old payment worker has to be gone too, or it would
# silently point a buy button at something that no longer answers.
for f in R.rglob("*.py"):
    if ".git" in f.parts or f.name in ("selftest_audit.py",):
        continue
    try:
        body = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    for needle in ("slingshot-pay.bougnartaha2", "api/download?token=",
                   "/api/order"):
        if needle in body:
            problems.append((f.name, f"still calls the removed worker: {needle}"))

# ---- the repository must never track anything private ----
# The repo is public on purpose, because GitHub Pages serves the site from it,
# so this checks that the paid source, the money and the credentials stay out.
try:
    sys.path.insert(0, str(R))
    import check_repo_hygiene as _h
    for _p in _h.check_tracked(_h.tracked()):
        problems.append(("-", f"tracked but must not be: {_p}"))
    for _p in _h.check_ignore_rules():
        problems.append(("-", _p))
    for _p in _h.check_secrets(_h.tracked()):
        problems.append(("-", _p))
except Exception as _e:  # noqa: BLE001
    problems.append(("-", f"repo hygiene check failed: {_e}"))

# ---- the weekly cycle is wired up ----
# Every stage names the file that runs it, so a renamed or deleted script is
# caught here rather than silently doing nothing on schedule.
WEEKLY_STAGES = {
    "monday-vote.yml": ["weekly_cycle.py monday", "budget.py"],
    # the review runs through weekly_cycle.py, which calls the others
    "wednesday-review.yml": ["weekly_cycle.py wednesday",
                             "retire_product.py", "self_upgrade.py",
                             "weekly_guard.py", "check_exposure.py"],
    # The Friday lane closes this week's ballot and opens the next one. The
    # stage is named rather than pinned to one string, because the ballot has
    # to be closed before the build reads the vote, and the Monday stage only
    # closes a ballot that has aged out.
    "friday-build.yml": ["stage_app.py", "vote_steer.py", "budget.py",
                         "weekly_cycle.py", "selfheal.py",
                         "selftest.py"],
    "friday-verify.yml": ["verify_app.py", "build_paid_only.py",
                          "check_exposure.py", "weekly_guard.py",
                          "budget.py"],
    # the release lane: plan, announce, trailer, publish the public state
    "monthly-update.yml": ["update_plan.py", "update_discord.py",
                           "update_trailer_script.py",
                           "update_trailer_voice.py",
                           "update_trailer_render.py",
                           "update_trailer_mux.py", "update_state.py",
                           "weekly_guard.py", "update_selftest.py"],
    "weekly-patch.yml": ["update_weekly.py", "weekly_guard.py", "budget.py",
                         "update_selftest.py"],
    # the fast lane: it reads the goal and the signals, then tries one change
    "daily-improve.yml": ["signals.py", "goals.py", "improve_daily.py",
                          "self_upgrade.py", "weekly_guard.py",
                          "budget.py", "selftest.py"],
}
for name, scripts in WEEKLY_STAGES.items():
    path = wf_dir / name
    if not path.exists():
        problems.append(("-", f"weekly stage missing: {name}"))
        continue
    text = path.read_text(encoding="utf-8")
    for script in scripts:
        if script not in text:
            problems.append(("-", f"{name} never runs {script}"))

# The guard must actually protect the workflows and the price limits, or a
# self-improving job could edit its own schedule or raise its own ceiling.
try:
    sys.path.insert(0, str(R))
    import weekly_guard as _g
    for _p in ("site/index.html", "site/apps.json", "check_exposure.py",
               "pricing.py", "retire_product.py", "publish_paid.py",
               "set_itch_url.py",
               ".github/workflows/friday-build.yml",
               ".github/workflows/friday-verify.yml",
               ".github/workflows/monthly-update.yml",
               ".github/workflows/weekly-patch.yml",
               ".github/workflows/pages.yml"):
        if not _g.is_protected(_p):
            problems.append(("-", f"should be protected but is not: {_p}"))
    for _p in ("make_app.py", "verify_app.py", "weekly_guard.py"):
        if _g.is_protected(_p):
            problems.append(("-", f"should be improvable but is locked: {_p}"))

    # the price floor and ceiling have to be exactly the agreed amounts
    import pricing as _p2
    if abs(_p2.FLOOR - 1.0) > 0.001 or abs(_p2.CEILING - 10.0) > 0.001:
        problems.append(("-", f"price range moved: "
                             f"{_p2.FLOOR:.2f} to {_p2.CEILING:.2f}"))
    for _raw, _want in ((-99, 1.0), (0, 1.0), (5.0, 5.0), (99, 10.0)):
        if abs(_p2.clamp(_raw) - _want) > 0.001:
            problems.append(("-", f"clamp({_raw}) is {_p2.clamp(_raw)}, "
                                 f"expected {_want}"))
except Exception as _e:  # noqa: BLE001
    problems.append(("-", f"price or guard check failed: {_e}"))

# The budget has to be asked before work starts, not only reported afterwards.
for name in ("monday-vote.yml", "wednesday-review.yml", "friday-build.yml",
             "friday-verify.yml", "monthly-update.yml", "weekly-patch.yml",
             "daily-improve.yml"):
    path = wf_dir / name
    if path.exists() and "budget.py check" not in path.read_text(encoding="utf-8"):
        problems.append(("-", f"{name} runs without checking the budget"))

# Nothing protected may be committed by an automated job.
#
# This used to be a substring test for "git add -A" plus a protected filename
# anywhere in the workflow, with weekly_guard imported and then never called.
# That passes any workflow that merely mentions a protected path in a comment,
# which is how the monthly release job tripped it while only ever writing
# data/. The real rule is asked of the guard itself, so the two cannot drift.
sys.path.insert(0, str(R))
try:
    import weekly_guard as _guard
    for wf_file in sorted(wf_dir.glob("*.yml")):
        text = wf_file.read_text(encoding="utf-8")
        if "git add -A" not in text and "git add ." not in text:
            continue
        for line in text.splitlines():
            if "git add" not in line:
                continue
            # anything this step stages has to be allowed to change
            for token in line.replace("\\", " ").split():
                if token.startswith(("site/", ".github/", "pricing.",
                                     "publish_paid", "set_itch_url",
                                     "retire_product", "check_exposure")):
                    rel = token.strip("'\"").rstrip(",;")
                    if _guard.is_protected(rel):
                        problems.append(
                            ("-", f"{wf_file.name} stages the protected "
                                  f"{rel} with a blanket add"))
except ImportError:
    problems.append(("-", "weekly_guard.py cannot be imported"))

# ---- an unanchored ignore pattern must not swallow the published site
# .gitignore had "apps/" with no leading slash, and git matches an unanchored
# pattern at EVERY depth. That hid site/apps/, which is the deployed free
# catalogue, so the Friday job's "git add -A" committed data/candidate.json
# pointing at an app it had never committed. The verifier then failed every run
# with "staged file is gone", and it had failed that way on the first run too.
# These two need a real git repository. cleanroom_selftest.py runs this suite
# in a plain directory, where `git check-ignore` exits 128 and would otherwise
# be read as "not ignored", passing for the wrong reason.
def _ignored(rel: str) -> bool | None:
    r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=str(R),
                       capture_output=True, timeout=120, env=clean_env())
    if r.returncode == 128:
        return None                     # not a repository: cannot answer
    return r.returncode == 0


_here = _ignored("site/apps/probe/app/index.html")
if _here is True:
    problems.append(("-", "gitignore is hiding site/apps/, which is the "
                          "deployed free catalogue"))
for _probe, _want in (("apps/probe.py", True),
                      ("paid/probe/installer.nsi", True)):
    _got = _ignored(_probe)
    if _got is not None and _got != _want:
        problems.append(("-", f"gitignore no longer matches {_probe}"))

# ---- a committed file must not carry the build machine's folder layout
# data/candidate.json is tracked, and stage_app wrote paid_dir and installer as
# str(path.resolve()). The Friday runner's own directory went into a public
# repository, where every other machine resolved it to a path that is not
# there, so the verifier could never find the app it had been told to check.
for _rel in ("data/candidate.json", "data/published.json"):
    _p = R / _rel
    if not _p.exists():
        continue
    try:
        _body = json.loads(_p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        continue
    if not isinstance(_body, dict):
        continue
    for _k, _v in _body.items():
        if isinstance(_v, str) and re.match(r"^[A-Za-z]:[\\/]", _v):
            problems.append((_rel, f"{_k} holds an absolute path: {_v[:50]}"))
_src = (R / "stage_app.py").read_text(encoding="utf-8")
if "def _rel(" not in _src:
    problems.append(("stage_app.py", "stores paths absolutely, which publishes "
                                     "the build machine's layout"))

# ---- a test must not be able to reach the real world
# A selftest that starts a child process with the inherited environment gets
# the runner's real credentials, and a scheduled runner has them. That is how
# update_selftest.py came to create a real Discord guild event: it called
# upsert() expecting it to refuse for want of a token, and the token was
# there. The same shape lets a test spend real model tokens, push a real
# build to itch.io, or post to the real server.
#
# The rule this enforces: a selftest that starts a child process must pass an
# explicit env=, and that env must not be the ambient one. The check is on
# the source, because a test that could reach out is wrong even on the day
# nothing does.
def _child_calls(path):
    """Every subprocess.run / Popen call in a file, as ast nodes."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError):
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        if fn.attr not in ("run", "Popen"):
            continue
        if not isinstance(fn.value, ast.Name) or fn.value.id != "subprocess":
            continue
        yield node


def _env_is_ambient(node) -> bool:
    """Does this env= argument carry the ambient environment through?"""
    for kw in node.keywords:
        if kw.arg != "env":
            continue
        v = kw.value
        if isinstance(v, ast.Dict):
            for k, val in zip(v.keys, v.values):
                if isinstance(k, ast.Constant) and k.value == "**":
                    return True
                if isinstance(k, ast.Constant) and k.value == "**os.environ":
                    return True
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) \
                and v.func.id == "dict":
            for kw2 in v.keywords:
                if kw2.arg is None and isinstance(kw2.value, ast.Attribute) \
                        and kw2.value.attr == "environ":
                    return True
        if isinstance(v, ast.Name) and v.id == "os.environ":
            return True
    return False


for _p in py_files:
    if "selftest" not in _p.name:
        continue
    _body = _p.read_text(encoding="utf-8", errors="ignore")
    if "subprocess.run" not in _body and "subprocess.Popen" not in _body:
        continue
    for _node in _child_calls(_p):
        _has_env = any(kw.arg == "env" for kw in _node.keywords)
        if not _has_env:
            problems.append((_p.name, "starts a child process with the "
                                      "inherited environment, so it can reach "
                                      "the real service with the runner's "
                                      "credentials"))
            break
    for _node in _child_calls(_p):
        if _env_is_ambient(_node):
            problems.append((_p.name, f"line {_node.lineno} copies the "
                                      "ambient environment into a child "
                                      "process, so the real credentials are "
                                      "still reachable"))
            break

print("== problems ==")
if not problems:
    print("  none")
for name, detail in problems:
    print(f"  {name}: {detail}")

print(f"\n{len(problems)} problems across {len(py_files)} files")
sys.exit(1 if problems else 0)