"""Pass C, empirically: does the pipeline work from a different directory?

Static reading of paths is unreliable — "site/icon-512.png" looked suspicious
and turned out to be joined to ROOT correctly two lines later. So this moves
the working directory instead and runs each entry point there, which is what a
cron job or a double-click actually does.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(".").resolve()
fails = []

# entry points that read the repository and can be run without credentials
SCRIPTS = [
    "links.py", "check_links.py", "check_exposure.py", "check_repo_hygiene.py",
    "weekly_guard.py", "selftest.py", "selftest_audit.py",
    "selftest_deep.py", "tracked_selftest.py", "audit_selftest.py",
    "growth_selftest.py", "property_selftest.py", "update_selftest.py",
    "site_js_selftest.py", "links_selftest.py", "update_state.py",
    "goals.py", "signals.py", "improve_daily.py --list", "update_plan.py --show",
]

tmp = Path(tempfile.mkdtemp(prefix="cwdtest-"))
for f in ROOT.glob("*.py"):
    shutil.copy2(f, tmp / f.name)
# the .ps1 has to come too: a check that only passes when one file is missing
# from the copy is not checking anything
for f in ROOT.glob("*.ps1"):
    shutil.copy2(f, tmp / f.name)
for extra in ("site", ".github", "data", "assets"):
    s = ROOT / extra
    if s.exists():
        shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
for junk in ("apps", "paid", "dist"):
    shutil.rmtree(tmp / junk, ignore_errors=True)

# run from a directory that is NOT the repo
elsewhere = Path(tempfile.mkdtemp(prefix="elsewhere-"))

print("RUNNING EVERY ENTRY POINT FROM AN UNRELATED DIRECTORY")
print(f"  repo copy : {tmp}")
print(f"  cwd       : {elsewhere}")
print()
for script in SCRIPTS:
    parts = script.split()
    r = subprocess.run([sys.executable, str(tmp / parts[0]), *parts[1:]],
                       cwd=str(elsewhere), capture_output=True, text=True,
                       timeout=900)
    bad = "Traceback" in (r.stdout or "") + (r.stderr or "")
    # the scripts that intentionally exit 1 do so with a message
    if r.returncode not in (0, 1) or bad:
        fails.append(script)
        print(f"  FAIL  {script}")
        tail = [ln for ln in ((r.stdout or "") + (r.stderr or "")).splitlines()
                if ln.strip()][-1:]
        print(f"        rc={r.returncode} {tail[0][:78] if tail else ''}")
    else:
        print(f"  ok    {script}")

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(elsewhere, ignore_errors=True)
print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)