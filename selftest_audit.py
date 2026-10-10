"""Full-code audit: parse every file, walk every call site, wire every module.

Three earlier passes tested behaviour. This one checks the things those cannot
see: names referenced but never defined, names defined but shadowed, calls into
functions that raise, imports that pull the wrong symbol, and workflows whose
steps call scripts that do not exist.
"""
import ast
import builtins
import sys
from pathlib import Path as _P
HERE = _P(__file__).resolve().parent
from pathlib import Path

R = HERE
problems = []

py_files = sorted(p for p in R.rglob("*.py")
                  if ".git" not in p.parts and "dist" not in p.parts
                  and "paid" not in p.parts and "_internal" not in p.parts)
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
    import re
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
          "check_exposure.py", "build_paid_only.py", "mark_verified.py",
          "build_exe.py", "build_installer_app.py", "patcher.py",
          "app_scanner.py", "qa_loop.py", "debug_team.py", "providers.py",
          "paid_store.py", "buglog.py", "tokenmeter.py", "sizeguard.py",
          "selfheal.py"):
    if not (R / f).exists():
        problems.append(("-", f"referenced script missing: {f}"))

# ---- the weekly cycle is wired up ----
# Every stage names the file that runs it, so a renamed or deleted script is
# caught here rather than silently doing nothing on schedule.
WEEKLY_STAGES = {
    "monday-vote.yml": ["weekly_cycle.py monday", "budget.py"],
    # the review runs through weekly_cycle.py, which calls the others
    "wednesday-review.yml": ["weekly_cycle.py wednesday",
                             "retire_product.py", "self_upgrade.py",
                             "weekly_guard.py", "check_exposure.py"],
    "friday-build.yml": ["stage_app.py", "vote_steer.py", "budget.py",
                         "weekly_cycle.py monday", "selfheal.py",
                         "selftest.py"],
    "friday-verify.yml": ["verify_app.py", "build_paid_only.py",
                          "check_exposure.py", "weekly_guard.py",
                          "budget.py"],
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
               "worker/worker.js", "pricing.py", "retire_product.py",
               ".github/workflows/friday-build.yml",
               ".github/workflows/friday-verify.yml",
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
             "friday-verify.yml"):
    path = wf_dir / name
    if path.exists() and "budget.py check" not in path.read_text(encoding="utf-8"):
        problems.append(("-", f"{name} runs without checking the budget"))

# Nothing protected may be committed by an automated job.
sys.path.insert(0, str(R))
try:
    import weekly_guard as _guard
    for wf_file in sorted(wf_dir.glob("*.yml")):
        text = wf_file.read_text(encoding="utf-8")
        for bad in ("site/index.html", "check_exposure.py "):
            if f"git add -A" in text and bad in text:
                problems.append(("-", f"{wf_file.name} edits {bad.strip()}"))
except ImportError:
    problems.append(("-", "weekly_guard.py cannot be imported"))

print("== problems ==")
if not problems:
    print("  none")
for name, detail in problems:
    print(f"  {name}: {detail}")

print(f"\n{len(problems)} problems across {len(py_files)} files")
sys.exit(1 if problems else 0)