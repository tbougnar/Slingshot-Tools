"""Self-healing build debugger.

When the build workflow fails, this collects the evidence, asks the model what
broke and what to change, applies the patch under strict limits, and lets the
workflow run again.

Guardrails, because a model is editing the code that takes payments:

  * only files on ALLOWED may be touched - the pipeline only, never the price
    bounds, never the itch.io links, never the site output or policies
  * FORBIDDEN patterns are rejected outright (payment endpoints, price clamps,
    publish gating, secrets, delete/rm of the paid folder)
  * every patch is compiled and must survive a test run before it counts
  * a hard attempt cap, then it stops and says so instead of thrashing
  * every patch is a separate commit, so it is visible and revertable
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Windows consoles default to a legacy code page, so any non-ASCII character in
# model output used to raise UnicodeEncodeError and kill the run. Output that
# cannot be encoded is replaced rather than fatal.
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _safe(text) -> str:
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return "<unprintable>"


from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_ATTEMPT = int(os.environ.get("SELFHEAL_MAX", "3"))
# The debug team picks its own live models (providers.model_chain); this name is
# kept only so an older caller that imports it still resolves to something real.
try:
    import providers as _providers
    MODEL = _providers.default_model("debug")
except (ImportError, SystemExit):
    MODEL = "openai/gpt-oss-120b"

ALLOWED = {
    "make_app.py",
    "learn.py",
    "build_exe.py",
    "build_installer_app.py",
    "native_launcher.py",
    "selfheal.py",
}

# The scripts that make the site work are protected by weekly_guard, and two
# of them were in the list above, so the repair lane could rewrite the very
# scripts the guard exists to protect and the gate would not have said so,
# because the gate was not looking. A file that is protected is not
# repairable, whatever else says so.
#
# The import failing used to be tolerated, which left the protected set empty
# and the final guard check skipped: the one lane that edits live code failed
# open. A repair lane that cannot consult the rule set must not run at all.
try:
    import weekly_guard as _guard
    _PROTECTED = set(_guard.all_protected()) | {
        p for p in _guard.MONEY_AND_DEATH}
except Exception as e:  # noqa: BLE001
    raise RuntimeError(
        "selfheal cannot run without weekly_guard: the protected-file rules "
        f"and the rollback guarantee depend on it ({str(e)[:120]})") from None

FORBIDDEN = [
    r"itch_url",              # where a product is sold
    r"publish_paid",
    r"PRICE_FLOOR",
    r"PRICE_CEILING",
    r"ITCH_(API_KEY|USER)",
    r"LICENSE_SECRET",
    r"CF_API_TOKEN",
    r"cfut_",
    r"github_pat_",
    r"staging\.lockdown",
    r"rmtree",
    r"published\s*=\s*True",
    r"selfheal\.env",
]

SYSTEM = """You repair a Python build pipeline for a small app store.

You will get a failure report from a GitHub Actions run. Reply with JSON only:
{"diagnosis": "<one sentence>", "fixes": [{"file": "<repo-relative path>",
"note": "<what changed>", "content": "<the COMPLETE new file content>"}]}

Rules:
- content must be the entire file, not a fragment or a diff.
- Keep the change as small as possible. Do not refactor working code.
- Preserve every existing behaviour that is not the direct cause of the failure.
- Never touch payment endpoints, pricing bounds, secrets, or publish gating.
- Never disable the quality checks to make a failure disappear.
- If the report shows an infrastructure problem (network, rate limit, outage),
  return {"diagnosis": "...", "fixes": []} and say so instead of editing code.
"""


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def collect(attempt: int) -> dict:
    """Gather the evidence: the failing job's log tail and the last commits."""
    log = ""
    # The log is looked for in several places, because where it lands depends
    # on how it was fetched. It used to look only in selfheal/, a directory
    # nothing in this repository ever wrote, so the repair lane found no
    # evidence on any run and gave up before it asked anything. The generate
    # job now keeps its output as an artifact and the workflow downloads it
    # into data/.
    for p in ("selfheal/last_run.log", "selfheal/failure.txt",
              "data/generate-log.txt"):
        f = ROOT / p
        if f.exists():
            log += f.read_text(encoding="utf-8", errors="replace") + "\n"
    for pattern in ("data/generate-log/*.txt", "data/*.log", "data/*.txt"):
        for f in sorted(ROOT.glob(pattern)):
            log += f.read_text(encoding="utf-8", errors="replace") + "\n"
    tail = log[-12000:]
    _, recent = run(["git", "log", "--oneline", "-8"])
    _, status = run(["git", "status", "--porcelain"])
    return {"attempt": attempt, "log_tail": tail, "recent_commits": recent,
            "git_status": status[:2000]}


def ask(diag: dict) -> dict:
    """The debugger team works to a fixed order.

    Each debugger reads the fixbook first. If they agree, that fix is proposed.
    If they disagree, every proposal is reported so each can be tried and
    tested separately. If they all fail, the team researches together.
    """
    report = json.dumps(diag)[:12000]
    try:
        import debug_team2 as team
    except ImportError:
        return {"diagnosis": "debugger team unavailable", "fixes": []}
    if not os.environ.get("GROQ_API_KEY") \
            and not os.environ.get("OPENROUTER_API_KEY") \
            and not os.environ.get("GEMINI_API_KEY") \
            and not os.environ.get("CEREBRAS_API_KEY"):
        return {"diagnosis": "no model provider key available", "fixes": []}

    props = team.proposals(report, team.DEBUGGERS)
    if not props:
        return {"diagnosis": "no debugger could answer", "fixes": []}

    key, agree = team.agreement(props)
    if len(agree) >= 2:
        print(f"[selfheal] {len(agree)}/{len(props)} debuggers agreed")
    else:
        print(f"[selfheal] no agreement: {[d.get('fix','')[:40] for _, d in props]}")
        return {"diagnosis": "debuggers disagreed: "
                              + " | ".join(d.get("fix", "")[:120] for _, d in props),
                "fixes": [], "disagreed": [d for _, d in props]}

    chosen = props[0][1]
    chosen_model = props[0][0]
    for model, d in props:
        if re.sub(r"\s+", " ", d.get("fix", "").strip().lower())[:160] == key:
            chosen, chosen_model = d, model
            break

    files = [f for f in (chosen.get("files") or []) if f in ALLOWED]
    if not files:
        return {"diagnosis": f"proposed fix touches no allowed file: "
                              f"{chosen.get('files')}", "fixes": []}

    # A diagnosis is not a patch. Ask the agreeing debugger for the complete
    # rewritten file, which safe() then checks and apply() compiles and tests.
    name = files[0]
    try:
        current = (ROOT / name).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"diagnosis": f"the fix targets {name}, which cannot be read: "
                              f"{str(e)[:80]}", "fixes": []}
    content = team.rewrite(chosen_model, name, current,
                           str(chosen.get("fix") or ""))
    if not content:
        return {"diagnosis": chosen.get("diagnosis") or "agreed fix",
                "fixes": [{"file": name, "note": chosen.get("fix", ""),
                           "content": None}],
                "research": None}

    return {"diagnosis": chosen.get("diagnosis") or "agreed fix",
            "fixes": [{"file": name, "note": chosen.get("fix", ""),
                       "content": content}],
            "research": None}


def research(diag: dict, tried: list[str]) -> dict:
    """Every proposal failed, so the team researches instead of guessing."""
    try:
        import debug_team2 as team
    except ImportError:
        return {"diagnosis": "debugger team unavailable", "fixes": []}
    got = team.research(json.dumps(diag)[:10000], team.DEBUGGERS, tried)
    if not got:
        return {"diagnosis": "research found nothing usable", "fixes": []}
    files = [f for f in (got.get("files") or []) if f in ALLOWED]
    if not files:
        return {"diagnosis": "research proposed no allowed file", "fixes": []}
    name = files[0]
    try:
        current = (ROOT / name).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"diagnosis": f"research targets {name}, which cannot be read: "
                              f"{str(e)[:80]}", "fixes": []}
    content = team.rewrite(got.get("model") or team.DEBUGGERS[0], name, current,
                           str(got.get("fix") or ""))
    return {"diagnosis": f"research: {got.get('found','')[:160]}",
            "fixes": [{"file": name, "note": got.get("fix", ""),
                       "content": content or None}]}


def safe(plan: dict) -> list[dict]:
    """Keep only fixes that are allowed and that violate nothing."""
    if _guard is None:
        print("[selfheal] the guard is unavailable - refusing every patch")
        return []
    keep = []
    for fix in plan.get("fixes") or []:
        name = str(fix.get("file", "")).replace("\\", "/").strip()
        if name not in ALLOWED:
            continue
        # A protected file is never repairable, whatever the list says. The
        # guard is what stands between the lane and the scripts that decide
        # what a customer gets, and a file the guard protects cannot be in
        # the repairable set as well.
        if name in _PROTECTED or _guard.is_protected(name):
            print(f"[selfheal] refused {name}: it is protected")
            continue
        content = fix.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        bad = [p for p in FORBIDDEN if re.search(p, content)]
        if bad:
            print(f"[selfheal] refused {name}: touches {bad[0]}")
            continue
        if len(content.splitlines()) < 5:
            continue
        keep.append({"file": name, "note": str(fix.get("note", ""))[:200],
                     "content": content})
    return keep


LESSONS = ROOT / "data" / "lessons.txt"


def remember(diagnosis: str, fixes: list[dict]) -> None:
    """Write the lesson down so the builder is told next time.

    This was called twice and never defined, so the debugger crashed with a
    NameError at the exact moment it tried to record what it had learned.
    """
    if not fixes:
        return
    try:
        import buglog
    except ImportError:
        return
    files = [f.get("file", "?") for f in fixes]
    what = "; ".join(str(f.get("note", ""))[:200] for f in fixes)
    entry = buglog.record(
        symptom=diagnosis,
        cause=(fixes[0].get("note") or diagnosis)[:300],
        fix=what[:400],
        files=files,
        detects=f"recurs if {files[0]} changes this behaviour",
        verified=False)
    print(f"[selfheal] fixbook {entry['id']} recorded: {diagnosis[:80]}")


def apply(fixes: list[dict], attempt: int, diagnosis: str) -> bool:
    if not fixes:
        print("[selfheal] no changes proposed - stopping here")
        return False
    backups: dict[str, str] = {}
    for f in fixes:
        target = ROOT / f["file"]
        content = f.get("content")
        if content is None:
            print(f"[selfheal] proposal is guidance only, not a patch: "
                  f"{f['note'][:90]}")
            print("[selfheal] recording it in the fixbook instead")
            remember(diagnosis, [f])
            return False
        backup = target.read_text(encoding="utf-8", errors="replace")
        backups[f["file"]] = backup
        target.write_text(content, encoding="utf-8")
        rc, out = run([sys.executable, "-m", "py_compile", f["file"]], timeout=180)
        if rc != 0:
            print(f"[selfheal] {f['file']} did not compile - reverting")
            target.write_text(backup, encoding="utf-8")
            return False

    def _revert() -> None:
        for name, text in backups.items():
            (ROOT / name).write_text(text, encoding="utf-8")

    # A patch that parses is not a patch that works. The suite is the only
    # thing that says the pipeline still works, and this lane used to compile
    # the file and stop, so a whole-file rewrite that broke the build but
    # still parsed was committed to main and pushed.
    rc, out = run([sys.executable, "run_selftests.py", "--quiet"], timeout=3600)
    if rc != 0:
        print("[selfheal] the suite fails with the patch in place - reverting")
        for line in out.splitlines():
            if "FAIL" in line or "failing" in line:
                print("   ", line.strip()[:110])
        _revert()
        return False

    # The guard has the last word, and it has it before anything is
    # committed. The workflow asks the guard as well, but by then the patch
    # is already in history and the working tree is clean. A violation must
    # also put the file back: returning False used to leave the forbidden
    # edit sitting in the tree for the next step to commit.
    if _guard is None:
        print("[selfheal] the guard is unavailable - reverting the patch")
        _revert()
        return False
    bad = _guard.violations([f["file"] for f in fixes])
    if bad:
        print("[selfheal] refusing to commit: these are protected")
        for p in bad:
            print("  -", p)
        _revert()
        return False

    # Only the patched file is staged. "git add -A" committed whatever else
    # happened to be in the tree, so the commit mixed the patch with
    # unrelated files and the patch was not visible on its own.
    for f in fixes:
        run(["git", "add", "--", f["file"]])
    msg = f"fix(attempt {attempt}): {diagnosis[:120]}"
    rc, out = run(["git", "-c", "user.name=slingshot-bot",
                   "-c", "user.email=bot@users.noreply.github.com",
                   "commit", "-q", "-m", msg])
    if rc != 0:
        print("[selfheal] nothing to commit")
        return False
    print(f"[selfheal] committed: {msg}")
    for f in fixes:
        print(f"           {f['file']}: {f['note'][:100]}")
    return True


def main() -> int:
    attempt = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    if attempt > MAX_ATTEMPT:
        print(f"[selfheal] {attempt} attempts already made - stopping for a human")
        return 1
    diag = collect(attempt)
    if not diag["log_tail"].strip():
        print("[selfheal] no failure log found")
        return 1
    print(f"[selfheal] attempt {attempt}/{MAX_ATTEMPT}: asking the model what broke")
    plan = ask(diag)
    diagnosis = str(plan.get("diagnosis", "")).strip() or "unspecified"
    print(f"[selfheal] diagnosis: {diagnosis}")
    fixes = safe(plan)
    print(f"[selfheal] {len(fixes)} fix(es) allowed by policy")
    if fixes:
        remember(diagnosis, fixes)
    return 0 if apply(fixes, attempt, diagnosis) else 1


if __name__ == "__main__":
    raise SystemExit(main())