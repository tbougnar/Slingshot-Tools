"""Keep the public Discord invite alive, without a person pasting a new one.

Discord invites expire. check_links.py is right to refuse a dead one: a site
footer that sends someone to an expired invitation is worse than no link at
all. The old pipeline waited for a human to create a fresh invite and set a
variable, which meant every expiry stopped the site deploy until somebody
noticed.

The bot is already in the server and already posts in #announcements, so it can
mint its own never-expiring invite before the link check runs. One is made only
when the invite currently in use is dead, so a working link is left alone. If
the bot cannot create an invite in the announcements channel, it tries every
other text channel it can see before giving up.

Nothing secret is printed. The invite itself is public by definition and is
written to GITHUB_ENV so every later step in the deploy uses the same address:
the link check, the site footer and the welcome message cannot disagree. The
repository variable is updated too, so the next run starts with the good link.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

UA = "DiscordBot (https://github.com/tbougnar/Slingshot-Tools, 1.0)"
API = "https://discord.com/api/v10"
GH_API = "https://api.github.com"


def log(msg: str) -> None:
    print(f"[invite] {msg}", flush=True)


def request(url: str, method: str = "GET", token: str = "",
            body: dict | None = None, scheme: str = "Bot",
            accept: str = "application/json") -> tuple[int, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": UA, "Accept": accept}
    if token:
        headers["Authorization"] = f"{scheme} {token}"
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


def candidate_channels(token: str) -> list[str]:
    """Channel ids to try, best first, using only what the bot already knows.

    A dedicated announcements id wins. Otherwise the guild id, already a
    secret for the connection check, lets us list the channels and prefer the
    obvious public ones. We never hard-code channel ids in a public repo.
    """
    result: list[str] = []
    for key in ("DISCORD_ANNOUNCEMENTS_CHANNEL_ID", "DISCORD_CHANNEL_ID"):
        value = (os.environ.get(key) or "").strip()
        if value.isdigit() and value not in result:
            result.append(value)

    guild = (os.environ.get("DISCORD_GUILD_ID") or "").strip()
    if token and guild.isdigit():
        status, data = request(f"{API}/guilds/{guild}/channels", token=token)
        if status == 200 and isinstance(data, list):
            text = [c for c in data if c.get("type") in (0, 5)]
            text.sort(key=lambda c: (
                0 if "announce" in c.get("name", "").lower() else
                1 if "welcome" in c.get("name", "").lower() else
                2 if "general" in c.get("name", "").lower() else 3,
                c.get("name", "")))
            for channel in text:
                cid = str(channel.get("id") or "")
                if cid.isdigit() and cid not in result:
                    result.append(cid)
    return result


def mint(token: str, channel: str) -> str:
    """Create one permanent invite in a channel the bot can reach."""
    status, reply = request(
        f"{API}/channels/{channel}/invites", method="POST", token=token,
        body={"max_age": 0, "max_uses": 0, "temporary": False})
    if status not in (200, 201) or not isinstance(reply, dict):
        log(f"channel {channel} could not create an invite "
            f"(HTTP {status}: {reply})")
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


def save_variable(url: str) -> None:
    """Persist the good invite so the next workflow does not start stale.

    The invite is public; the token used here is the short-lived GITHUB_TOKEN
    and is never printed. A missing variable is created; an existing one is
    updated. Failure is stated, not hidden, but it does not break this deploy
    because GITHUB_ENV already fixed the current job.
    """
    token = (os.environ.get("GH_TOKEN")
             or os.environ.get("GITHUB_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo or "/" not in repo:
        return
    name = "DISCORD_INVITE_URL"
    base = f"{GH_API}/repos/{repo}/actions/variables"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    status, reply = request(f"{base}/{name}", method="PATCH", token=token,
                            body={"value": url}, scheme="Bearer",
                            accept=headers["Accept"])
    if status in (200, 204):
        log("the repository variable now holds the working invite")
        return
    if status != 404:
        log(f"could not update the repository variable (HTTP {status}: {reply})")
        return
    status, reply = request(base, method="POST", token=token,
                            body={"name": name, "value": url},
                            scheme="Bearer", accept=headers["Accept"])
    if status in (200, 201, 204):
        log("the repository variable now holds the working invite")
    else:
        log(f"could not create the repository variable (HTTP {status}: {reply})")


def main() -> int:
    url = current_invite()
    if url and invite_is_good(url):
        log(f"the invite still works: {url}")
        return 0
    log("the invite is missing, expired or temporary; minting a new one")
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        log("DISCORD_BOT_TOKEN is not set")
        return 0  # check_links.py reports the dead link; do not hide it

    fresh = ""
    for channel in candidate_channels(token):
        fresh = mint(token, channel)
        if fresh:
            break
    if not fresh:
        log("the bot could not create an invite in any channel it can see; "
            "give it CREATE_INVITE in a text channel or set "
            "DISCORD_INVITE_URL to a permanent invite yourself")
        return 0
    log(f"made a permanent invite: {fresh}")
    remember(fresh)
    save_variable(fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
