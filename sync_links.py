"""Write the brand's link row into the site and the Discord welcome.

The four surfaces are generated from links.py so they cannot drift. Run after
changing a URL:

    python sync_links.py

It is idempotent: running it twice changes nothing the second time, which is
what makes it safe to wire into the deploy step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import links

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site" / "index.html"

MARK = "site-links"          # the class links.py emits
BEGIN = "  <!-- slingshot-links:start -->"
END = "  <!-- slingshot-links:end -->"


def log(m: str) -> None:
    print(f"[links] {m}", flush=True)


def block() -> str:
    return (f"{BEGIN}\n  <style>{links.css()}</style>\n"
            f"{links.footer_html()}\n{END}")


def sync_site(html: Path = SITE) -> bool:
    """Put the link row inside the footer, replacing any previous one."""
    if not html.exists():
        log(f"{html} is not there, nothing to do")
        return False

    text = html.read_text(encoding="utf-8")
    if MARK not in text and "<!-- slingshot-links" not in text:
        # first run: find the footer and put the row inside it
        m = re.search(r"(<footer[^>]*>)(.*?)(</footer>)", text, re.S)
        if not m:
            log("no footer in the page, so the links were not added")
            return False
        inner = m.group(2)
        text = text[:m.start(2)] + inner + "\n      " + block() \
            + text[m.end(2):]
        html.write_text(text, encoding="utf-8")
        log("added the link row to the footer")
        return True

    # already there: swap the contents between the markers
    pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if not pat.search(text):
        log("the markers are missing, so the links were not refreshed")
        return False
    new = pat.sub(block(), text)
    if new == text:
        log("the footer links were already up to date")
        return False
    html.write_text(new, encoding="utf-8")
    log("refreshed the link row in the footer")
    return True


def discord_payload() -> str:
    """The welcome text, written where the bot can pick it up."""
    dest = ROOT / "data" / "discord_welcome.txt"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(links.discord_welcome(), encoding="utf-8")
    log(f"wrote {dest.relative_to(ROOT)}")
    return links.discord_welcome()


def youtube_sample() -> str:
    """A description with every link in it, for checking by eye."""
    import shorts_script as ss
    p = ss.product()
    return links.youtube_description(
        p.get("name") or "Slingshot Tool",
        ss.price_label(p.get("price")),
        p.get("blurb") or "")


def main() -> int:
    sync_site()
    discord_payload()
    log("")
    log("the YouTube description looks like this:")
    for line in youtube_sample().splitlines():
        log(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())