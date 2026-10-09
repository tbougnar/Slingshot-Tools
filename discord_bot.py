"""The Slingshot Tools Discord bot.

Driven by the same pipeline that builds the tools, so the server reflects what
is actually live. Handles the interactive parts a webhook cannot:

    /tools          every live tool with prices and links
    /article slug   the write-up for one tool
    /vote           the open ballot, as buttons, with live counts
    /vote results   closed-poll history
    /ping           liveness check

Run it with a bot token:

    DISCORD_BOT_TOKEN=... python discord_bot.py

The bot is optional. Without a token this exits quietly and the webhook in
discord_announce.py still posts announcements, so the server is never silent.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import discord_data as dd

try:
    import discord
except ImportError:  # noqa: BLE001
    discord = None

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
PREFIX = "new: "
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip() or None
MAX_EMBED = 4000  # Discord's hard limit


def log(msg: str) -> None:
    print(f"[bot] {msg}", flush=True)


def clip(text: str, limit: int = MAX_EMBED) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def split_embed(text: str, limit: int = 3800) -> list[str]:
    """Split a long article across several embeds at paragraph boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    parts, buf = [], []
    size = 0
    for line in text.splitlines():
        add = len(line) + 1
        if size + add > limit and buf:
            parts.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += add
    if buf:
        parts.append("\n".join(buf))
    return parts


# ----------------------------------------------------------------- rendering

def tools_view() -> discord.Embed:
    tools = dd.live_tools()
    if not tools:
        return discord.Embed(
            title="Slingshot Tools",
            description="No tools are live yet. The first one lands soon.",
            color=dd_ok())
    lines = []
    for t in tools:
        price = f"${t['price']:.2f}" if t["price"] else "free"
        row = f"**{t['title']}** - {price}"
        if t["free_url"]:
            row += f"\n[Free download]({t['free_url']})"
        if t["buy_url"]:
            row += f"  |  [Buy the full edition]({t['buy_url']})"
        if t["blurb"]:
            row += f"\n{clip(t['blurb'], 160)}"
        lines.append(row)
    body = "\n\n".join(lines)
    return discord.Embed(title="Live tools", description=clip(body),
                         color=dd_ok())


def dd_ok() -> int:
    return 0x2ECC71


def poll_embed(poll: dict) -> discord.Embed:
    rows = dd.tally(poll["id"])
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(f"**{i}. {r['label']}** - {r['votes']} vote(s)")
    body = "\n".join(lines) or "No options."
    if poll.get("notes"):
        body += f"\n\n{clip(poll['notes'], 600)}"
    body += f"\n\nVote with the buttons below. Results: `/vote results`"
    return discord.Embed(title=poll.get("question", "Vote for the next tool"),
                         description=clip(body), color=0xC1272D)


def article_embeds(slug: str) -> list:
    tool = dd.tool_by_slug(slug)
    body = dd.get_article(slug)
    if not body and tool:
        body = tool["blurb"]
    if not body:
        return []
    out = []
    for i, chunk in enumerate(split_embed(body)):
        emb = discord.Embed(description=chunk,
                            color=dd_ok() if i == 0 else 0x8899A6)
        if i == 0 and tool:
            emb.title = tool["title"]
            emb.url = f"{dd.SITE_URL}/"
            if tool["price"]:
                emb.add_field(name="Full edition",
                              value=f"${tool['price']:.2f}", inline=True)
            if tool["free_url"]:
                emb.add_field(name="Free download",
                              value=f"[link]({tool['free_url']})", inline=True)
        out.append(emb)
    return out


# -------------------------------------------------------------------- client

def register(tree):
    """Attach every slash command to a CommandTree.

    Kept separate from build_client so the setup script can register the same
    commands without spinning up a second client.
    """

    @tree.command(name="ping", description="Is the Slingshot bot running?")
    async def ping(interaction):
        await interaction.response.send_message(
            f"Pong - {len(dd.live_tools())} tool(s) live.", ephemeral=True)

    @tree.command(name="tools", description="Every live Slingshot Tool.")
    async def tools(interaction):
        await interaction.response.send_message(embed=tools_view(), ephemeral=True)

    @tree.command(name="article", description="Read about one tool.")
    @discord.app_commands.describe(slug="For example: password-manager")
    async def article(interaction, slug: str):
        embeds = article_embeds(slug)
        if not embeds:
            await interaction.response.send_message(
                f"No article for `{slug}` yet. Try `/tools`.", ephemeral=True)
            return
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    @tree.command(name="vote", description="Vote for the next Slingshot Tool.")
    @discord.app_commands.describe(
        results="Show closed polls instead of the open ballot")
    async def vote(interaction, results: bool = False):
        if results:
            await interaction.response.send_message(
                embed=results_embed(), ephemeral=True)
            return

        poll = dd.open_poll()
        if not poll:
            await interaction.response.send_message(
                "No ballot is open right now. The AI opens a new one after "
                "each release.", ephemeral=True)
            return

        view = build_vote_view(poll)
        await interaction.response.send_message(embed=poll_embed(poll), view=view,
                                                ephemeral=True)

    return tree


def build_client() -> "discord.Client":
    intents = discord.Intents.default()
    intents.message_content = False          # the bot never reads messages
    client = discord.Client(intents=intents)
    tree = register(discord.app_commands.CommandTree(client))

    @client.event
    async def on_ready():
        log(f"logged in as {client.user}")
        try:
            if GUILD_ID:
                guild = discord.Object(id=int(GUILD_ID))
                await tree.sync(guild=guild)
                log(f"commands synced to guild {GUILD_ID}")
            else:
                await tree.sync()
                log("commands synced globally")
        except Exception as e:  # noqa: BLE001
            log(f"command sync failed: {e}")

    return client


if discord is not None:

    def build_vote_view(poll: dict):
        """One button per option. Rebuilt after every vote so counts refresh."""
        view = discord.ui.View(timeout=None)
        for i, opt in enumerate(poll.get("options", [])[:5], 1):
            view.add_item(VoteButton(poll["id"], opt["label"], i))
        return view

    class VoteButton(discord.ui.Button):
        """One ballot option. Re-renders the counts in place as votes land."""

        def __init__(self, poll_id: str, label: str, number: int):
            super().__init__(style=discord.ButtonStyle.primary,
                             label=f"{number}. {label}"[:80],
                             custom_id=f"vote:{poll_id}:{label}"[:100])
            self.poll_id = poll_id
            self.option = label

        async def callback(self, interaction):
            result = dd.vote(self.poll_id, self.option, str(interaction.user.id))
            if result.startswith("error:"):
                await interaction.response.send_message(
                    f"Could not record that vote: {result[6:]}", ephemeral=True)
                return
            if result == "closed":
                await interaction.response.send_message(
                    "That ballot has closed. Ask the AI to open the next one.",
                    ephemeral=True)
                return

            poll = dd.polls().get(self.poll_id)
            await interaction.response.edit_message(
                embed=poll_embed(poll), view=build_vote_view(poll))


def results_embed() -> discord.Embed:
    data = dd.polls()
    closed = [p for p in data.values()
              if isinstance(p, dict) and p.get("status") == "closed"]
    if not closed:
        return discord.Embed(title="Poll results",
                             description="No ballot has closed yet.",
                             color=0x8899A6)
    closed.sort(key=lambda p: p.get("closed") or 0, reverse=True)
    lines = []
    for p in closed[:10]:
        rows = p.get("result") or dd.tally(p["id"])
        top = rows[0] if rows else {"label": "?", "votes": 0}
        win = p.get("winner")
        lines.append(f"**{p.get('question', p['id'])}**\n"
                     + "\n".join(f"- {r['label']}: {r['votes']}" for r in rows)
                     + (f"\nWinner: **{win}**" if win else "\nResult: tie"))
    return discord.Embed(title="Poll results", description=clip("\n\n".join(lines)),
                         color=0x8899A6)


# -------------------------------------------------------- pipeline side hooks

def announce_now(slug: str, text: str = "") -> bool:
    """Post an announcement from outside the bot, e.g. a cron job.

    Requires a channel id because there is no interaction to reply to.
    """
    channel_id = os.environ.get("DISCORD_ANNOUNCEMENTS_CHANNEL_ID", "").strip()
    if not TOKEN or not channel_id:
        log("announce_now needs DISCORD_BOT_TOKEN and "
            "DISCORD_ANNOUNCEMENTS_CHANNEL_ID")
        return False

    async def run():
        intents = discord.Intents.default()
        async with discord.Client(intents=intents) as client:
            await client.wait_until_ready()
            channel = client.get_channel(int(channel_id)) or await client.fetch_channel(
                int(channel_id))
            tool = dd.tool_by_slug(slug)
            emb = discord.Embed(
                title=f"New tool: {(tool or {}).get('title', slug)}",
                description=clip((tool or {}).get("blurb") or text or ""),
                url=f"{dd.SITE_URL}/", color=dd_ok())
            if (tool or {}).get("free_url"):
                emb.add_field("Free download",
                              f"[link]({tool['free_url']})", inline=True)
            if (tool or {}).get("buy_url"):
                emb.add_field("Buy the full edition",
                              f"[checkout]({tool['buy_url']})", inline=True)
            await channel.send(embed=emb)

    try:
        asyncio.run(run())
        return True
    except Exception as e:  # noqa: BLE001
        log(f"announce failed: {e}")
        return False


def main() -> int:
    if not TOKEN:
        log("no DISCORD_BOT_TOKEN set - the bot stays offline "
            "(announcements still work through the webhook)")
        return 0
    if discord is None:
        log("discord.py is not installed; run: pip install discord.py")
        return 1
    log("starting")
    build_client().run(TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
