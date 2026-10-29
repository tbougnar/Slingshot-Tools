"""Post the article for a published tool to #articles, and keep it in the repo.

Writing and posting are separate concerns: the text goes into
discord_articles.json (public, committed, readable by /article anywhere) and
the Discord post is best-effort, because a Discord outage must never fail a
release.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import discord_data as dd
import discord_post as dp

ROOT = Path(__file__).resolve().parent

FALLBACK = """**{title}** — {blurb}

**Why it exists**
{tag_title} is one of those small irritations that eats a little attention every
single day. This is a single-purpose tool for it: no setup, no sign-in, no
network calls. Open the page and it works.

**What the free edition does**
Everything you need for the job itself. It runs straight in the browser and
your data never leaves your device.
{paid_section}
**Get it**
- Free: {free_url}
{full_section}
One new tool lands every month. Use `/vote` in the server to pick what comes
next.
"""


def log(msg: str) -> None:
    print(f"[article] {msg}", flush=True)


def clean(body: str) -> str:
    """Trim to something that reads like prose, not a model transcript."""
    text = (body or "").strip()
    if not text:
        return ""
    # drop markdown fences and any leading "here is..." preamble
    text = re.sub(r"^```[a-z]*\n|\n```$", "", text).strip()
    text = re.sub(r"^(here(?:'s| is).*?:)\s*", "", text, flags=re.I)
    # a heading that just repeats the title adds nothing
    text = re.sub(r"^#\s+.+\n+", "", text, count=1)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:6000]


def fallback_article(tool: dict) -> str:
    tag = (tool.get("tags") or ["utility"])[0]
    tag_title = str(tag).replace("-", " ").strip().capitalize() or "This tool"
    # Only mention the paid edition when there is a real page to buy it from.
    # The fallback used to write a link to checkout.html with no product, so a
    # committed article advertised an edition that could not be bought.
    buy = tool.get("buy_url") or ""
    paid_section = (
        "\n**What the full edition adds**\n"
        "The full edition is a native Windows app: a real installer, a desktop "
        "shortcut,\nand no browser tab to hunt down. It also carries the extra "
        "features listed on\nthe product page.\n" if buy else "")
    full_section = f"- Full edition: {buy}\n" if buy else ""
    return FALLBACK.format(
        title=tool.get("title", "Slingshot Tool"),
        blurb=tool.get("blurb", "A small, focused tool."),
        tag_title=tag_title,
        free_url=tool.get("free_url") or dd.SITE_URL,
        paid_section=paid_section,
        full_section=full_section,
    )


def article_message(tool: dict, body: str) -> dict:
    """The article as a Discord embed, split so no embed runs past the limit."""
    head, _, rest = body.partition("\n")
    description = rest.strip() or body
    fields = []
    if tool.get("free_url"):
        fields.append({"name": "Free download",
                       "value": f"[Get it]({tool['free_url']})", "inline": True})
    if tool.get("buy_url"):
        fields.append({"name": "Full edition",
                       "value": f"[Buy ${tool['price']:.2f}]({tool['buy_url']})",
                       "inline": True})
    return dp.embed_message({
        "title": tool.get("title", "Slingshot Tool"),
        "description": description[:4000],
        "url": f"{dd.SITE_URL}/",
        "color": dp.OK,
        "fields": fields,
        "footer": {"text": head.strip()[:200]},
    })


def _model_article(tool: dict) -> str:
    """Ask the builder model for the write-up; any failure is not fatal."""
    try:
        import providers
        model = os.environ.get("ARTICLE_MODEL") or providers.default_model("chat")
        body = providers.chat(
            model,
            ("You write short product announcements for a Discord "
             "server. Plain markdown, no emoji, no preamble, never "
             "invent features that were not described to you."),
            (
                "Write a short article for this tool. Cover what problem it "
                "solves, what the free edition does, and what the full "
                f"edition adds. Under 220 words.\n\n"
                f"Title: {tool.get('title')}\n"
                f"Summary: {tool.get('blurb')}\n"
                f"Tags: {', '.join(tool.get('tags') or [])}\n"
                f"Price: ${tool.get('price', 0):.2f}\n"
                f"Free download: {tool.get('free_url')}"),
            0.7, 900, role="debug")
        return body if isinstance(body, str) else ""
    except Exception as e:  # noqa: BLE001
        log(f"model unavailable ({e})")
        return ""


def main() -> int:
    # the slug is optional, and a flag is never a slug
    dry = "--dry-run" in sys.argv
    slug = next((a for a in sys.argv[1:] if not a.startswith("-")), "").strip()
    if not slug:
        stage = dd._load(dd.PUBLISHED, {})
        slug = stage.get("slug") if isinstance(stage, dict) else ""
    if not slug:
        log("no product to write about")
        return 0

    tool = dd.tool_by_slug(slug)
    if not tool:
        log(f"{slug} is not a live tool")
        return 0

    body = ""
    try:
        import providers
        ready = providers.configured()
    except Exception:  # noqa: BLE001
        ready = False
    if ready:
        body = clean(_model_article(tool))
    if not body:
        body = fallback_article(tool)
        log("using the deterministic write-up")

    # A committed article is public marketing copy. Saving one whose buy link
    # goes nowhere is the same defect as a dead buy button, so nothing is saved
    # or posted until the paid edition is genuinely on sale. A dry run only
    # prints, and is allowed to preview an article before that.
    if not tool.get("buy_url") and not dry:
        log("paid tier is not live yet - not saving or posting the article")
        return 0

    if not dry:
        dd.save_article(tool["base"], body)
        log(f"wrote {len(body)} characters for {tool['base']}")

    if dry:
        print(json.dumps(article_message(tool, body), indent=2,
                         ensure_ascii=False))
        return 0

    if dp.post("articles", article_message(tool, body)):
        log(f"posted {tool['base']} to #articles")
    else:
        log(f"article saved but not posted (discord: {dp.describe()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())