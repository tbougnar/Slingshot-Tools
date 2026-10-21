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
    """Only an itch.io page for an actual product, so a buy button cannot be
    pointed at a stranger or at the account's own front page.

    The old check was len(path.split("/")) >= 1. For "https://slug.itch.io/"
    the path is "/", so strip("/") is "" and "".split("/") is [""], which has
    length one and passed. That let the account page be stored as a product's
    URL. The site then advertised a paid edition whose Buy button went to a
    store listing nothing at all, and the paid tier was marked published.

    A product page has a non-empty first path segment: the project's slug.
    """
    u = urlparse(url)
    if u.scheme != "https" or not u.netloc.endswith("itch.io"):
        return False
    # A buy button belongs to one account, which is a subdomain. Accepting the
    # bare itch.io host would point a purchase at the site itself.
    if u.netloc == "itch.io":
        return False
    segments = [s for s in u.path.split("/") if s]
    return len(segments) >= 1


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
        # Only the paid edition gets a store URL. The free edition is a
        # download from this site, and giving it a store URL puts a buy
        # button on a product that is free, which is the state the audit
        # closed: a free edition advertising itself as something to buy.
        # set_all() and itch_publish.record() both strip it from the free
        # tier, and this command is the one the release instructions tell
        # the operator to run, so it has to agree with them.
        if (entry.get("tier") or "") == "basic":
            entry.pop("itch_url", None)
            touched.append("basic (cleared)")
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


def set_all(apps: list, url: str) -> int:
    """Point every paid product at one project.

    The store holds one itch.io project and the paid products are builds in
    it, so those entries get the same URL. The free editions are deliberately
    not given one: they are served from this site and have never been uploaded
    to itch.io, so recording a store URL for them is a claim that is not true.
    A free app that later needs a store of its own gets one explicitly.

    Only itch_url is written here. Nothing is marked published, because a Buy
    button that leads to a project without that product's build is the
    advertising this audit spent most of its effort removing. Each product
    becomes purchasable when its own build is uploaded and the page answers.
    """
    if not valid(url):
        log(f"{url!r} is not an https itch.io page")
        return 1
    free = [e for e in apps if e.get("tier") == "basic"]
    paid = [e for e in apps if e.get("tier") != "basic"]
    for entry in paid:
        entry["itch_url"] = url
    # clear a stale store URL from the free editions, which should never have
    # one, so nothing claims they are on itch.io when they are not
    for entry in free:
        entry.pop("itch_url", None)
    if not paid:
        log("the catalogue has no paid editions, so there is nothing to point")
        return 1
    slugs = sorted({(a.get("base_slug") or a.get("slug")) for a in paid})
    save(apps)
    log(f"{len(slugs)} paid products now point at {url}")
    log(f"updated {len(paid)} paid entries; {len(free)} free editions left"
        " without a store URL, because they are not on itch.io")
    log("none are marked published yet: each becomes purchasable when its")
    log("own build is uploaded and the project page answers")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv[1:]:
        urls = [a for a in args if a.startswith("https://")]
        if len(urls) != 1:
            log("usage: python set_itch_url.py --all <https://...itch.io/page>")
            return 1
        return set_all(load(), urls[0])
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