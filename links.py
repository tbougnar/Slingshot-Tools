"""One place that knows every URL the brand lives at.

Four surfaces need the same four links, and they drift apart the moment each
one carries its own copy. The website footer, the Discord welcome message, the
YouTube description and the Short's end card all read from here instead, so
adding a channel means editing one list.

The URLs come from the environment with sensible defaults, because the repo is
public and the Discord invite in particular rotates.
"""
from __future__ import annotations

import os

REPO = os.environ.get("GITHUB_REPO", "tbougnar/Slingshot-Tools")
OWNER, NAME = (REPO.split("/", 1) + [""])[:2]

# The order matters: it is the order they appear everywhere.
CHANNELS = [
    {
        "key": "website",
        "label": "Website",
        # the store page is the site; the site links back out
        "url": os.environ.get("SITE_URL", "").strip()
        or "https://tbougnar.github.io/Slingshot-Tools/",
        "icon": "globe",
        "primary": True,
    },
    {
        "key": "itch",
        "label": "itch.io",
        # the main store page, not one product
        "url": os.environ.get("ITCH_STORE_URL", "").strip()
        or "https://slingshot-tools.itch.io/",
        "icon": "bag",
        "primary": True,
    },
    {
        "key": "youtube",
        "label": "YouTube",
        "url": os.environ.get("YOUTUBE_CHANNEL_URL", "").strip()
        or "https://www.youtube.com/@Slingshot_Tools",
        "icon": "play",
    },
    {
        "key": "discord",
        "label": "Discord",
        # the invite. Discord expires these, so the expiry is watched by
        # check_links.py rather than trusted.
        "url": os.environ.get("DISCORD_INVITE_URL", "").strip()
        or "https://discord.gg/uajfhbkMY",
        "icon": "chat",
    },
    {
        "key": "github",
        "label": "GitHub",
        "url": f"https://github.com/{OWNER}/{NAME}",
        "icon": "code",
    },
]


def by_key(key: str) -> dict:
    for c in CHANNELS:
        if c["key"] == key:
            return c
    raise KeyError(key)


def url(key: str) -> str:
    return by_key(key)["url"]


def all_links() -> list[dict]:
    return list(CHANNELS)


def footer_html() -> str:
    """The link row for the site, in the order the brand wants them read."""
    icons = {
        "globe": ("M12 2a10 10 0 100 0 10 10 0 000-20zm0 0c2.5 2.4 3.8 5.6 "
                  "3.8 10S14.5 19.6 12 22m0-20C9.5 4.4 8.2 7.6 8.2 12S9.5 "
                  "19.6 12 22"),
        "bag": ("M6 8h12l1 12H5L6 8zm3 0V6a3 3 0 016 0v2"),
        "play": ("M10 8l6 4-6 4V8zM3 5h18v14H3z"),
        "chat": ("M4 5h16v11H8l-4 4V5z"),
        "code": ("M9 8l-4 4 4 4m6-8l4 4-4 4m-3-10l-2 12"),
    }
    out = ['<nav class="site-links" aria-label="Slingshot Tools">']
    for c in CHANNELS:
        path = icons.get(c["icon"], "")
        prim = ' class="primary"' if c.get("primary") else ""
        out.append(
            f'  <a href="{c["url"]}"{prim} rel="noopener" '
            f'target="_blank" title="{c["label"]}">'
            f'<svg viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{path}" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>'
            f'<span>{c["label"]}</span></a>')
    out.append("</nav>")
    return "\n".join(out)


def css() -> str:
    """Stying for that row, kept beside the markup so they cannot disagree."""
    return """
.site-links {
  display: flex; flex-wrap: wrap; gap: 10px;
  justify-content: center; align-items: center; margin: 28px 0 0;
}
.site-links a {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 16px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.14);
  color: #f5f1ea; text-decoration: none;
  font: 500 14px/1 system-ui, sans-serif; letter-spacing: .02em;
  transition: border-color .18s, background .18s, transform .18s;
}
.site-links a:hover {
  border-color: #e45e5f; background: rgba(228,94,95,.10);
  transform: translateY(-1px);
}
.site-links a.primary { border-color: rgba(228,94,95,.55); }
.site-links svg { width: 18px; height: 18px; flex: none; }
.site-links a.primary svg { color: #e45e5f; }
@media (prefers-reduced-motion: reduce) {
  .site-links a:hover { transform: none; }
}
""".strip()


def discord_welcome() -> str:
    """The message posted when someone joins, carrying every link out.

    Discord is where the audience already is, so it is the one surface that
    should name the store, the videos and the code rather than assume people
    found them.
    """
    lines = [
        "Welcome to **Slingshot Tools**.",
        "",
        "Everything we make is here, and everything here links to everything "
        "else:",
        "",
    ]
    for c in CHANNELS:
        lines.append(f"{c['label']}  ->  {c['url']}")
    lines += [
        "",
        "Vote on what gets built next in #polls, and read the weekly notes in "
        "#announcements.",
    ]
    return "\n".join(lines)


def youtube_description(name: str = "", price: str = "",
                       blurb: str = "") -> str:
    """Every link, in the order a viewer wants them after watching.

    Written for a phone screen: short lines, one idea each, and marks that
    survive being skimmed rather than read. The links sit last because they are
    the action, not the pitch.
    """
    head = name or "Slingshot Tools"
    out = [
        f"⚡ {head}",
        "",
    ]
    if blurb:
        # the blurb is written for the catalogue, so it is shortened to one
        # readable line rather than pasted whole
        one = " ".join(blurb.split())
        if len(one) > 150:
            one = one[:147].rsplit(" ", 1)[0] + "..."
        out += [one, ""]
    if price:
        out += [f"💰 {price} — one off, yours forever", ""]
    out += [
        "🔒 What it does:",
        "  • Runs on your own device, nothing sent anywhere",
        "  • Works with no internet connection",
        "  • Export your data whenever you want",
        "",
        "⬇️ Get it:",
    ]
    for c in CHANNELS:
        if c["key"] == "youtube":
            continue
        mark = {"website": "🌐", "itch": "🛍️", "discord": "💬",
                "github": "💻"}.get(c["key"], "🔗")
        out.append(f"  {mark} [{c['label']}]({c['url']})")
    out += ["", "#shorts #productivity #software #privacy"]
    return "\n".join(out)


if __name__ == "__main__":
    for c in CHANNELS:
        print(f"  {c['label']:10} {c['url']}")