"""What the Wednesday self-improvement job is allowed to change.

The company can rewrite its own machinery, but two things stay off limits:

1. the published site itself, and the scripts that build or serve it
2. anything that moves money, or decides what gets deleted

This module is the single place those rules live, so there is no second copy to
drift out of step. ``guard_paths()`` reports a violation and exits non-zero, so
a job that ignores the rule still cannot commit the damage.
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The public site. Nothing here may be edited by an automated job: it is what
# customers actually load, and it is what GitHub Pages serves.
PROTECTED_GLOBS = [
    "site/**",
    "pages.yml",
]

# The scheduled workflows themselves. A job that could edit its own schedule
# could raise its own budget, drop a guard step, or run the publish path by
# hand, so they are protected exactly like the site.
PROTECTED_WORKFLOWS = [
    "pages.yml",
    "monday-vote.yml",
    "wednesday-review.yml",
    "friday-build.yml",
    "friday-verify.yml",
]

# The scripts that make the site work. Editing these changes what customers get
# without touching site/, so they are protected too.
SITE_SCRIPTS = [
    "check_exposure.py",
    "build_exe.py",
    "build_installer_app.py",
    "build_paid_only.py",
]

# Money, and deletion. Both need a human decision, not a model.
MONEY_AND_DEATH = [
    "site/apps.json",       # prices, what is for sale, and where it is sold
    "pricing.py",           # price movement
    "retire_product.py",    # taking a product down
    "publish_paid.py",      # putting a product on sale
    "set_itch_url.py",      # where a product is sold
]

# The generator and its QA stack: the part the company may freely improve.
SELF_IMPROVABLE = [
    "make_app.py",
    "stage_app.py",
    "verify_app.py",
    "qa_loop.py",
    "app_scanner.py",
    "patcher.py",
    "selfheal.py",
    "sizeguard.py",
    "tokenmeter.py",
    "providers.py",
    "learn.py",
    "log_lesson.py",
    "selftest*.py",
    "budget.py",
    "weekly_guard.py",
    "reputation.py",
    "data/fixbook.json",
    "data/fixbook.md",
]

# A product cannot be taken down until it has been ignored this long, and the
# evidence has to say it will never sell.
RETIRE_MIN_DAYS = 365


def protected_globs() -> list[str]:
    return (PROTECTED_GLOBS
            + [f".github/workflows/{n}" for n in PROTECTED_WORKFLOWS]
            + SITE_SCRIPTS)


def all_protected() -> set[str]:
    """Every protected path that exists, as repo-relative posix paths."""
    out: set[str] = set()
    for pattern in protected_globs():
        # a bare "site/**" makes glob return the directory, not the files
        probe = pattern[:-3] if pattern.endswith("/**") else pattern
        for p in ROOT.glob(probe):
            if p.is_file():
                out.add(p.relative_to(ROOT).as_posix())
            elif p.is_dir():
                for child in p.rglob("*"):
                    if child.is_file():
                        out.add(child.relative_to(ROOT).as_posix())
    return out


def changed_files(base: str = "HEAD", head: str = "HEAD") -> list[str]:
    """Files this working tree differs in, newest first."""
    args = ["diff", "--name-only", f"{base}...{head}"]
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        r = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                           cwd=ROOT, capture_output=True, text=True,
                           timeout=60)
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def is_protected(path: str) -> bool:
    """True when an automated job must not edit this path."""
    # normalize separators, and drop a leading "./" but keep the dot in
    # ".github", which str.lstrip would eat
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p in MONEY_AND_DEATH:
        return True
    for pattern in protected_globs():
        if fnmatch.fnmatch(p, pattern):
            return True
        # site/** has to cover everything under site/, not just one level
        if pattern.endswith("/**") and p.startswith(pattern[:-2]):
            return True
    return False


def violations(paths: list[str]) -> list[str]:
    """Which of these paths the learn job is not allowed to touch."""
    return [p for p in paths if is_protected(p)]


def uncommitted(paths: list[str]) -> list[str]:
    """Protected files that differ from HEAD right now."""
    out = []
    for p in paths:
        if not is_protected(p):
            continue
        r = subprocess.run(["git", "status", "--porcelain", "--", p],
                           cwd=ROOT, capture_output=True, text=True,
                           timeout=30)
        if r.stdout.strip():
            out.append(p)
    return out


def guard(paths: list[str] | None = None) -> int:
    """Refuse to go on if a protected file was modified. 0 means it is fine."""
    paths = paths if paths is not None else changed_files()
    bad = violations(paths)
    if not bad:
        print(f"[guard] ok: {len(paths)} changed file(s), none protected")
        return 0

    print("[guard] REFUSING: the learn job changed protected files:")
    for p in bad:
        why = ("the public site" if p.startswith("site/")
               else "money or deletion" if p in MONEY_AND_DEATH
               else "a script that makes the site work")
        print(f"  - {p}  ({why})")
    print()
    print("[guard] revert them with:")
    for p in bad:
        print(f"  git checkout -- {p}")
    return 1


def main() -> int:
    """Print the rule set, or check a change set."""
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return guard()
    if len(sys.argv) > 1 and sys.argv[1] == "uncommitted":
        bad = uncommitted(changed_files())
        if bad:
            print("[guard] protected files are modified but not committed:")
            for p in bad:
                print(f"  - {p}")
            return 1
        print("[guard] ok: no protected file is dirty")
        return 0

    print("PROTECTED (never edited by an automated job)")
    for p in PROTECTED_GLOBS:
        print(f"  {p}")
    for p in SITE_SCRIPTS:
        print(f"  {p}")
    print()
    print("MONEY AND DELETION (never edited by an automated job)")
    for p in MONEY_AND_DEATH:
        print(f"  {p}")
    print()
    print("SELF-IMPROVABLE (the company may rewrite these)")
    for p in SELF_IMPROVABLE:
        print(f"  {p}")
    print()
    print(f"A product cannot be retired until it has been ignored for "
          f"{RETIRE_MIN_DAYS} days.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())