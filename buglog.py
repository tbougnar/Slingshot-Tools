"""The fixbook: every bug we have hit, why it happened, and how it was fixed.

This is the memory that stops the same failure coming back. Each entry records
the symptom, the real cause, the change that fixed it, and a check that would
catch it next time. The builder and the debugger both read it, and entries are
marked verified once a run completes without that failure.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
BOOK = DATA / "fixbook.json"
LESSONS = DATA / "lessons.txt"

SCHEMA = ["id", "date", "symptom", "cause", "fix", "files", "detects", "verified"]


def load() -> list[dict]:
    if not BOOK.exists():
        return []
    try:
        data = json.loads(BOOK.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save(entries: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    BOOK.write_text(json.dumps(entries, indent=1), encoding="utf-8")


def record(symptom: str, cause: str, fix: str, files: list[str],
           detects: str = "", verified: bool = False) -> dict:
    entries = load()
    entry = {
        "id": f"B{len(entries) + 1:03d}",
        "date": date.today().isoformat(),
        "symptom": symptom.strip()[:300],
        "cause": cause.strip()[:300],
        "fix": fix.strip()[:400],
        "files": files[:8],
        "detects": detects.strip()[:200],
        "verified": verified,
    }
    entries.append(entry)
    save(entries)
    _append_lesson(entry)
    return entry


def verify(ids: list[str]) -> None:
    """Mark entries as holding after a clean run."""
    entries = load()
    changed = False
    for e in entries:
        if e["id"] in ids and not e.get("verified"):
            e["verified"] = True
            changed = True
    if changed:
        save(entries)


def digest(limit: int = 14) -> str:
    """Id plus symptom only. Enough to recognise a known fault, cheap to send."""
    entries = load()[-limit:]
    return "\n".join(f"{e['id']} {e['symptom'][:60]}" for e in entries)


def brief(limit: int = 14) -> str:
    """Compact form for prompts."""
    entries = load()
    if not entries:
        return "(no recorded bugs yet)"
    out = []
    for e in entries[-limit:]:
        mark = "verified" if e.get("verified") else "unverified"
        out.append(f"[{e['id']} {mark}] {e['symptom']} -> {e['fix']}")
    return "\n".join(out)


def match(text: str, limit: int = 3) -> str:
    """Fixes for entries whose symptom or files appear in this text.

    Costs nothing when nothing matches, which is the common case, so the
    builder can still read the answer to a fault it recognises without the
    whole fixbook being sent every time.
    """
    if not text:
        return ""
    t = text.lower()
    hits = []
    for e in load():
        hay = f"{e.get('symptom','')} {e.get('cause','')}".lower()
        words = [w for w in re.findall(r"[a-z']{5,}", hay)][:8]
        if words and sum(1 for w in words if w in t) >= 3:
            hits.append(f"[{e['id']}] {e['fix'][:160]}")
        if len(hits) >= limit:
            break
    return "\n".join(hits)


def open_entries() -> list[str]:
    return [e["id"] for e in load() if not e.get("verified")]


def _append_lesson(entry: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with LESSONS.open("a", encoding="utf-8") as fh:
        fh.write(f"- [{entry['id']}] {entry['symptom']} Cause: {entry['cause']} "
                 f"Fix: {entry['fix']}\n")


if __name__ == "__main__":
    for e in load():
        v = "verified" if e.get("verified") else "unverified"
        print(f"{e['id']} [{v}] {e['symptom'][:70]}")
    print(f"\n{len(load())} entries, {len(open_entries())} unverified")