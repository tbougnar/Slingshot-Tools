"""What the pipeline needs on a runner that this repository does not ship.

Answers the question the Friday failure asked one file at a time: simulate a
clean checkout, then ask every test and every workflow whether it can run.

The only honest way to do that is to copy what git actually tracks into a fresh
directory and run the suite there. Anything that survives on this machine and
dies there is a file the pipeline needs and does not have.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from testenv import clean_env

ROOT = Path(__file__).resolve().parent

CHECKS = [
    ("imports every module the pipeline uses",
     "python -c \"import qa_loop, verify_app, mark_verified, debug_team,"
     " make_app, build_paid_only, stage_app, build_exe, build_installer_app,"
     " itch_publish, signals, goals\""),
    ("the main selftest", "python selftest.py"),
    ("the deep selftest", "python selftest_deep.py"),
    ("the audit", "python selftest_audit.py"),
    ("the tracked-module check", "python tracked_selftest.py"),
    ("the exposure check", "python check_exposure.py"),
    ("the links check", "python check_links.py"),
    ("every selftest runs", "python run_selftests.py"),
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cleanroom-"))
    print(f"building a clean checkout in {tmp}\n")

    # exactly what a runner gets
    r = subprocess.run(["git", "ls-files"], cwd=str(ROOT), env=clean_env(),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        # An empty listing is not an empty repository; it is a broken command.
        # Continuing made every later check fail with "file not in repository",
        # which sends the reader after the wrong fault.
        print(f"git ls-files failed rc={r.returncode}: {(r.stderr or '')[:300]}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2
    for line in r.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    r = subprocess.run(["git", "submodule", "status"], cwd=str(ROOT),
                       env=clean_env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"git submodule status failed rc={r.returncode}: "
              f"{(r.stderr or '')[:300]}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2
    print(f"{len(r.stdout.splitlines())} submodules\n")

    bad = 0
    for label, cmd in CHECKS:
        p = subprocess.run(cmd, cwd=str(tmp), capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=clean_env(), shell=True, timeout=900)
        if p.returncode == 0:
            print(f"  ok    {label}")
        else:
            bad += 1
            tail = [ln for ln in (p.stdout or p.stderr or "").splitlines()
                    if ln.strip()][-3:]
            print(f"  BROKEN {label}")
            for ln in tail:
                print(f"          {ln.strip()[:88]}")

    print()
    if bad:
        print(f"{bad} of {len(CHECKS)} checks cannot pass on a clean checkout.")
        print("A file the pipeline needs is not in the repository.")
    else:
        print(f"all {len(CHECKS)} checks pass on a clean checkout.")
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
