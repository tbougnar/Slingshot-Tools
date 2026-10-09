"""Create and configure the Slingshot Tools Discord server.

Idempotent: safe to re-run. Existing categories and channels are reused and
corrected rather than duplicated, so it can be run again whenever the layout
changes.

Usage
-----
    python discord_setup_server.py --dry-run      # show the plan, touch nothing
    python discord_setup_server.py                # build it for real

Needs a bot token with the Manage Channels permission, plus the server id:

    DISCORD_BOT_TOKEN=... DISCORD_GUILD_ID=... python discord_setup_server.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
MOD_ROLE_ID = os.environ.get("DISCORD_MOD_ROLE_ID", "").strip()

try:
    import discord
except ImportError:  # noqa: BLE001
    discord = None


# ---------------------------------------------------------------- the layout
# name, kind ("bot" = bot posts, members read only, "human" = members write),
# topic shown in the channel
LAYOUT = [
    ("START HERE", None, None),
    ("welcome", "human",
     "What Slingshot Tools is and how the monthly build works."),
    ("rules", "human",
     "Short and practical. Be decent, no spam."),
    ("announcements", "bot",
     "Every new tool, posted automatically when it goes live."),
    ("roadmap", "bot",
     "What is shipping now and what comes next."),

    ("TOOLS", None, None),
    ("tools", "bot",
     "The whole catalog. Use /tools in the server."),
    ("articles", "bot",
     "A longer write-up for each tool. Use /article <slug>."),
    ("downloads", "bot",
     "Free downloads and the link to buy the full edition."),
    ("showcase", "human",
     "Screenshots, tips, and how you use these tools."),
    ("support", "human",
     "Bugs, questions and feature requests."),

    ("VOTING", None, None),
    ("polls", "bot",
     "The ballot for the next tool. Use /vote to have your say."),
    ("ideas", "human",
     "Tools you want that are not on the ballot yet."),
    ("results", "bot",
     "How each ballot turned out and what it decided."),

    ("ABOUT", None, None),
    ("how-it-works", "bot",
     "Generate, verify, build, publish: the pipeline explained."),
    ("changelog", "bot",
     "Changes worth knowing about."),
    ("links", "human",
     "Website, repository and support."),
]

CATEGORY_ORDER = [name for name, kind, _ in LAYOUT if kind is None]


def bot_permissions() -> discord.Permissions:
    """Everything the bot needs to run the server."""
    return discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        use_application_commands=True,
        manage_channels=True,
    )


def moderator_permissions() -> discord.Permissions:
    """Human moderation: talk in the bot channels, and keep them tidy."""
    return discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        manage_messages=True,
        manage_channels=True,
        read_message_history=True,
    )


def member_permissions() -> discord.Permissions:
    """Members: read and use the bot, but never post in a bot channel."""
    return discord.Permissions(
        view_channel=True,
        read_message_history=True,
        use_application_commands=True,
        send_messages=False,
        embed_links=False,
        add_reactions=True,
    )


def plan_lines() -> list[str]:
    out = []
    for name, kind, topic in LAYOUT:
        if kind is None:
            out.append(f"  [category] {name}")
        elif kind == "bot":
            out.append(f"      - #{name} (bot only, members read-only)  {topic or ''}")
        else:
            out.append(f"      - #{name} (everyone can post)            {topic or ''}")
    return out


async def configure(guild: discord.Guild) -> int:
    everyone = guild.default_role
    bot_role = guild.me.top_role
    mod_role = None
    if MOD_ROLE_ID:
        mod_role = guild.get_role(int(MOD_ROLE_ID))
        if mod_role is None:
            print(f"[setup] warning: moderator role {MOD_ROLE_ID} not found")

    mods = ([mod_role] if mod_role else []) + [bot_role]
    made = reused = 0

    # categories first, in the declared order
    cats: dict[str, discord.CategoryChannel] = {}
    existing_cats = {c.name: c for c in guild.categories}
    for name in CATEGORY_ORDER:
        if name in existing_cats:
            cats[name] = existing_cats[name]
            reused += 1
            print(f"[setup] category exists: {name}")
        else:
            cats[name] = await guild.create_category(name)
            made += 1
            print(f"[setup] created category: {name}")

    current = None
    for name, kind, topic in LAYOUT:
        if kind is None:
            current = cats[name]
            continue

        target = None
        for ch in guild.text_channels:
            if ch.name == name and ch.category_id == current.id:
                target = ch
                break
        if target is None:
            target = await current.create_text_channel(name, topic=topic)
            made += 1
            print(f"[setup] created #{name}")
        else:
            reused += 1
            if topic and (target.topic or "") != topic:
                try:
                    await target.edit(topic=topic)
                    print(f"[setup] updated #{name} topic")
                except discord.Forbidden:
                    print(f"[setup] no permission to edit #{name} topic")

        # members may read; only moderators and the bot may write
        allow_write = kind == "human"
        if allow_write:
            # members speak in human channels but still cannot use the bot
            # commands outside their own channel
            overwrites = {
                everyone: discord.PermissionOverwrite.from_pair(
                    discord.Permissions(
                        view_channel=True,
                        read_message_history=True,
                        send_messages=True,
                        embed_links=True,
                        add_reactions=True,
                    ),
                    discord.Permissions.none()),
                bot_role: bot_permissions(),
            }
        else:
            # bot channels: members read, they do not write
            overwrites = {
                everyone: discord.PermissionOverwrite.from_pair(
                    member_permissions(), discord.Permissions.none()),
                bot_role: bot_permissions(),
            }
        if mod_role:
            overwrites[mod_role] = moderator_permissions()

        try:
            await target.edit(overwrites=overwrites)
        except discord.Forbidden:
            print(f"[setup] no permission to set permissions on #{name}")

    print(f"[setup] done: {made} created, {reused} reused")
    return made + reused


async def register_commands(client: discord.Client) -> None:
    """Push the slash commands to this server only, which takes seconds."""
    import discord_bot
    tree = discord_bot.register(discord.app_commands.CommandTree(client))
    guild = discord.Object(id=int(GUILD_ID))
    synced = await tree.sync(guild=guild)
    print(f"[setup] synced {len(synced)} command(s) to this server")
    print(f"[setup] commands: {', '.join(sorted(c.name for c in synced))}")


async def run(dry_run: bool) -> int:
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
    try:
        guild_id = int(GUILD_ID)
    except ValueError:
        print(f"[setup] DISCORD_GUILD_ID is not a number: {GUILD_ID!r}")
        return 1

    if dry_run:
        print("[setup] DRY RUN - nothing will be changed")
        print("[setup] planned structure:")
        for line in plan_lines():
            print(line)
        return 0

    intents = discord.Intents.default()
    intents.message_content = False
    async with discord.Client(intents=intents) as client:
        try:
            await client.login(TOKEN)
        except discord.LoginFailure as e:
            print(f"[setup] the bot token was rejected: {e}")
            return 1

        guild = client.get_guild(guild_id)
        if guild is None:
            print(f"[setup] server {guild_id} not found. Invite the bot to it "
                  f"first: OAuth2 -> URL Generator, scopes "
                  f"'bot' and 'applications.commands'.")
            return 1

        me = guild.me
        missing = [p for p in ("manage_channels", "use_application_commands")
                   if not me.guild_permissions.permissions.get(p)]
        if missing:
            print(f"[setup] the bot is missing permissions: {', '.join(missing)}")
            print("[setup] enable Administrator on the bot role, or grant "
                  "Manage Channels and Use Application Commands.")
            return 1

        print(f"[setup] connected as {me} in '{guild.name}'")
        await configure(guild)
        await register_commands(client)

    print()
    print("[setup] next steps:")
    print("  - create a role called 'Moderator' and set DISCORD_MOD_ROLE_ID to "
          "its id if you want moderators to post in the bot channels")
    print("  - start the bot so the slash commands answer: "
          "python discord_bot.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="__doc__")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without changing anything")
    args = ap.parse_args()

    if discord is None:
        print("[setup] discord.py is not installed: "
              "pip install \"discord.py>=2.3\"")
        return 1
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())