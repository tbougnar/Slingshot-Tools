"""Announce a newly published Slingshot Tool in Discord.

Runs after the Windows installer publishes the paid edition, so the message
only goes out once the product is genuinely buyable. Posts a rich embed to a
Discord channel webhook.

The webhook is optional: with no DISCORD_WEBHOOK_URL configured this exits
cleanly and the publish pipeline carries on untouched.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
PUBLISHED = ROOT / "data" / "published.json"
SENT = ROOT / "data" / "discord_sent.json"

SITE_URL = (os.environ.get("SITE_URL")
            or "https://tbougnar.github.io/Slingshot-Tools").rstrip("/")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

BRAND = 0xC1272D
OK = 0x2ECC71


def log(msg: str) -> None:
    print(f"[discord] {msg}", flush=True)


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _sent() -> set:
    data = _load(SENT, {})
    return set(data if isinstance(data, dict) else [])


def _remember(slug: str) -> None:
    data = _load(SENT, {})
    if not isinstance(data, dict):
        data = {}
    data[slug] = True
    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _product(slug: str) -> dict | None:
    """Collect the full and basic catalog entries for one product family."""
    catalog = _load(CATALOG, [])
    if not isinstance(catalog, list):
        return None
    family = [a for a in catalog
              if (a.get("base_slug") or a.get("slug")) == slug]
    if not family:
        return None
    full = next((a for a in family if a.get("tier") == "full"), None)
    basic = next((a for a in family if a.get("tier") == "basic"), None)
    return {"full": full, "basic": basic,
            "title": (full or basic).get("title", slug),
            "price": (full or {}).get("price", 0.0)}


def build_embed(prod: dict) -> dict:
    """Render the product as a Discord embed."""
    full = prod.get("full") or {}
    basic = prod.get("basic") or {}
    title = prod["title"]
    price = float(prod.get("price") or 0)

    fields = []
    if basic.get("url"):
        fields.append({
            "name": "Free edition",
            "value": f"[Download free]({basic['url']}) - $0",
            "inline": True,
        })
    if full.get("price") is not None and price > 0:
        fields.append({
            "name": "Full edition",
            "value": f"**${price:.2f}** - Windows installer",
            "inline": True,
        })
    if basic.get("url"):
        fields.append({
            "name": "Browse",
            "value": f"[All tools]({SITE_URL}/)",
            "inline": True,
        })

    tags = full.get("tags") or basic.get("tags") or []
    footer = "Slingshot Tools" + ("  |  " + " / ".join(tags[:3]) if tags else "")
    blurb = full.get("blurb") or basic.get("blurb") or ""

    return {
        "username": "Slingshot Tools",
        "avatar_url": f"{SITE_URL}/icon-512.png",
        "embeds": [{
            "title": f"New tool: {title}",
            "description": blurb or "A new free tool is live.",
            "url": f"{SITE_URL}/",
            "color": OK,
            "fields": fields,
            "footer": {"text": footer},
            "timestamp": full.get("date") or None,
        }],
        # keeps the channel tidy when several tools land at once
        "allowed_mentions": {"parse": []},
    }


def post(payload: dict) -> bool:
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "slingshot-tools/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        log(f"discord rejected the message: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        log(f"discord unreachable: {e}")
    return False


def main() -> int:
    # --dry-run prints the payload instead of posting it, so the message can
    # be checked before a webhook is connected.
    if "--dry-run" in sys.argv:
        stage = _load(PUBLISHED, {})
        slug = stage.get("slug") if isinstance(stage, dict) else None
        if not slug:
            print("[discord] no published product to preview")
            return 0
        prod = _product(slug)
        if not prod:
            print(f"[discord] {slug} is not in the catalog")
            return 1
        print(json.dumps(build_embed(prod), indent=2, ensure_ascii=False))
        return 0

    if not WEBHOOK:
        log("no DISCORD_WEBHOOK_URL set - nothing to do")
        return 0

    stage = _load(PUBLISHED, {})
    slug = stage.get("slug") if isinstance(stage, dict) else None
    if not slug:
        log("no published product to announce")
        return 0

    if slug in _sent():
        log(f"{slug} was already announced - skipping")
        return 0

    prod = _product(slug)
    if not prod:
        log(f"{slug} is not in the catalog - skipping")
        return 0

    if (prod.get("full") or {}).get("published") is not True:
        # never advertise a paid edition that is not actually on sale
        log(f"{slug} paid tier is not live yet - not announcing")
        return 0

    if post(build_embed(prod)):
        _remember(slug)
        log(f"announced {slug} ({prod['title']})")
        return 0
    log("announcement failed - will retry next run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
