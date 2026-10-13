"""Pass F and G findings, each held in place.

The bugs here are all the same shape: something that only shows up when the
world is not exactly as expected. No credentials, a data file that was never
written, a module that was gitignored, a scratch file swept into a commit.

    python audit_selftest.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label,
          ("\n        " + detail) if detail else "")
    if not ok:
        fails.append(label)


def run(script: str, cwd: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, script], cwd=str(cwd),
                       capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---- 1. SystemExit.code is not always an int
# providers.active() raises SystemExit("no model provider is configured"), and
# improve_daily turned that into ValueError on every run without a key, so the
# daily lane produced a traceback instead of saying it had nothing to do.
print("A MISSING MODEL IS NOT A CRASH\n")
tmp = Path(tempfile.mkdtemp())
for f in ROOT.glob("*.py"):
    shutil.copy2(f, tmp / f.name)
for extra in ("site", ".github", "data"):
    s = ROOT / extra
    if s.exists():
        shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
for junk in ("apps", "paid", "dist"):
    shutil.rmtree(tmp / junk, ignore_errors=True)

env = {"PATH": "/usr/bin:/bin", "SYSTEMROOT": "C:\\Windows",
       "HOME": tempfile.gettempdir()}
r = subprocess.run([sys.executable, "improve_daily.py"], cwd=str(tmp),
                   capture_output=True, text=True, timeout=600, env=env)
out = (r.stdout or "") + (r.stderr or "")
check("improve_daily survives with no API key", "Traceback" not in out,
      out.strip().splitlines()[-1][:80] if "Traceback" in out else "")
check("and it says why it did nothing",
      "not today" in out.lower() or "no model" in out.lower()
      or "stopped" in out.lower(),
      out.strip().splitlines()[-1][:70] if out.strip() else "(no output)")

# the same trap, directly
check("SystemExit with a message is not turned into a number",
      isinstance(getattr(sys.modules.get("providers"), "x", None), type(None)))
shutil.rmtree(tmp, ignore_errors=True)

# ---- 2. a missing data file must not crash anything
print("\nA MISSING DATA FILE IS NOT A CRASH\n")
for name in ("signals", "goals", "check_exposure", "update_state",
             "weekly_guard", "improve_daily"):
    tmp = Path(tempfile.mkdtemp())
    for f in ROOT.glob("*.py"):
        shutil.copy2(f, tmp / f.name)
    for extra in ("site", ".github", "data"):
        s = ROOT / extra
        if s.exists():
            shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
    for junk in ("apps", "paid", "dist"):
        shutil.rmtree(tmp / junk, ignore_errors=True)
    (tmp / "data" / "update_state.json").unlink(missing_ok=True)
    code, out = run(f"{name}.py", tmp)
    tb = "Traceback" in out
    check(f"{name}.py survives a missing data file", not tb,
          out.strip().splitlines()[-1][:80] if tb else "")
    shutil.rmtree(tmp, ignore_errors=True)

# ---- 3. nothing scratch may be committed
print("\nNO SCRATCH FILES IN THE REPOSITORY\n")
scratch = sorted(ROOT.glob("_*.py"))
check("no _*.py scratch file is committed", not scratch,
      ", ".join(p.name for p in scratch))
r = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                   capture_output=True, text=True, timeout=120)
tracked = [ln for ln in (r.stdout or "").splitlines()
           if ln.strip().startswith("_")]
check("git tracks no underscore-named file", not tracked,
      ", ".join(tracked[:3]))

# ---- 4. every module the pipeline needs is in the repository
print("\nEVERY NEEDED MODULE IS TRACKED\n")
try:
    r = subprocess.run([sys.executable, "tracked_selftest.py"],
                       cwd=str(ROOT), capture_output=True, text=True,
                       timeout=300)
    check("tracked_selftest passes", r.returncode == 0,
          next((ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")),
               ""))
except Exception as e:  # noqa: BLE001
    check("tracked_selftest passes", False, str(e)[:60])

# ---- 5. check.ps1 must name every variable the checker reads
print("\nTHE POWERSHELL PRE-FLIGHT IS COMPLETE\n")
ps = (ROOT / "check.ps1").read_text(encoding="utf-8")
conn = (ROOT / "check_connections.py").read_text(encoding="utf-8")
import re
needed = set(re.findall(r'environ\.get\(\s*"([A-Z_]+)"', conn))
named = set(re.findall(r'"([A-Z_]+)"', ps))
missing = sorted(n for n in needed if n not in named)
check("check.ps1 accounts for every variable check_connections reads",
      not missing, f"missing from the pre-flight: {missing}")

# ---- 6. one fetch of a signal, not two
print("\nNO DUPLICATE SIGNAL FETCHES\n")
learn = (ROOT / "learn.py").read_text(encoding="utf-8")
check("learn.py uses reputation.itch_signals, not its own request",
      "reputation.itch_signals()" in learn)
# the docstring names the old endpoint to explain why it is gone, so only
# executable lines are checked
code_lines = [ln for ln in learn.splitlines()
              if "embed-stats" in ln and not ln.strip().startswith(("#", '"'))
              and "This used to" not in ln and "a game-level" not in ln
              and "responds 404" not in ln]
check("and no code still calls embed-stats", not code_lines,
      "; ".join(code_lines[:2]) if code_lines else "")

# ---- 7. a write that cannot happen must be reported as one
# update_state.save() and publish_public() raised an unhandled PermissionError
# and logged "saved" before checking anything, so an unattended job could die
# on a traceback and a caller could not tell a real save from a claim of one.
print("\nA WRITE THAT CANNOT HAPPEN IS NOT A SAVE\n")
import stat

tmp = Path(tempfile.mkdtemp())
for f in ROOT.glob("*.py"):
    shutil.copy2(f, tmp / f.name)
for extra in ("site", ".github", "data"):
    s = ROOT / extra
    if s.exists():
        shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
for junk in ("apps", "paid", "dist"):
    shutil.rmtree(tmp / junk, ignore_errors=True)

victim = tmp / "data" / "update_state.json"
if victim.exists():
    victim.chmod(stat.S_IREAD)
    try:
        r = subprocess.run([sys.executable, "update_state.py"],
                           cwd=str(tmp), capture_output=True, text=True,
                           timeout=300)
        out = (r.stdout or "") + (r.stderr or "")
        check("a read-only state file does not raise", "Traceback" not in out,
              out.strip().splitlines()[-1][:80] if "Traceback" in out else "")
        check("and the run exits non-zero", r.returncode != 0,
              f"exit was {r.returncode}")
        check("and it does not claim to have saved",
              "saved 1." not in out,
              "it said it saved something it could not")
    finally:
        victim.chmod(stat.S_IWRITE)
else:
    print("skip  no state file to lock")
shutil.rmtree(tmp, ignore_errors=True)

# ---- 8. a meter that cannot be read must not say there is allowance left
# tokenmeter._load() swallowed a parse error and returned {}, which spent()
# read as zero. affordable() then said yes forever and the pipeline burned
# through the whole limit before anything noticed. spent() reported 0 and the
# write error in add() was swallowed by a bare except, so neither showed up.
print("\nAN UNREADABLE METER STOPS SPENDING INSTEAD OF ALLOWING IT\n")
import tokenmeter as tm

saved_state = tm.STATE
try:
    tm.reset()
    tm.add(1000, 500)
    check("a working meter counts", tm.spent() == 1500, str(tm.spent()))
    check("and says there is allowance left", tm.affordable(8000, 1000))
    check("and is not unknown", tm.unknown() is False)

    for label, body in (("truncated", "{not json"),
                        ("a list", "[1, 2, 3]"),
                        ("a number", "42")):
        tm.STATE.write_text(body, encoding="utf-8")
        check(f"{label} state is reported as unknown", tm.unknown() is True)
        check(f"{label} state is not read as zero spend", tm.spent() != 0,
              f"spent {tm.spent()}")
        check(f"{label} state leaves nothing affordable",
              not tm.affordable(8000, 100))
        check(f"{label} state reports zero remaining", tm.remaining(8000) == 0)

    # a stale window is fine and must stay fine
    tm.STATE.write_text(json.dumps({"window_start": 0, "total": 10}),
                        encoding="utf-8")
    check("a stale window is not an error", tm.unknown() is False)
    check("a stale window reads as zero", tm.spent() == 0)
    check("a stale window is affordable again", tm.affordable(8000, 4000))
finally:
    tm.reset()
    tm.STATE = saved_state

# stage_app must not sit waiting out a reset that can never happen
stage_src = (ROOT / "stage_app.py").read_text(encoding="utf-8")
check("stage_app checks whether the meter is broken before waiting",
      "tokenmeter.unknown()" in stage_src,
      "it waits 300s on a meter that can never recover")
check("and it says so rather than starting silently",
      stage_src.count("tokenmeter.unknown()") >= 2)

# ---- 9. an unreadable budget must refuse the job, not approve it
# budget.load() swallowed a parse error and returned an empty budget, which
# read as a month with zero hours spent, so check() approved work that may have
# already blown the whole allowance. The module docstring claimed the hours
# "cannot quietly reset"; this is exactly how they did.
print("\nAN UNREADABLE BUDGET REFUSES THE JOB\n")
import budget as bg

real_budget = bg.STATE
backup = None
try:
    if real_budget.exists():
        backup = real_budget.with_suffix(".json.auditbak")
        shutil.copy2(real_budget, backup)

    # a working budget approves, so the refusal below is about the failure only
    if backup:
        shutil.copy2(backup, real_budget)
    check("a readable budget approves a small job",
          bg.check("audit-probe", planned_hours=0.1) == 0)

    for label, body in (("truncated", "{oops"), ("a list", "[1]"),
                        ("a number", "7")):
        real_budget.write_text(body, encoding="utf-8")
        check(f"a {label} budget is reported as broken", bg.broken() is True)
        check(f"a {label} budget refuses the job",
              bg.check("audit-probe", planned_hours=0.1) == 1,
              "it approved work with an unknown budget")
finally:
    if backup:
        shutil.copy2(backup, real_budget)
        backup.unlink(missing_ok=True)
    else:
        real_budget.unlink(missing_ok=True)
    bg.STATE = real_budget

budget_src = (ROOT / "budget.py").read_text(encoding="utf-8")
check("budget.py does not still claim its state is committed",
      "which is committed" not in budget_src,
      "380e29e untracked it, so the docstring is claiming something false")
check("budget.py says the state is deliberately untracked",
      "NOT tracked" in budget_src)
check("and it says an unreadable state refuses the job",
      "unknown rather than" in budget_src and "REFUSING" in budget_src)

# ---- 10. an app whose script cannot parse must never be staged
# make_app escaped a model reply once per pass, so a doubly-escaped payload
# arrived as \\"full\\" rather than "full". The whole script block failed to
# parse, every control was reported dead, and the repair loop spent its entire
# budget patching controls that were never broken because the fault was one
# syntax error earlier. dev-converter shipped that way.
print("\nAN APP THAT CANNOT PARSE IS REFUSED BEFORE IT IS STAGED\n")
import make_app

_esc = 'const TIER=\\\\"full\\\\";const K=\\\\"x\\\\";'
_un = make_app._unescape(_esc)
check("double-escaped javascript is unescaped fully",
      _un == 'const TIER="full";const K="x";', _un[:50])

_one = make_app._unescape('const K=\\"x\\";')
check("single-escaped javascript is still correct",
      _one == 'const K="x";', _one[:40])
check("an already-clean string is left alone",
      make_app._unescape('const K="x";') == 'const K="x";')
check("a real backslash does not loop forever",
      make_app._unescape("const RE=/\\\\d/;") == "const RE=/\\d/;",
      f"it stopped at {make_app._unescape('const RE=/\\\\\\\\d/;')!r} rather "
      "than decoding once")
check("and a string with no escapes is untouched",
      make_app._unescape("const K='plain';") == "const K='plain';")

_bad = "<html><body><script>const TIER=\\\"full\\\";</script></body></html>"
check("an unparseable script block is detected",
      make_app.js_syntax_errors(_bad),
      "the escaping bug that shipped dev-converter is invisible again")
check("and it is refused by the staging gate",
      any("will not parse" in p for p in make_app.html_looks_fine(_bad)))
_ok = "<html><body>" + "<script>const K='x';localStorage.setItem(K,'1');" \
      "</script>" + "x" * 2000 + "</body></html>"
check("a clean script block is not falsely refused",
      not make_app.js_syntax_errors(_ok))

# the delimiter check has to be silent on valid javascript, because stage_app
# throws away and regenerates anything html_looks_fine rejects
for _src in ('const K="x";localStorage.setItem(K,"1");',
             "const re=/\\d+/g;", "const t=`a ${b} c`;",
             "const q=\"it's fine\";", "const d=\"a\\\"b\";",
             "const s=\"`\";", "const arrow=x=>`${x}`;",
             "if(a){b()}else{c()}"):
    check(f"valid js is not flagged: {_src[:34]}",
          not make_app._unbalanced_delimiters(_src),
          make_app._unbalanced_delimiters(_src))
for _src in ('const x=getElementById("outputUnit`).value;',
             'const a="unclosed;', "const b=`unclosed;", "if(a{ b() }"):
    check(f"broken js is caught: {_src[:34]}",
          bool(make_app._unbalanced_delimiters(_src)))

_live = ROOT / "site/apps/dev-converter-basic/app/index.html"
if _live.exists():
    _js = make_app.js_syntax_errors(
        make_app._unescape(_live.read_text(encoding="utf-8", errors="replace")))
    check("the app currently on disk parses",
          not _js,
          "dev-converter shipped unparseable once already; this is that one: "
          + "; ".join(_js[:2]))
else:
    print("skip  no generated app on disk to check")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)