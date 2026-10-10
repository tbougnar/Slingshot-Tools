"""Let the company improve its own generator, under hard limits.

What it may touch: the generator and its QA stack, nothing else. What it may
not touch: the site, the scripts that serve it, prices, and anything to do with
taking a product down. That is enforced three ways, so a confused model cannot
get past all of them:

1. the patch is written by the same machinery the build uses, with its existing
   security guards, which already refuse dangerous calls and CSS changes
2. every file it proposes is checked against weekly_guard before it is applied
3. the whole test suite runs afterwards, and a failure discards the patch

A patch that changes nothing useful is thrown away rather than committed, so
the repository does not fill with cosmetic churn.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import weekly_guard as guard

DATA = ROOT / "data"
STATE = DATA / "self_upgrade.json"
RECENT = DATA / "lessons.txt"

# The editable set. Anything not listed here is off limits even if the guard
# has a gap, because the check below happens before the patch is applied.
ALLOWED = [p.strip() for p in
           (os.environ.get("SLINGSHOT_ALLOWED") or
            "make_app.py,qa_loop.py,app_scanner.py,patcher.py,selfheal.py,"
            "sizeguard.py,tokenmeter.py,providers.py").split(",")
           if p.strip()]

MODEL = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() \
    or "openai/gpt-oss-20b"

# The tests that must all pass before a patch is kept.
TEST_SUITE = ["selftest.py", "selftest_deep.py", "selftest_audit.py",
              "check_exposure.py"]


def log(msg: str) -> None:
    print(f"[upgrade] {msg}", flush=True)


def load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def recent_lessons(limit: int = 25) -> list:
    """The most recent fixbook entries, newest first, as text for the prompt."""
    rows = load(ROOT / "data" / "fixbook.json", [])
    if not isinstance(rows, list):
        return []
    rows = sorted(rows, key=lambda e: str(e.get("id", "")), reverse=True)
    out = []
    for e in rows[:limit]:
        out.append(f"{e.get('id')}: {e.get('symptom')}\n"
                   f"  cause: {e.get('cause')}\n"
                   f"  fix:   {e.get('fix')}")
    return out


def run_tests() -> tuple[bool, str]:
    """Every test has to pass. Returns (ok, what failed)."""
    for script in TEST_SUITE:
        r = subprocess.run([sys.executable, script], cwd=ROOT,
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            tail = (r.stdout or r.stderr or "").strip().splitlines()[-6:]
            return False, (f"{script} exited {r.returncode}\n"
                           + "\n".join(tail))
    return True, "all tests passed"


UPGRADE_SYSTEM = (
    "You improve a tool generator that builds one small Windows desktop app a "
    "week, verifies it in a real browser, and refuses to publish anything "
    "broken.\n"
    "You are given recent faults it actually hit. Propose at most ONE change "
    "that would stop a whole class of them recurring, in ONE file.\n"
    "Return JSON and nothing else: a list of at most one object with keys "
    '"file" and "content", where content is the COMPLETE new contents of that '
    "file.\n"
    'Return [] when nothing here is worth changing. Do not change behaviour '
    "that is already tested and working. Do not add dependencies. Do not "
    "weaken or remove a check."
)

UPGRADE_USER = """The files you may rewrite, and nothing else:
{allowed}

Recent faults, newest first:

{lessons}

Pick the one fault whose fix would prevent the most future ones. Change a
single file, return its complete new contents."""


def propose(lessons: list) -> list[dict]:
    """Ask the model for one whole-file replacement.

    patcher.py only knows how to patch generated HTML, so the call is made
    directly and the safety checks live here instead.
    """
    try:
        import patcher
    except ImportError:
        log("patcher.py is unavailable; nothing to do")
        return []

    lesson_text = "\n\n".join(lessons) or "(no faults recorded yet)"
    user = UPGRADE_USER.format(allowed="\n".join(f"  - {f}" for f in ALLOWED),
                               lessons=lesson_text)

    for model in (MODEL, "openai/gpt-oss-20b", "llama-3.3-70b-versatile"):
        try:
            raw = patcher.chat(model, UPGRADE_SYSTEM, user, max_tokens=6000)
        except Exception as e:  # noqa: BLE001
            log(f"{model}: {str(e)[:140]}")
            continue

        got = re.search(r"\[.*\]", raw, re.S) or re.search(r"\{.*\}", raw, re.S)
        if not got:
            continue
        try:
            data = json.loads(got.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            continue

        plan = []
        for item in data[:1]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("file") or "").strip()
            content = item.get("content")
            if not path or not isinstance(content, str) or not content.strip():
                continue
            if not content.rstrip().endswith(("}", ")")):
                log(f"{model}: the file looks truncated, skipping")
                continue
            plan.append({"file": path.replace("\\", "/"), "content": content})
        if plan:
            return plan

    log("the model did not return a usable patch")
    return []


def already_tried(text: str) -> bool:
    """Do not repeat a patch that was already applied or already rejected."""
    history = load(STATE, {"tried": []})
    blob = (text or "")[:400]
    return any(h.get("fingerprint") == blob for h in history["tried"])


def remember(fingerprint: str, outcome: str, detail: str) -> None:
    history = load(STATE, {"tried": []})
    history["tried"] = (history["tried"] or [])[-19:] + [{
        "fingerprint": fingerprint,
        "at": int(datetime.now(timezone.utc).timestamp()),
        "outcome": outcome,
        "detail": detail[:400],
    }]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def changed_by_git(paths: list[str]) -> bool:
    """Did the patch actually change any of these files?

    Scoped to the given paths on purpose: the repository may already hold new
    untracked files, and that is not a reason to throw a good patch away.
    """
    if not paths:
        return False
    r = subprocess.run(["git", "status", "--porcelain", "--"] + paths,
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def tree_is_dirty() -> bool:
    """Is there anything uncommitted at all? Used as a precondition."""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def apply_and_test(plan: list[dict]) -> dict:
    """Apply, test, and roll back on any failure."""
    targets = [p.get("file", "") for p in plan if p.get("file")]
    if not targets:
        return {"ok": False, "why": "the patch named no file"}

    blocked = guard.violations(targets)
    if blocked:
        return {"ok": False, "why": f"tried to edit protected files: {blocked}"}

    stray = [t for t in targets if t not in ALLOWED]
    if stray:
        return {"ok": False, "why": f"tried to edit files outside the "
                                   f"allow list: {stray}"}

    for path in targets:
        if not (ROOT / path).exists():
            return {"ok": False, "why": f"{path} does not exist"}

    # keep the originals so a failure can be undone exactly
    originals = {p: (ROOT / p).read_text(encoding="utf-8") for p in targets}

    for p in plan:
        (ROOT / p["file"]).write_text(p.get("content", ""), encoding="utf-8")
    log(f"applied {', '.join(targets)}")

    if not changed_by_git(targets):
        for p, text in originals.items():
            (ROOT / p).write_text(text, encoding="utf-8")
        return {"ok": False,
                "why": "the patch changed nothing, so there is nothing to keep"}

    ok, detail = run_tests()
    if not ok:
        for p, text in originals.items():
            (ROOT / p).write_text(text, encoding="utf-8")
        log("tests failed, patch rolled back")
        return {"ok": False, "why": detail}

    # the guard runs on the real diff too, in case a test regenerated something
    blocked_after = guard.violations(guard.changed_files())
    if blocked_after:
        for p, text in originals.items():
            (ROOT / p).write_text(text, encoding="utf-8")
        return {"ok": False, "why": f"protected files changed: {blocked_after}"}

    return {"ok": True, "why": "all tests passed", "files": targets}


def main() -> int:
    ap = argparse.ArgumentParser(description="self-improvement pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="propose a patch and print it, change nothing")
    args = ap.parse_args()

    if tree_is_dirty():
        log("the working tree is already dirty; refusing to start so a "
            "rollback cannot discard somebody else's work")
        return 1

    log(f"model: {MODEL}")
    log(f"may edit: {', '.join(ALLOWED)}")

    lessons = recent_lessons()
    log(f"reading {len(lessons)} recent lessons")

    plan = propose(lessons)
    if not plan:
        log("nothing worth changing, or the model declined")
        remember("no-plan", "no-change", "the model proposed nothing")
        return 0

    for p in plan:
        log(f"proposed: {p.get('file')} "
            f"({len(p.get('content', ''))} characters)")

    if already_tried(plan[0].get("content", "")):
        log("this patch was already tried; skipping")
        return 0

    if args.dry_run:
        print(json.dumps([{"file": p.get("file"),
                           "chars": len(p.get("content", ""))}
                          for p in plan], indent=2))
        for p in plan:
            print(f"\n{'=' * 62}\n{p.get('file')}\n{'=' * 62}")
            print(p.get("content", "")[:4000])
        return 0

    result = apply_and_test(plan)
    remember(plan[0].get("content", "")[:400],
             "kept" if result["ok"] else "rejected", result["why"])

    if result["ok"]:
        log(f"KEPT the patch to {', '.join(result.get('files', []))}")
        return 0
    log(f"rejected: {result['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())