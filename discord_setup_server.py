"""Create and configure the Slingshot Tools Discord server.

Idempotent and safe to re-run. Categories and channels are matched by name and
position order, so a second run reuses what is there, corrects permissions and
topics, and removes leftovers instead of duplicating them. Leftovers that hold
messages are never deleted: they are renamed with an ``old-`` prefix and
reported.

Usage
-----
    python discord_setup_server.py --dry-run      # show the plan, touch nothing
    python discord_setup_server.py                # build it for real
    python discord_setup_server.py --keep-legacy  # do not clean up leftovers

Needs a bot token and the server id:

    DISCORD_BOT_TOKEN=... DISCORD_GUILD_ID=... python discord_setup_server.py

The bot needs the Manage Channels and Use Application Commands permissions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import aiohttp

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
API = "https://discord.com/api/v10"

# channel type ids
TEXT = 0
ANNOUNCEMENT = 5

# permission bits, from Discord's table
ADMINISTRATOR = 1 << 3
MANAGE_CHANNELS = 1 << 4
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_HISTORY = 1 << 16
ADD_REACTIONS = 1 << 17
USE_APPLICATION_COMMANDS = 1 << 31
MANAGE_WEBHOOKS = 1 << 28
SLOW_MODE = 30

# what the bot needs in every channel it posts to
BOT_BITS = (VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES
            | READ_HISTORY | ADD_REACTIONS | USE_APPLICATION_COMMANDS
            | MANAGE_WEBHOOKS | MANAGE_CHANNELS)

# Members in a chat channel: talk and react
MEMBER_WRITE = (VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES
                | READ_HISTORY | ADD_REACTIONS)

# Members in a ballot channel: they vote by replying, so posting is allowed
# there and nowhere else.
MEMBER_VOTE = (VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ADD_REACTIONS
               | READ_HISTORY)

# Members in a read-only channel: reading and reacting, never typing. Reacting
# is how somebody answers an announcement.
MEMBER_REACT = VIEW_CHANNEL | READ_HISTORY | ADD_REACTIONS
MEMBER_REACT_DENY = SEND_MESSAGES

# kind, name, topic, type
#
# The emoji prefix is part of the name. The bot looks its channels up by name,
# so the names here and the ones on the server have to match.
#
# kind:
#   "bot"   the bot posts; members read and react, but cannot type
#   "vote"  members reply, because a reply is how a ballot is cast
#   "chat"  members talk and react
#   "human" members talk
#   "owner" only the server owner (an Administrator) and the bot
LAYOUT = [
    ("\U0001f3e0-start-here", None, None, None),
    ("\U0001f44b-welcome", "chat",
     "What Slingshot Tools is, and how one tool ships every week.", TEXT),
    ("\U0001f4d3-rules", "human",
     "Short and practical. Be decent, no spam.", TEXT),
    ("\U0001f4e3-announcements", "bot",
     "Every new tool, posted the moment it goes live. React with an emoji to "
     "tell us what you think.", ANNOUNCEMENT),
    ("\U0001f5fa\ufe0f-roadmap", "bot",
     "What is being built now, and what comes after it.", TEXT),

    ("\U0001f6e0\ufe0f-tools", None, None, None),
    ("\U0001f6e0\ufe0f-catalog", "bot",
     "The whole catalog. Use /tools in this server.", TEXT),
    ("\U0001f4da-articles", "bot",
     "A longer write-up for each tool. Use /article <slug>.", TEXT),
    ("\U0001f4e9-downloads", "bot",
     "Free downloads, one installer per tool.", TEXT),
    ("\U0001f4e4-showcase", "human",
     "Screenshots, tips, and what you built with these.", TEXT),
    ("\U0001f198-support", "human",
     "Bugs, questions and feature requests.", TEXT),

    ("\U0001f6d2-shop", None, None, None),
    ("\U0001f6d2-store", "bot",
     "Buy the Full edition of any tool. Checkout runs on the website.", TEXT),
    ("\U0001f6d2-checkout-help", "human",
     "Stuck at payment? Say it here and it gets sorted.", TEXT),

    ("\U0001f5f3\ufe0f-voting", None, None, None),
    ("\U0001f5f3\ufe0f-polls", "vote",
     "The ballot for next week's tool. Reply to the ballot with the emoji of "
     "the one you want.", TEXT),
    ("\U0001f4a1-ideas", "chat",
     "Tools you want that are not on the ballot yet. Talk about them here, "
     "and react to what you like.", TEXT),
    ("\U0001f451-idea-rating", "bot",
     "How the community ranks the ideas above.", TEXT),
    ("\U0001f3c6-results", "bot",
     "How each ballot turned out, and what it decided.", TEXT),

    ("\U0001f4d6-about", None, None, None),
    ("\u2699\ufe0f-how-it-works", "bot",
     "Monday ballot, Wednesday review, Friday release: the week, explained.",
     TEXT),
    ("\U0001f4dd-changelog", "bot",
     "Changes worth knowing about.", TEXT),
    ("\U0001f517-links", "human",
     "Website, repository and contact.", TEXT),

    ("\U0001f512-owner", None, None, None),
    ("\U0001f512-owner-room", "owner",
     "Private. Notes, and the Discord secrets you need to paste here.", TEXT),
]

CATEGORY_NAMES = [n for n, kind, _, _ in LAYOUT if n and kind is None]

COMMANDS = [
    {"name": "ping", "description": "Is the Slingshot bot running?"},
    {"name": "tools", "description": "Every live Slingshot Tool."},
    {"name": "article", "description": "Read about one tool.",
     "options": [{"name": "slug", "description": "Tool slug, like "
                    "password-manager", "type": 3, "required": True}]},
    {"name": "vote", "description": "Vote for the next Slingshot Tool.",
     "options": [{"name": "results",
                  "description": "Show closed polls instead of the open ballot",
                  "type": 5, "required": False}]},
]


class Discord:
    """The small slice of the REST API this script needs."""

    def __init__(self, session: aiohttp.ClientSession):
        self.s = session

    async def call(self, method: str, path: str, **kw):
        async with self.s.request(method, API + path, **kw) as r:
            text = await r.text()
            try:
                body = json.loads(text) if text else None
            except ValueError:
                body = text
            return r.status, body

    async def channels(self):
        st, data = await self.call("GET", f"/guilds/{GUILD_ID}/channels")
        if st != 200:
            raise SystemExit(f"[setup] cannot list channels: {st} {data}")
        return data

    async def roles(self):
        st, data = await self.call("GET", f"/guilds/{GUILD_ID}/roles")
        if st != 200:
            raise SystemExit(f"[setup] cannot list roles: {st} {data}")
        return data

    async def create_category(self, name: str):
        st, data = await self.call("POST", f"/guilds/{GUILD_ID}/channels",
                                   json={"name": name, "type": 4})
        if st != 201:
            raise SystemExit(f"[setup] could not create {name}: {st} {data}")
        return data

    async def create_channel(self, name, topic, ctype, parent, overwrites):
        st, data = await self.call(
            "POST", f"/guilds/{GUILD_ID}/channels",
            json={"name": name, "topic": topic, "type": ctype,
                  "parent_id": parent, "permission_overwrites": overwrites,
                  "position": 0})
        if st != 201:
            raise SystemExit(f"[setup] could not create #{name}: {st} {data}")
        return data

    async def edit_channel(self, cid, **fields):
        return await self.call("PATCH", f"/channels/{cid}", json=fields)

    async def delete_channel(self, cid):
        return await self.call("DELETE", f"/channels/{cid}")

    async def message_count(self, cid) -> int:
        st, data = await self.call("GET", f"/channels/{cid}/messages?limit=1")
        return len(data) if st == 200 and isinstance(data, list) else 0

    async def put_commands(self, app_id):
        st, data = await self.call(
            "PUT", f"/applications/{app_id}/guilds/{GUILD_ID}/commands",
            json=COMMANDS)
        if st not in (200, 201):
            print(f"[setup] could not register commands: {st} {data}")
            return 0
        names = sorted(c.get("name", "?") for c in data)
        st, live = await self.call(
            "GET", f"/applications/{app_id}/guilds/{GUILD_ID}/commands")
        live_names = sorted(c.get("name", "?") for c in live) \
            if isinstance(live, list) else []
        if names != live_names:
            print(f"[setup] WARNING: wrote {names}, server shows {live_names}")
        print(f"[setup] registered {len(live_names)} command(s): "
              f"{', '.join(live_names)}")
        return len(live_names)

    async def whoami(self):
        st, data = await self.call("GET", "/users/@me")
        if st != 200:
            raise SystemExit("[setup] the bot token was rejected "
                             f"({st}). Reset it in the Developer Portal.")
        return data


def plan_lines() -> list[str]:
    out = []
    for name, kind, topic, ctype in LAYOUT:
        if kind is None:
            out.append(f"  [category] {name}")
            continue
        who = {"bot": "bot only, members read-only",
               "owner": "owner and bot only",
               "human": "everyone can post"}[kind]
        note = " [announcement channel]" if ctype == ANNOUNCEMENT else ""
        out.append(f"      - #{name} ({who}){note}")
        out.append(f"          {topic}")
    return out


def overwrites_for(kind: str, everyone_id: str, bot_role_id: str) -> list[dict]:
    """Permission overwrites for one channel.

    A bit left out of both allow and deny is inherited from the base role,
    which here would leave Send Messages on. So a read-only channel denies it
    outright rather than relying on the base role staying quiet.
    """
    if kind == "owner":
        member_allow = "0"
        member_deny = str(VIEW_CHANNEL | SEND_MESSAGES | ADD_REACTIONS)
    elif kind in ("chat", "human"):
        member_allow, member_deny = str(MEMBER_WRITE), "0"
    elif kind == "vote":
        member_allow, member_deny = str(MEMBER_VOTE), "0"
    else:
        # "bot": read and react, never type. Reacting is how people answer an
        # announcement, so ADD_REACTIONS is granted on purpose.
        member_allow = str(MEMBER_REACT)
        member_deny = str(MEMBER_REACT_DENY)
    return [
        {"id": everyone_id, "type": 0,
         "allow": member_allow, "deny": member_deny},
        {"id": bot_role_id, "type": 0, "allow": str(BOT_BITS), "deny": "0"},
    ]


async def find_roles(d: Discord) -> tuple[str, str]:
    """The @everyone role id and the bot's own role id."""
    me = await d.whoami()
    roles = await d.roles()
    everyone_id = GUILD_ID          # @everyone always shares the server id
    bot_role_id = None
    for r in roles:
        if r["id"] == GUILD_ID:
            everyone_id = r["id"]
        if r.get("tags", {}).get("bot_id") == me["id"]:
            bot_role_id = r["id"]
    if bot_role_id is None:
        for r in roles:
            if r["name"] == me["username"]:
                bot_role_id = r["id"]
    if bot_role_id is None:
        raise SystemExit("[setup] cannot find the bot's role in this server")
    return everyone_id, bot_role_id


async def build(d: Discord, keep_legacy: bool) -> None:
    me = await d.whoami()
    everyone_id, bot_role_id = await find_roles(d)

    existing = await d.channels()
    by_id = {c["id"]: c for c in existing}
    keep: set[str] = set()
    made = reused = 0

    cats: dict[str, dict] = {}
    for name in CATEGORY_NAMES:
        found = [c for c in existing
                 if c["type"] == 4 and c["name"] == name]
        found.sort(key=lambda c: c["position"])
        if found:
            cats[name] = found[0]
            reused += 1
            print(f"[setup] category exists: {name}")
        else:
            cat = await d.create_category(name)
            cats[name] = cat
            by_id[cat["id"]] = cat
            existing.append(cat)
            made += 1
            print(f"[setup] created category: {name}")

    current = None
    for name, kind, topic, ctype in LAYOUT:
        if kind is None:
            current = cats[name]
            keep.add(current["id"])
            continue

        siblings = [c for c in existing
                    if c["type"] in (TEXT, ANNOUNCEMENT)
                    and c.get("parent_id") == current["id"]
                    and c["name"] == name]
        siblings.sort(key=lambda c: c["position"])
        overs = overwrites_for(kind, everyone_id, bot_role_id)

        if siblings:
            target = siblings[0]
            reused += 1
            st, data = await d.edit_channel(
                target["id"],
                permission_overwrites=overs,
                topic=topic,
                rate_limit_per_user=SLOW_MODE if kind == "human" else 0,
            )
            if st == 200:
                print(f"[setup] updated #{name}")
            else:
                print(f"[setup] could not update #{name}: {st} {data}")
            keep.add(target["id"])
        else:
            target = await d.create_channel(name, topic, ctype,
                                            current["id"], overs)
            by_id[target["id"]] = target
            made += 1
            print(f"[setup] created #{name}")
            keep.add(target["id"])

    if not keep_legacy:
        await drop_leftovers(d, existing, keep)

    print(f"[setup] done: {made} created, {reused} reused")


async def drop_leftovers(d: Discord, existing: list, keep: set) -> None:
    """Clear out anything from an older layout.

    Empty channels and categories are deleted. Anything holding messages is
    kept, renamed with an ``old-`` prefix, and reported.
    """
    for ch in existing:
        if ch["id"] in keep:
            continue
        if ch["type"] == 4:
            continue                      # handled after its channels
        if ch["type"] not in (TEXT, ANNOUNCEMENT, 2, 13, 15):
            continue

        n = await d.message_count(ch["id"])
        if n == 0:
            st, data = await d.delete_channel(ch["id"])
            if st in (200, 204):
                print(f"[setup] deleted empty #{ch['name']}")
            else:
                print(f"[setup] could not delete #{ch['name']}: {st} {data}")
        else:
            # do not pile prefixes up on repeated runs
            base = ch["name"]
            while base.startswith("old-"):
                base = base[4:]
            safe = f"old-{base}"[:100]
            if safe == ch["name"]:
                print(f"[setup] kept #{ch['name']} ({n} message(s))")
                continue
            st, data = await d.edit_channel(ch["id"], name=safe)
            if st == 200:
                print(f"[setup] kept #{ch['name']} ({n} message(s)), "
                      f"renamed to #{safe}")
            else:
                print(f"[setup] kept #{ch['name']} ({n} message(s)), "
                      f"rename failed: {st}")

    # now the categories that no longer hold anything
    for ch in existing:
        if ch["type"] != 4 or ch["id"] in keep:
            continue
        st, kids = await d.call("GET", f"/channels/{ch['id']}")
        if st == 200 and kids:
            # only empty leftovers in here, so the category itself is dead
            for kid in kids:
                await d.delete_channel(kid["id"])
            st, kids2 = await d.call("GET", f"/channels/{ch['id']}")
            if st == 200 and kids2:
                print(f"[setup] kept category {ch['name']}, it still has "
                      f"{len(kids2)} channel(s)")
                continue
            print(f"[setup] emptied category {ch['name']}")
        st, data = await d.delete_channel(ch["id"])
        if st in (200, 204):
            print(f"[setup] deleted empty category {ch['name']}")
        else:
            print(f"[setup] could not delete category {ch['name']}: {st}")


async def check_permissions(d: Discord, bot_role_id: str) -> bool:
    """The bot needs to manage channels and register commands.

    Read from the role itself rather than a per-guild endpoint, because
    /users/@me/guilds/<id> is not available to application tokens.
    """
    roles = await d.roles()
    for r in roles:
        if r["id"] != bot_role_id:
            continue
        p = int(r["permissions"])
        if p & (1 << 3):                  # administrator covers everything
            return True
        return bool((p & (1 << 4)) and (p & (1 << 31)))
    return False


async def run(dry_run: bool, keep_legacy: bool) -> int:
    if dry_run:
        print("[setup] DRY RUN - nothing will be changed")
        print("[setup] planned structure:")
        for line in plan_lines():
            print(line)
        print()
        print("[setup] to apply it, set the secrets and re-run without "
              "--dry-run:")
        print("  DISCORD_BOT_TOKEN=<bot token>")
        print("  DISCORD_GUILD_ID=<your server id>")
        return 0

    if not TOKEN:
        print("[setup] DISCORD_BOT_TOKEN is not set")
        return 1
    if not GUILD_ID:
        print("[setup] DISCORD_GUILD_ID is not set")
        return 1
    if not GUILD_ID.isdigit():
        print(f"[setup] DISCORD_GUILD_ID is not a number: {GUILD_ID!r}")
        return 1

    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        d = Discord(session)

        st, guilds = await d.call("GET", "/users/@me/guilds")
        if st != 200:
            print(f"[setup] the bot token was rejected ({st})")
            return 1
        if not any(g["id"] == GUILD_ID for g in guilds):
            print(f"[setup] the bot is not in server {GUILD_ID}. Invite it "
                  "first: OAuth2 -> URL Generator, scopes 'bot' and "
                  "'applications.commands'.")
            return 1

        me = await d.whoami()
        print(f"[setup] connected as {me['username']}#{me['discriminator']}")

        _, bot_role_id = await find_roles(d)
        if not await check_permissions(d, bot_role_id):
            print("[setup] the bot's role lacks Manage Channels or Use "
                  "Application Commands")
            print("[setup] enable Administrator on the bot's role, then "
                  "re-run")
            return 1

        await build(d, keep_legacy)

        st, app = await d.call("GET", "/oauth2/applications/@me")
        if st == 200:
            await d.put_commands(app["id"])

    print()
    print("[setup] next steps:")
    print("  - start the bot so the slash commands answer: "
          "python discord_bot.py")
    print("  - your account is the server Administrator, so you can post "
          "and pin anywhere")
    print("  - preview an announcement: python discord_announce.py --dry-run")
    return 0


def main() -> int:
    # channel names carry emoji, so the console has to handle utf-8
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    ap = argparse.ArgumentParser(description="Build the Discord server layout")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without changing anything")
    ap.add_argument("--keep-legacy", action="store_true",
                    help="leave old channels alone instead of cleaning up")
    args = ap.parse_args()
    return asyncio.run(run(args.dry_run, args.keep_legacy))


if __name__ == "__main__":
    raise SystemExit(main())