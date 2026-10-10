"""Post the Short's link to Discord, or say plainly that nothing went up.

Announcements run on success and on failure, because a silent pipeline is
indistinguishable from a working one. The message names which step stopped.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import discord_post as dp

ROOT = Path(__file__).resolve().parent


def log(m: str) -> None:
    print(f"[announce] {m}", flush=True)


def read(name: str) -> dict | None:
    p = ROOT / "data" / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> int:
    script = read("shorts_script.json")
    if not script:
        log("no script, so there is nothing to announce")
        return 0

    done = read("shorts_published.json")
    video = read("shorts_video.json")

    name = script.get("name") or "A new tool"
    price = script.get("price") or ""
    secs = (video or {}).get("seconds")

    if done and done.get("id"):
        fields = [
            {"name": "Price", "value": str(price), "inline": True},
            {"name": "Length", "value": f"{secs:.0f}s", "inline": True}
            if secs else {"name": "Length", "value": "?", "inline": True},
            {"name": "Channel", "value": "Short", "inline": True},
        ]
        payload = dp.embed_message({
            "title": f"New Short: {name}",
            "url": done.get("url", ""),
            "description": (script.get("blurb") or "")[:900],
            "fields": fields,
            "color": 0xD6582E,
            "footer": {"text": "slingshot.tools"},
        })
        ok = dp.post("announcements", payload)
        log("announced" if ok else "the announcement did not send")
        return 0

    # nothing published: say what stage it reached, so the failure is legible
    stage = "rendered" if video else "no video"
    payload = dp.embed_message({
        "title": f"Short not published: {name}",
        "description": f"{stage}. The pipeline will not retry on its own.\n"
                       f"Run **Shorts — publish the Short** by hand to "
                       f"try again.",
        "color": 0x9B3A2E,
        "footer": {"text": "slingshot.tools"},
    })
    dp.post("announcements", payload)
    log(f"announced that the run stopped at: {stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())