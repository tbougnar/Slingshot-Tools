"""Record a lesson in data/fixbook.json and rebuild the readable copies.

Usage:
    python log_lesson.py --symptom "..." --cause "..." --fix "..." \
        --files a.py b.py --detects "..." [--verified]

Lessons are appended with the next free B0NN id. Existing entries are left
alone, so this is safe to re-run after editing an older entry by hand.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
JSON_PATH = DATA / "fixbook.json"
MD_PATH = DATA / "fixbook.md"
TXT_PATH = DATA / "lessons.txt"


def load() -> list[dict]:
    if JSON_PATH.exists():
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return []


def next_id(entries: list[dict]) -> str:
    used = []
    for e in entries:
        bid = str(e.get("id", ""))
        if bid.startswith("B") and bid[1:].isdigit():
            used.append(int(bid[1:]))
    return f"B{max(used, default=0) + 1:03d}"


def write_json(entries: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def write_md(entries: list[dict]) -> None:
    lines = ["# Fixbook", "",
             "One entry per bug that actually happened. Newest last.", ""]
    for e in entries:
        lines.append(f"## {e.get('id')} - {e.get('symptom', '')}")
        lines.append("")
        lines.append(f"- **Date:** {e.get('date', '')}")
        lines.append(f"- **Cause:** {e.get('cause', '')}")
        lines.append(f"- **Fix:** {e.get('fix', '')}")
        files = e.get("files") or []
        if files:
            lines.append(f"- **Files:** {', '.join(files)}")
        if e.get("detects"):
            lines.append(f"- **Detects:** {e['detects']}")
        lines.append(f"- **Verified:** "
                     f"{'yes' if e.get('verified') else 'no'}")
        lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_txt(entries: list[dict]) -> None:
    """A compact version the generator can read into its prompt."""
    out = []
    for e in entries:
        out.append(f"{e.get('id')}: {e.get('symptom', '')}")
        out.append(f"  cause: {e.get('cause', '')}")
        out.append(f"  fix:   {e.get('fix', '')}")
        for f in e.get("files") or []:
            out.append(f"  file:  {f}")
        out.append("")
    TXT_PATH.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Append a lesson to the fixbook")
    ap.add_argument("--symptom", required=True)
    ap.add_argument("--cause", required=True)
    ap.add_argument("--fix", required=True)
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--detects", default="")
    ap.add_argument("--verified", action="store_true")
    args = ap.parse_args()

    entries = load()
    entry = {
        "id": next_id(entries),
        "date": date.today().isoformat(),
        "symptom": args.symptom,
        "cause": args.cause,
        "fix": args.fix,
        "files": args.files,
        "detects": args.detects,
        "verified": bool(args.verified),
    }
    entries.append(entry)
    write_json(entries)
    write_md(entries)
    write_txt(entries)

    print(f"recorded {entry['id']} ({len(entries)} total)")
    print(f"  data/fixbook.json")
    print(f"  data/fixbook.md")
    print(f"  data/lessons.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())