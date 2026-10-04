"""Write the fixbook as a plain file every model reads.

Generated from data/fixbook.json so the recorded bugs and this file can never
drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buglog

OUT = buglog.DATA / "fixbook.md"


def render() -> str:
    entries = buglog.load()
    out = [
        "# Fixbook",
        "",
        "Every fault we have hit in this pipeline, what actually caused it, and",
        "the change that fixed it. Check here before proposing anything.",
        "",
    ]
    if not entries:
        out.append("_Nothing recorded yet._")
        return "\n".join(out) + "\n"
    for e in entries:
        state = "PROVEN" if e.get("verified") else "UNTESTED"
        out += [
            f"## {e['id']} - {e['symptom']}",
            "",
            f"- **Cause:** {e.get('cause','')}",
            f"- **Fix:** {e.get('fix','')}",
            f"- **Files:** {', '.join(e.get('files', [])) or '-'}",
            f"- **Check for recurrence:** {e.get('detects','')}",
            f"- **Status:** {state}",
            "",
        ]
    out += [
        "## How to use this",
        "",
        "1. If the symptom matches an entry, use that fix. Do not invent a new one.",
        "2. If it does not match, treat it as new: diagnose it, then record it with",
        "   `buglog.record(symptom, cause, fix, files, detects)` so it is here next time.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({len(buglog.load())} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())