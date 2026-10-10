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

# the channels this project owns, by plain name. An explicit id always wins.
CHANNELS = {
    "announcements": os.environ.get("DISCORD_ANNOUNCEMENTS_CHANNEL_ID", "").strip(),
    "polls": os.environ.get("DISCORD_POLLS_CHANNEL_ID", "").strip(),
    "results": os.environ.get("DISCORD_RESULTS_CHANNEL_ID", "").strip(),
    "articles": os.environ.get("DISCORD_ARTICLES_CHANNEL_ID", "").strip(),
    "store": os.environ.get("DISCORD_STORE_CHANNEL_ID", "").strip(),
    "roadmap": os.environ.get("DISCORD_ROADMAP_CHANNEL_ID", "").strip(),
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


def strip_emoji(name: str) -> str:
    """Drop a leading emoji and separator.

    "\U0001f6e0\ufe0f-tools" -> "tools", "\U0001f5f3\ufe0f-polls" -> "polls".

    Done by code point rather than from a list of prefixes, so a channel whose
    emoji is changed later is still found.
    """
    text = (name or "").strip()
    while text:
        head = text[0]
        # emoji live above the BMP, plus the variation and joiner selectors
        if ord(head) > 0x2000 or head in "\ufe0f\u200d":
            text = text[1:].lstrip()
            continue
        break
    return text.lstrip("-_ ").strip()


def find_channel(name: str) -> str | None:
    """The channel id for a name, preferring an explicit id from the env.

    Channels are named with an emoji prefix, so matching is done on the plain
    part as well. Renaming a channel for looks must not silently stop the
    announcements.
    """
    explicit = CHANNELS.get(name, "").strip()
    if explicit and explicit.isdigit():
        return explicit
    if not TOKEN or not GUILD_ID:
        return None

    st, data = _rest("GET", f"/guilds/{GUILD_ID}/channels")
    if st != 200 or not isinstance(data, list):
        return None

    text = [c for c in data if c.get("type") in (0, 5)]

    # an exact match wins, so a channel called "tools" beats "my-tools"
    for c in text:
        if c.get("name") == name:
            return c["id"]
    # then the same name once the emoji prefix is taken off
    wanted = name.lower()
    for c in text:
        if strip_emoji(c.get("name", "")).lower() == wanted:
            return c["id"]
    return None


def messages(channel: str, limit: int = 100) -> list:
    """Recent messages in a channel, newest first.

    This is how a ballot collects votes without anybody having to keep a bot
    running: members reply to the ballot message, and Friday reads the replies
    through the REST API.
    """
    if not TOKEN or not GUILD_ID:
        return []
    cid = find_channel(channel)
    if not cid:
        return []
    st, data = _rest("GET", f"/channels/{cid}/messages?limit={int(limit)}")
    return data if st == 200 and isinstance(data, list) else []


def find_message(channel: str, needle: str = "") -> str | None:
    """The id of the most recent message in a channel.

    A webhook returns no message id, so a ballot posted that way still has to
    be found again before its replies can be counted. ``needle`` narrows the
    search to messages whose content or embeds hold that text.
    """
    for m in messages(channel, 50):
        if not needle:
            return m.get("id")
        blob = (m.get("content") or "") + json.dumps(m.get("embeds") or [])
        if needle.lower() in blob.lower():
            return m.get("id")
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