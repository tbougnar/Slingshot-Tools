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

**What the full edition adds**
The full edition is a native Windows app: a real installer, a desktop shortcut,
and no browser tab to hunt down. It also carries the extra features listed on
the product page.

**Get it**
- Free: {free_url}
- Full edition: {buy_url}

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
    return FALLBACK.format(
        title=tool.get("title", "Slingshot Tool"),
        blurb=tool.get("blurb", "A small, focused tool."),
        tag_title=tag_title,
        free_url=tool.get("free_url") or dd.SITE_URL,
        buy_url=tool.get("buy_url") or f"{dd.SITE_URL}/checkout.html",
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
        model = os.environ.get("ARTICLE_MODEL") or "openai/gpt-oss-20b"
        body = providers.groq_chat(
            model=model,
            system=("You write short product announcements for a Discord "
                    "server. Plain markdown, no emoji, no preamble, never "
                    "invent features that were not described to you."),
            user=(
                "Write a short article for this tool. Cover what problem it "
                "solves, what the free edition does, and what the full "
                f"edition adds. Under 220 words.\n\n"
                f"Title: {tool.get('title')}\n"
                f"Summary: {tool.get('blurb')}\n"
                f"Tags: {', '.join(tool.get('tags') or [])}\n"
                f"Price: ${tool.get('price', 0):.2f}\n"
                f"Free download: {tool.get('free_url')}"),
            temperature=0.4,
            max_tokens=700,
        )
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
    if os.environ.get("GROQ_API_KEY"):
        body = clean(_model_article(tool))
    if not body:
        body = fallback_article(tool)
        log("using the deterministic write-up")

    dd.save_article(tool["base"], body)
    log(f"wrote {len(body)} characters for {tool['base']}")

    if dry:
        print(json.dumps(article_message(tool, body), indent=2,
                         ensure_ascii=False))
        return 0

    # only advertise the paid edition once it is genuinely on sale
    if not tool.get("buy_url"):
        log("paid tier is not live yet - not posting the article")
        return 0

    if dp.post("articles", article_message(tool, body)):
        log(f"posted {tool['base']} to #articles")
    else:
        log(f"article saved but not posted (discord: {dp.describe()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())