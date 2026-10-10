"""Posting to Discord, one place for every script.

Two ways in, tried in order:

1. a webhook (``DISCORD_WEBHOOK_URL``), which needs no bot token at all
2. the bot token plus a channel name, which is what the pipeline has

Both write the same payload, so a message looks identical whichever way it
went out. Nothing here ever raises: Discord being unreachable must not stop a
release, so every failure is logged and reported as False.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
TIMEOUT = 30

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

SITE_URL = "https://tbougnar.github.io/Slingshot-Tools"
BRAND = 0xC1272D
OK = 0x2ECC71

# the channels this project owns, by name
CHANNELS = {
    "announcements": os.environ.get("DISCORD_ANNOUNCEMENTS_CHANNEL_ID", "").strip(),
    "polls": os.environ.get("DISCORD_POLL_WEBHOOK_URL", "").strip(),
    "results": os.environ.get("DISCORD_RESULTS_WEBHOOK_URL", "").strip(),
    "articles": os.environ.get("DISCORD_ARTICLES_CHANNEL_ID", "").strip(),
}


def log(msg: str) -> None:
    print(f"[discord] {msg}", flush=True)


def avatar() -> str:
    return f"{SITE_URL}/icon-512.png"


def embed_message(embed: dict, username: str = "Slingshot Tools") -> dict:
    """Wrap an embed in the shape both transports accept."""
    return {
        "username": username,
        "avatar_url": avatar(),
        "embeds": [embed],
        # never ping anybody from an automated post
        "allowed_mentions": {"parse": []},
    }


# ------------------------------------------------------------------ webhook

def post_webhook(url: str, payload: dict) -> bool:
    if not url:
        return False
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "slingshot-tools/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        log(f"discord rejected the webhook message: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        log(f"discord webhook unreachable: {e}")
    return False


# ---------------------------------------------------------------- bot token

def _rest(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """One REST call, synchronous, so callers do not need an event loop."""
    import urllib.request as ur

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = ur.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Bot {TOKEN}",
                 "Content-Type": "application/json",
                 "User-Agent": "slingshot-tools/1.0"})
    try:
        with ur.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read().decode("utf-8")
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:  # noqa: BLE001
        log(f"discord unreachable: {e}")
        return 0, str(e)[:200]


def find_channel(name: str) -> str | None:
    """The channel id for a name, preferring an explicit id from the env."""
    explicit = CHANNELS.get(name, "").strip()
    if explicit and explicit.isdigit():
        return explicit
    if not TOKEN or not GUILD_ID:
        return None

    st, data = _rest("GET", f"/guilds/{GUILD_ID}/channels")
    if st != 200 or not isinstance(data, list):
        return None
    for c in data:
        if c.get("name") == name and c.get("type") in (0, 5):
            return c["id"]
    return None


def post_channel(name: str, payload: dict) -> bool:
    """Post through the bot, resolving the channel by name."""
    if not TOKEN:
        log(f"no bot token, cannot post to #{name}")
        return False
    cid = find_channel(name)
    if not cid:
        log(f"channel #{name} not found in the server")
        return False
    st, data = _rest("POST", f"/channels/{cid}/messages", payload)
    if st in (200, 201):
        return True
    log(f"discord rejected the message in #{name}: HTTP {st} {data}")
    return False


def post(name: str, payload: dict, webhook: str = "") -> bool:
    """Send to a channel by name, falling back between webhook and bot.

    ``webhook`` overrides the default webhook for this channel, for the poll
    and result webhooks that may be set separately.
    """
    target = webhook or (CHANNELS.get(name, "").strip() if name in CHANNELS
                         else "") or WEBHOOK
    if target.startswith("https://"):
        if post_webhook(target, payload):
            return True
        log("webhook post failed, trying the bot instead")

    if post_channel(name, payload):
        return True

    if target.startswith("https://") or not TOKEN:
        return False
    return False


def available() -> bool:
    """True when there is some way to reach Discord."""
    return bool(WEBHOOK or (TOKEN and GUILD_ID))


def describe() -> str:
    """Which transport is configured, for the startup log."""
    if WEBHOOK:
        return "webhook"
    if TOKEN and GUILD_ID:
        return "bot token"
    return "nothing configured"