"""Keep the public Discord invite alive, without a person pasting a new one.

Discord invites expire. check_links.py is right to refuse a dead one: a site
footer that sends someone to an expired invitation is worse than no link at
all. The old pipeline waited for a human to create a fresh invite and set a
variable, which meant every expiry stopped the site deploy until somebody
noticed.

The bot is already in the server and already posts in #announcements, so it can
mint its own never-expiring invite before the link check runs. One is made only
when the invite currently in use is dead, so a working link is left alone.

Nothing secret is printed. The invite itself is public by definition and is
written to GITHUB_ENV so every later step in the deploy uses the same address:
the link check, the site footer and the welcome message cannot disagree.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "DiscordBot (https://github.com/tbougnar/Slingshot-Tools, 1.0)"
API = "https://discord.com/api/v10"


def log(msg: str) -> None:
    print(f"[invite] {msg}", flush=True)


def request(url: str, method: str = "GET", token: str = "",
            body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bot {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:200]


def current_invite() -> str:
    """The invite the rest of the pipeline is about to use."""
    return (os.environ.get("DISCORD_INVITE_URL") or "").strip()


def invite_is_good(url: str) -> bool:
    m = re.search(r"discord\.gg/([A-Za-z0-9]+)", url)
    if not m:
        return False
    status, reply = request(f"{API}/invites/{m.group(1)}")
    if status != 200 or not isinstance(reply, dict):
        return False
    # A temporary invite works today and breaks next week. Refuse it now,
    # while there is still a bot here to replace it.
    guild = reply.get("guild") or {}
    return not guild.get("temporary", False)


def mint(token: str, channel: str) -> str:
    """Create one permanent invite in the server's announcements channel."""
    status, reply = request(
        f"{API}/channels/{channel}/invites", method="POST", token=token,
        body={"max_age": 0, "max_uses": 0, "temporary": False})
    if status not in (200, 201) or not isinstance(reply, dict):
        log(f"the bot could not create an invite (HTTP {status}: {reply})")
        log("give it CREATE_INVITE in #announcements, or set "
            "DISCORD_INVITE_URL to a permanent invite yourself")
        return ""
    code = str(reply.get("code") or "").strip()
    if not code:
        log("Discord accepted the request but returned no invite code")
        return ""
    return f"https://discord.gg/{code}"


def remember(url: str) -> None:
    """Share the new address with every step after this one."""
    env = os.environ.get("GITHUB_ENV", "").strip()
    if not env:
        return
    with open(env, "a", encoding="utf-8") as fh:
        fh.write(f"DISCORD_INVITE_URL={url}\n")
    log("the new invite is set for the later deploy steps")


def main() -> int:
    url = current_invite()
    if url and invite_is_good(url):
        log(f"the invite still works: {url}")
        return 0
    log("the invite is missing, expired or temporary; minting a new one")
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    channel = (os.environ.get("DISCORD_ANNOUNCEMENTS_CHANNEL_ID")
               or os.environ.get("DISCORD_CHANNEL_ID") or "").strip()
    if not token or not channel:
        log("DISCORD_BOT_TOKEN or DISCORD_ANNOUNCEMENTS_CHANNEL_ID is not set")
        return 0  # check_links.py reports the dead link; do not hide it
    fresh = mint(token, channel)
    if not fresh:
        return 0
    log(f"made a permanent invite: {fresh}")
    remember(fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
