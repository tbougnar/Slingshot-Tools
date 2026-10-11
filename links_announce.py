"""Post the welcome message, carrying every platform link, into #announcements.

Run by hand when the links change, and by the deploy step so the Discord
server and the site never name different addresses:

    python links_announce.py          post it
    python links_announce.py --check  show what would be posted

Uses the webhook, which needs no bot permissions and keeps working while
Discord's own API is having a bad day.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import links

ROOT = Path(__file__).resolve().parent
CHANNEL = "announcements"


def log(m: str) -> None:
    print(f"[post] {m}", flush=True)


def main() -> int:
    body = links.discord_welcome()

    if "--check" in sys.argv:
        print(body)
        return 0

    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not hook:
        log("no DISCORD_WEBHOOK_URL, so nothing was posted")
        log("gh secret set DISCORD_WEBHOOK_URL --repo tbougnar/Slingshot-Tools")
        return 1

    try:
        import discord_post as dp
    except ImportError as e:
        log(f"discord_post could not be imported: {e}")
        return 1

    payload = dp.embed_message({
        "title": "Everything is here, and everything links to everything",
        "description": body,
        "color": 0xD6582E,
        "footer": {"text": "slingshot.tools"},
    })

    if dp.post(CHANNEL, payload, webhook=hook):
        log("posted")
        return 0
    log("the post did not send; the bot path may still have tried")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())