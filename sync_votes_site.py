"""Sync the public site votes file from current poll state.

The website reads site/votes.json. This keeps it aligned with the latest open
(or most recent) ballot so vote percentages stay current.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
SITE = ROOT / "site"
POLLS = DATA / "polls.json"
OUT = SITE / "votes.json"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _pick_poll(polls: dict) -> dict | None:
    if not isinstance(polls, dict):
        return None
    items = [p for p in polls.values() if isinstance(p, dict)]
    if not items:
        return None
    open_polls = [p for p in items if p.get("status") == "open"]
    pool = open_polls or items
    pool.sort(key=lambda p: (p.get("created") or 0, str(p.get("id") or "")))
    return pool[-1]


def build_votes() -> dict:
    try:
        import discord_data as dd
        poll = dd.open_poll() or _pick_poll(load_json(POLLS, {}))
    except Exception:
        poll = _pick_poll(load_json(POLLS, {}))
    if not poll:
        return {"poll": None}

    options = []
    for opt in (poll.get("options") or []):
        if not isinstance(opt, dict):
            continue
        label = str(opt.get("label") or "").strip()
        if not label:
            continue
        if "votes" in opt:
            try:
                votes = int(opt.get("votes") or 0)
            except Exception:
                votes = 0
        elif isinstance(opt.get("voters"), list):
            votes = len(opt.get("voters") or [])
        else:
            votes = 0
        options.append({"label": label, "votes": max(0, votes)})

    # If we have a live Discord-configured tally path, prefer it for open polls.
    try:
        if poll.get("status") == "open":
            import discord_tally as dt
            counts = dt.collect(poll.get("id", ""), poll.get("options", []), poll.get("message_id", ""))
            if counts:
                options = [{"label": o["label"], "votes": int(counts.get(o["label"], o["votes"]))} for o in options]
    except Exception:
        pass

    return {
        "poll": {
            "id": poll.get("id"),
            "question": poll.get("question") or "What should Slingshot Tools build next week?",
            "options": options,
            "status": poll.get("status"),
        }
    }


def main() -> int:
    data = build_votes()
    save_json(OUT, data)
    poll = data.get("poll") or {}
    total = sum(int(o.get("votes") or 0) for o in (poll.get("options") or []))
    print(f"[votes] synced site/votes.json ({poll.get('id') or 'no poll'}, {total} vote(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
