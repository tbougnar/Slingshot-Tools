"""Point a product at its itch.io page.

The site has no checkout of its own any more: itch.io takes the payment and
hands over the paid file. So all that is needed per product is the URL of its
itch.io project, and this writes it into the catalog.

    python set_itch_url.py password-manager https://yourslug.itch.io/offline-password-manager

Both editions of the family get the URL, because they are one product as far
as a buyer is concerned. A product with no URL stays unpublished rather than
showing a button that leads nowhere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"


def log(msg: str) -> None:
    print(f"[itch] {msg}", flush=True)


def load() -> list:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[itch] cannot read the catalog: {e}")
    return data if isinstance(data, list) else []


def save(apps: list) -> None:
    CATALOG.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")


def valid(url: str) -> bool:
    """Only an itch.io page, so a typo cannot point a buy button at a stranger."""
    u = urlparse(url)
    return u.scheme == "https" and u.netloc.endswith("itch.io") \
        and len(u.path.strip("/").split("/")) >= 1


def show(apps: list) -> int:
    print(f"{'product':<26} {'price':>7}  itch.io page")
    print("-" * 76)
    for slug in sorted({(a.get("base_slug") or a.get("slug")) for a in apps}):
        family = [a for a in apps
                  if (a.get("base_slug") or a.get("slug")) == slug]
        paid = next((a for a in family if a.get("tier") == "full"), {})
        price = float(paid.get("price") or 0)
        url = paid.get("itch_url") or ""
        print(f"{slug:<26} ${price:>6.2f}  {url or '(not set yet)'}")
    return 0


def set_url(apps: list, slug: str, url: str) -> int:
    if not valid(url):
        log(f"{url!r} is not an https itch.io page")
        log("expected something like https://yourslug.itch.io/your-tool")
        return 1

    touched = []
    for entry in apps:
        if (entry.get("base_slug") or entry.get("slug")) != slug:
            continue
        entry["itch_url"] = url
        touched.append(entry.get("tier") or "?")

    if not touched:
        log(f"{slug} is not in the catalog")
        log("known products: " + ", ".join(sorted(
            {a.get("base_slug") or a.get("slug") for a in apps})))
        return 1

    save(apps)
    log(f"{slug} now points at {url}")
    log(f"updated {len(touched)} entries ({', '.join(sorted(touched))})")

    # say what to do next, because the page has to exist before this matters
    family = [a for a in apps
              if (a.get("base_slug") or a.get("slug")) == slug]
    paid = next((a for a in family if a.get("tier") == "full"), {})
    if paid.get("published") is not True:
        log("the paid tier is not published yet, so the button still says "
            "'coming soon'")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        return show(load())
    if len(args) < 2:
        log("usage: python set_itch_url.py <slug> <https://...itch.io/page>")
        return 1
    slug, url = args[0], args[1]
    if url.startswith("http://") or "itch.io/" not in url:
        log("that does not look like an itch.io page link")
    return set_url(load(), slug, url)


if __name__ == "__main__":
    raise SystemExit(main())