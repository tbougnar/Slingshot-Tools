"""Give every channel something in it, and keep it that way.

An empty channel looks broken, whether or not anything is wrong. This fills any
channel that has no messages with a short, honest introduction, so a member
who clicks in always finds something that explains what the channel is for.

Nothing is posted twice: a channel with any message is left alone, so this is
safe to run from the weekly cycle. Nothing is ever deleted either.

It also refreshes the channels that are supposed to stay current, such as the
catalog and the roadmap, because those go stale on their own as products ship.
"""
from __future__ import annotations

import json
import sys

import discord_data as dd
import discord_post as dp

BRAND = 0xC1272D
OK = 0x2ECC71

# The first message in each channel, written once and never repeated.
INTRO = {
    "catalog": {
        "title": "Welcome to Slingshot Tools",
        "description": (
            "One small, useful tool every week, chosen by the people who use "
            "them.\n\n"
            "**Every tool comes in two editions.** The Basic edition is free "
            "and runs in your browser. The Full edition is a real Windows app "
            "with nothing capped, sold on the site.\n\n"
            "**Nothing is collected.** No accounts, no sign-up, no tracking, "
            "no cookies. The tools make no network calls and your data never "
            "leaves your device.\n\n"
            "New here? Start in "
            "<#1558218171138179263> for the catalog, or vote on what gets "
            "built in <#1558218192147714161>."),
        "color": BRAND,
    },
    "rules": {
        "title": "Rules",
        "description": (
            "Only three, and all of them are about being decent.\n\n"
            "**1.** Be decent to each other. No harassment, no slurs.\n"
            "**2.** No spam, no advertising, no self-promotion.\n"
            "**3.** Post what belongs. Bugs go in "
            "<#1558218181175156826>, ideas in <#1558218196983615540>.\n\n"
            "That is the whole list. If something is ambiguous, use your "
            "judgement."),
        "color": BRAND,
    },
    "announcements": {
        "title": "Announcements",
        "description": (
            "Every new tool lands here first. Read-only, so nobody can talk "
            "over a release.\n\n"
            "You can still **react with an emoji**. That is genuinely useful: "
            "it tells us what people actually want without anyone having to "
            "type, and it is the fastest signal we get."),
        "color": BRAND,
    },
    "roadmap": {
        "title": "Roadmap",
        "description": (
            "What is being built, and what comes after.\n\n"
            "The short version: the ballot in "
            "<#1558218192147714161> decides the next tool. Whatever wins on "
            "Friday is what gets built that week.\n\n"
            "Posted here as each release lands, so you can see the shape of "
            "it rather than having to remember."),
        "color": BRAND,
    },
    "catalog": {
        "title": "The catalog",
        "description": (
            "Every live tool, newest at the top.\n\n"
            "Use `/tools` in this server for the list with prices and links, "
            "or browse the site.\n\n"
            "This post refreshes itself every Friday as tools ship."),
        "color": OK,
    },
    "articles": {
        "title": "Articles",
        "description": (
            "A proper write-up for each tool: what problem it solves, what the "
            "free edition does, and what the paid one adds.\n\n"
            "Use `/article` followed by a slug, for example "
            "`/article password-manager`.\n\n"
            "Posted automatically when a tool goes live."),
        "color": BRAND,
    },
    "downloads": {
        "title": "Downloads",
        "description": (
            "Free downloads, one installer per tool.\n\n"
            "The Basic edition of every tool is free and needs no installer at "
            "all, it runs in the browser. The Full edition is a Windows "
            "installer, sold on the site.\n\n"
            "This channel refreshes as new tools ship."),
        "color": BRAND,
    },
    "showcase": {
        "title": "Showcase",
        "description": (
            "What you made with these.\n\n"
            "Screenshots, workflows, the thing you built in an afternoon that "
            "used to take a morning. Talk about it here."),
        "color": BRAND,
    },
    "support": {
        "title": "Support",
        "description": (
            "Bugs, questions and feature requests.\n\n"
            "If something does not work, say which tool, what you did, and "
            "what happened instead. That is enough to fix it.\n\n"
            "Feature requests are welcome and they do get read."),
        "color": BRAND,
    },
    "store": {
        "title": "The shop",
        "description": (
            "Buy the Full edition of any tool.\n\n"
            "Same app as the free one, with nothing capped: export and import, "
            "extra themes, bulk actions, history, and a real Windows app with "
            "an installer instead of a browser tab.\n\n"
            "Checkout runs on the site. If it goes wrong, say so in "
            "<#1558218188699865100> and it gets sorted."),
        "color": OK,
    },
    "checkout-help": {
        "title": "Checkout help",
        "description": (
            "Stuck at payment?\n\n"
            "Say which tool, what you saw, and roughly when. That is all that "
            "is needed to sort it out."),
        "color": BRAND,
    },
    "polls": {
        "title": "Ballots",
        "description": (
            "This is where you decide what gets built.\n\n"
            "A ballot opens every Monday and closes on Friday. Each option "
            "has an emoji next to it. **Reply to the ballot with the emoji of "
            "the one you want.**\n\n"
            "Change your mind any time before Friday by replying again. Only "
            "your last reply counts, so nobody can vote twice.\n\n"
            "Whatever wins is what gets built."),
        "color": BRAND,
    },
    "ideas": {
        "title": "Ideas",
        "description": (
            "Tools you want that are not on the ballot yet.\n\n"
            "Talk about them here and react to what you like. The most "
            "discussed ones end up on the next ballot.\n\n"
            "Chat freely in this channel."),
        "color": BRAND,
    },
    "idea-rating": {
        "title": "Idea ranking",
        "description": (
            "How the ideas in <#1558218196983615540> rank.\n\n"
            "This posts after each ballot closes, so you can see what people "
            "actually wanted rather than what turned up."),
        "color": BRAND,
    },
    "results": {
        "title": "Results",
        "description": (
            "How each ballot turned out, and what it decided.\n\n"
            "Every result is posted here with the full tally. If the top two "
            "were level, it says so, because a tie is broken at random rather "
            "than pretending one of them won."),
        "color": OK,
    },
    "how-it-works": {
        "title": "How this works",
        "description": (
            "Monday ballot, Wednesday review, Friday release.\n\n"
            "**Monday** - a ballot opens here with five options.\n"
            "**Wednesday** - the week is reviewed: what sold, what people "
            "asked for, what changes. The generator also reviews itself and "
            "improves.\n"
            "**Friday** - the tool the ballot chose is built, clicked through "
            "in a real browser, and released.\n\n"
            "**It will not ship something broken.** Every control is tested "
            "before release. Two or more dead controls and nothing is "
            "published.\n\n"
            "**It cannot cheat.** The website, the prices and the products are "
            "all off limits to the automation.\n\n"
            "Everything runs on a schedule. Nothing waits for a person to press "
            "anything."),
        "color": BRAND,
    },
    "changelog": {
        "title": "Changelog",
        "description": (
            "What changed, and when.\n\n"
            "New tools, fixes, and the weekly review's conclusions. Posted "
            "automatically after each release."),
        "color": BRAND,
    },
    "links": {
        "title": "Links",
        "description": (
            "**Website:** https://tbougnar.github.io/Slingshot-Tools/\n"
            "**Repository:** https://github.com/tbougnar/Slingshot-Tools\n"
            "**Support:** ask in <#1558218181175156826>"),
        "color": BRAND,
    },
    "owner-room": {
        "title": "Owner",
        "description": (
            "Private. Just you and the bot.\n\n"
            "Notes, secrets to paste, and anything that should not be read by "
            "accident."),
        "color": BRAND,
    },
}

# Channels whose content goes stale as products ship, so they are refreshed
# rather than filled once.
REFRESH = {"catalog", "roadmap"}


def live_summary() -> str:
    """The catalog, for the channels that list it."""
    tools = dd.live_tools()
    if not tools:
        return ("No tools are live yet. The first one is being built now, and "
                "the ballot in the voting channel decides what it will be.")
    lines = []
    for t in tools:
        price = f"${t['price']:.2f}" if t["price"] else "free"
        row = f"**{t['title']}** - {price}"
        if t["free_url"]:
            row += f"\n[Free download]({t['free_url']})"
        if t["buy_url"]:
            row += f"  |  [Buy the full edition]({t['buy_url']})"
        lines.append(row)
    return "\n\n".join(lines)


def roadmap_summary() -> str:
    """What is being built and what is on offer."""
    poll = dd.open_poll()
    lines = []
    if poll:
        import discord_tally as dt
        options = "\n".join(
            f"{dt.option_emoji(i)} **{o['label']}**"
            for i, o in enumerate(poll.get("options", []), 1))
        lines.append(f"**Being decided now:** {poll.get('question', '')}\n"
                     f"{options}")
    winners = dd.recent_winners(1)
    if winners:
        lines.append(f"**Last ballot won by:** {winners[0].replace('-', ' ')}")

    tools = dd.live_tools()
    if tools:
        lines.append("**Live now:** " +
                     ", ".join(t["title"] for t in tools))
    else:
        lines.append("**Live now:** nothing yet.")
    return "\n\n".join(lines) if lines else "Nothing scheduled yet."


def build(channel: str) -> dict | None:
    """The message to put in a channel, or None to leave it alone."""
    spec = INTRO.get(channel)
    if not spec:
        return None

    embed = dict(spec)
    if channel == "catalog":
        embed["description"] = live_summary()
    elif channel == "roadmap":
        embed["description"] = roadmap_summary()
    return dp.embed_message(embed)


def fill(dry_run: bool = False) -> int:
    """Post an intro into every channel that has none."""
    posted = 0
    for channel in INTRO:
        if not dp.find_channel(channel):
            dp.log(f"#{channel} does not exist, skipping")
            continue
        existing = dp.messages(channel, 1)
        payload = build(channel)
        if payload is None:
            continue
        if existing and channel not in REFRESH:
            continue
        if existing and channel in REFRESH and _fresh(channel, existing[0]):
            continue
        if dry_run:
            print(f"would post to #{channel}")
            posted += 1
            continue
        if dp.post(channel, payload):
            dp.log(f"posted into #{channel}")
            posted += 1
        else:
            dp.log(f"could not post into #{channel}")
    return posted


def _fresh(channel: str, latest: dict) -> bool:
    """Is the newest post still accurate?"""
    blob = (latest.get("content") or "") + json.dumps(latest.get("embeds") or [])
    want = live_summary() if channel == "catalog" else roadmap_summary()
    # the first line is enough: the list changes, the heading does not
    return want.split("\n")[0].strip() in blob or len(blob) > 40 and \
        bool(want) and want[:30] in blob


def check() -> int:
    """Report any channel that is still empty."""
    empty = []
    for channel in INTRO:
        if not dp.find_channel(channel):
            empty.append(f"#{channel} (missing)")
            continue
        if not dp.messages(channel, 1):
            empty.append(f"#{channel} (empty)")
    if not empty:
        dp.log(f"ok: all {len(INTRO)} channels have content")
        return 0
    dp.log("channels with nothing in them:")
    for e in empty:
        print(f"  - {e}")
    return 1


def main() -> int:
    dry = "--dry-run" in sys.argv
    if "--check" in sys.argv:
        return check()
    n = fill(dry)
    print(f"[intro] {'would post to' if dry else 'posted into'} {n} channel(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())