"""Run every selftest in the repository and report one number.

There are now more than a dozen of them, each with its own output convention,
and running them by hand is how one of them sat broken for weeks. This is the
single command: it runs all of them, says which passed and which did not, and
exits non-zero if any failed.

The e2e journeys are deliberately not in here. They go over the network and
they fail on purpose while the shop is closed, which would make this file
useless as a gate. Run those with ``python e2e_all.py``.

    python run_selftests.py
    python run_selftests.py --quiet
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from testenv import clean_env

# these are the orchestrators, not tests of their own
SKIP = {"run_selftests.py", "cleanroom_selftest.py"}


def tests() -> list[Path]:
    found = sorted(ROOT.glob("*selftest*.py"))
    return [f for f in found if f.name not in SKIP]


def main() -> int:
    args = [a.lower() for a in sys.argv[1:]]
    quiet = "--quiet" in args
    found = tests()
    failed: list[str] = []

    for f in found:
        # The credentials are taken out of the environment every test runs
        # with. A test that reaches out with a real key is a test that can
        # spend real money, post to the real server or push a real build, and
        # a scheduled runner has those keys. A test that forgets to protect
        # itself is still protected here.
        r = subprocess.run([sys.executable, f.name], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=900,
                           env=clean_env())
        out = (r.stdout or "") + (r.stderr or "")
        ok = r.returncode == 0
        note = ""
        for line in out.splitlines():
            if "FAILURES:" in line and "none" not in line:
                note = line.strip()[:70]
                break
        if not ok and not note:
            tail = [ln for ln in out.splitlines() if ln.strip()][-1:]
            note = tail[0].strip()[:70] if tail else f"exit {r.returncode}"
        if not ok:
            failed.append(f.name)
        if not quiet or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  {f.name}"
                  + (f"  {note}" if note and not ok else ""))
        if not quiet:
            summary = next((ln for ln in out.splitlines()
                            if "FAILURES:" in ln or "behavioural checks" in ln
                            or "problems across" in ln), "")
            if summary.strip():
                print(f"          {summary.strip()[:76]}")

    print()
    if failed:
        print(f"{len(found) - len(failed)} of {len(found)} selftests pass")
        print("failing:")
        for name in failed:
            print(f"  - {name}")
    else:
        print(f"all {len(found)} selftests pass")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())