"""Fail the build if anything private is ever tracked again.

The repository is public on purpose, because GitHub Pages serves the website
from it. So the job of this script is not to make everything private, it is to
keep three specific things out:

1. the source or the build of any paid edition
2. the company's money: revenue, margins, prices, budget
3. credentials of any kind

It also looks at the whole history once, because a file that was committed by
accident and deleted later is still readable in the log.

Run it directly, or let any workflow run it: it exits non-zero on a problem.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GITIGNORE = ROOT / ".gitignore"

# Never tracked, whatever else changes.
FORBIDDEN_PREFIXES = [
    "paid/",
    "apps/",          # full native source of the paid products
    "dist/",
    "build/",
]

FORBIDDEN_FILES = [
    ".env",
    "data/earnings.json",
    "data/prices.json",
    "data/price_log.json",
    "data/budget.json",
    "data/reputation.json",
    "data/polls.json",
    "data/discord_sent.json",
    "PATTERN_CARD.txt",
    "PATTERNS.md",
    "debug_team.py",
    "debug_team2.py",
    "seed_fixbook.py",
    "mark_verified.py",
    "groq_check.py",
    "itch_login.py",
    "paypal_check.py",
]

# Things that are public on purpose and must not trip the scanner.
ALLOWED_PREFIXES = ["site/", ".github/workflows/"]
ALLOW_SELF = "check_repo_hygiene.py"

# Secret shapes. Kept tight on purpose: a loose rule produces false alarms that
# people learn to ignore, and a check that gets ignored protects nothing.
SECRET_PATTERNS = [
    (r"github_pat_[A-Za-z0-9_]{20,}", "a GitHub fine-grained token"),
    (r"ghp_[A-Za-z0-9]{30,}", "a GitHub personal access token"),
    (r"AKIA[0-9A-Z]{16}", "an AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
    (r"\bsk-[A-Za-z0-9]{32,}", "an API secret key"),
    (r"\bgsk_[A-Za-z0-9]{20,}", "a Groq API key"),
    (r"x-access-token:[A-Za-z0-9_]{10,}@", "a token in a git remote"),
    (r"M[TIU5ODExNDA2MDE3ODgyMTI1MQ\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
     "a Discord bot token"),
    (r"\bA[A-Za-z0-9_-]{50,}\b", "a PayPal client id"),
    (r"\bEO[A-Za-z0-9_-]{50,}\b", "a PayPal secret"),
]

# Long opaque strings are only a problem in files that are not supposed to hold
# one, so the scanner skips the data files it knows are full of hashes.
SKIP_EXTENSIONS = {".png", ".ico", ".jpg", ".jpeg", ".gif", ".exe", ".zip",
                   ".woff", ".woff2", ".ttf"}


def log(msg: str) -> None:
    print(f"[hygiene] {msg}", flush=True)


def git(*args: str) -> tuple[int, str]:
    # bytes, not text: the history holds binary files whose names the console
    # encoding cannot decode, and this must not crash on them
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                       timeout=180)
    def decode(raw: bytes) -> str:
        return raw.decode("utf-8", "replace")
    return r.returncode, decode(r.stdout) + decode(r.stderr)


def tracked() -> list[str]:
    _, out = git("ls-files")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def is_allowed(path: str) -> bool:
    if path == ALLOW_SELF:
        return True
    return any(path.startswith(p) for p in ALLOWED_PREFIXES)


def check_tracked(files: list[str]) -> list[str]:
    problems = []
    for path in files:
        p = path.replace("\\", "/")
        if is_allowed(p):
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if p.startswith(prefix):
                problems.append(f"tracked but must not be: {p}")
                break
        else:
            if p in FORBIDDEN_FILES:
                problems.append(f"tracked but must not be: {p}")
                continue
            if p.endswith((".bak", ".bak2", ".bak3")):
                problems.append(f"tracked but must not be: {p} "
                                f"(stale backup)")
    return problems


def check_ignore_rules() -> list[str]:
    """Every forbidden path has to be in .gitignore, not just untracked."""
    if not GITIGNORE.exists():
        return [".gitignore is missing"]
    text = GITIGNORE.read_text(encoding="utf-8")
    problems = []
    for prefix in FORBIDDEN_PREFIXES:
        if prefix not in text:
            problems.append(f".gitignore does not mention {prefix}")
    for name in FORBIDDEN_FILES:
        base = Path(name).name
        if base not in text and name not in text:
            problems.append(f".gitignore does not mention {name}")
    return problems


def check_secrets(files: list[str]) -> list[str]:
    """Look for a credential in the content of every tracked text file."""
    problems = []
    for path in files:
        p = Path(path)
        if p.suffix.lower() in SKIP_EXTENSIONS or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, what in SECRET_PATTERNS:
            m = re.search(pattern, text)
            if m:
                line = text[:m.start()].count("\n") + 1
                problems.append(f"{path}:{line} contains {what}")
    return problems


def check_history() -> list[str]:
    """One pass over the whole log, because a deleted file is still readable."""
    code, out = git("log", "--all", "-p")
    if code != 0:
        log("could not read the history; skipping that check")
        return []
    problems = []
    for pattern, what in SECRET_PATTERNS:
        m = re.search(pattern, out)
        if m:
            problems.append(f"the git history contains {what} "
                            f"(found {m.group(0)[:16]}...)")
    return problems


def check_paid_in_site() -> list[str]:
    """The exposure guard, restated so this script stands on its own."""
    problems = []
    site_apps = ROOT / "site" / "apps"
    if not site_apps.is_dir():
        return problems
    catalog = ROOT / "site" / "apps.json"
    paid_slugs = set()
    if catalog.exists():
        try:
            import json
            for entry in json.loads(catalog.read_text(encoding="utf-8")):
                if entry.get("tier") == "full":
                    paid_slugs.add(entry.get("base_slug") or entry.get("slug"))
        except (ValueError, OSError):
            problems.append("site/apps.json could not be read")

    for d in sorted(site_apps.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if name in paid_slugs:
            problems.append(f"site/apps/{name} is a paid edition and must "
                            f"not be public")
            continue
        # anything else has to be the free edition of a product that exists,
        # or it is a leftover that has no business being public
        basic = name[:-6] if name.endswith("-basic") else None
        if basic is None or basic not in paid_slugs:
            problems.append(f"site/apps/{name} is not a known free edition "
                            f"and must not be public")
    return problems


def main() -> int:
    files = tracked()
    log(f"{len(files)} tracked files")

    problems: list[str] = []
    problems += check_tracked(files)
    problems += check_ignore_rules()
    problems += check_secrets(files)
    problems += check_paid_in_site()
    problems += check_history()

    if not problems:
        log("ok: no paid source, no business data, no credentials")
        log("    and the website holds only free editions")
        return 0

    print()
    log("PROBLEMS")
    for p in problems:
        print(f"  - {p}")
    print()
    print("  fix it with:")
    print("    git rm --cached <path>")
    print("    add it to .gitignore")
    print("  and if a credential is real, rotate it before anything else")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())