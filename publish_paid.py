"""Show a product in the catalog, once it is actually for sale on itch.io.

Used to be done automatically the moment the build reached Cloudflare. It is not
any more: the paid file lives on itch.io, and only a human can upload it. So
this is run by hand after the upload, and it refuses unless the itch.io URL is
already in the catalog.

    python publish_paid.py password-manager
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import auditlog

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"


def log(msg: str) -> None:
    print(f"[publish] {msg}", flush=True)


def load() -> list:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[publish] cannot read the catalog: {e}")


def main() -> int:
    if len(sys.argv) < 2:
        log("usage: python publish_paid.py <slug>")
        return 1
    slug = sys.argv[1].strip()

    apps = load()
    family = [a for a in apps
              if (a.get("base_slug") or a.get("slug")) == slug]
    if not family:
        log(f"{slug} is not in the catalog")
        return 1

    paid = next((a for a in family if a.get("tier") == "full"), None)
    if paid is None:
        log(f"{slug} has no paid tier")
        return 1

    url = paid.get("itch_url") or ""
    if not url:
        log(f"{slug} has no itch_url yet, so it cannot be shown for sale")
        log(f"run:  python set_itch_url.py {slug} <https://yourslug.itch.io/...>")
        auditlog.blocked("publish-paid", job=slug,
                         reason="no itch_url recorded for the paid tier")
        return 1

    # A URL that passes the shape check is not proof the page exists. This one
    # pointed at the account's own front page, which is a valid itch.io URL
    # with no product on it, and the site advertised a Buy button that went
    # nowhere while the tier was marked published. The page has to be fetched
    # and shown to be a product page before anything is claimed to be on sale.
    from urllib.parse import urlparse as _urlparse
    _u = _urlparse(url)
    _segments = [s for s in _u.path.split("/") if s]
    if len(_segments) < 1:
        log(f"{url} is the account page, not a product page")
        log("a buy button must go to https://yourslug.itch.io/the-product")
        auditlog.failed("publish-paid", job=slug,
                        error="itch_url is the account page, not a product",
                        evidence={"itch_url": url})
        return 1

    # Beyond the shape: does the page actually answer, and does it look like a
    # product rather than an account? An itch.io account page has no download
    # section. This is the independent check the audit requires before anything
    # is claimed to be purchasable.
    try:
        import urllib.request
        _req = urllib.request.Request(
            url, headers={"User-Agent": "slingshot-publish-check"})
        with urllib.request.urlopen(_req, timeout=30) as _r:
            _body = _r.read(200000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log(f"could not open {url} to confirm it: {str(e)[:90]}")
        auditlog.not_verified("publish-paid", job=slug,
                              reason=f"could not fetch {url}: {str(e)[:60]}",
                              evidence={"itch_url": url})
        return 1

    if not any(m in _body for m in ("download", "Buy", "purchase")):
        log(f"{url} answered but does not look like a product page")
        log("nothing is marked on sale until it does")
        auditlog.failed("publish-paid", job=slug,
                        error="the itch.io page has no purchase or download "
                              "section, so it is not a product page",
                        evidence={"itch_url": url, "bytes": len(_body)})
        return 1

    # The page having a download section is not enough. The store is ONE
    # itch.io project holding every product, so the word "download" is on
    # that page for every slug forever, and the check above passed for a
    # product that had never been uploaded. What has to be there is THIS
    # product's own installer, by name, the way a buyer would see it. The
    # publisher already works this way, with build_is_listed.
    import itch_publish as ip

    names = []
    for cand in (paid.get("title"), slug):
        if cand:
            names.append(f"{cand}-Setup.exe")
            names.append(f"SlingshotTool-{cand}-Setup.exe")
    listed = next((n for n in names if ip.build_is_listed(url, n)), "")
    if not listed:
        log(f"{url} does not list {slug}'s own installer, so there is "
            "nothing to sell")
        log("it looked for: " + ", ".join(names[:4]))
        log("another product's build on the same page is not this product's, "
            "so nothing is marked on sale")
        auditlog.failed("publish-paid", job=slug,
                        error="the itch.io page does not list this product's "
                              "own build, so there is nothing to buy",
                        evidence={"itch_url": url, "looked_for": names[:4]})
        return 1
    log(f"the page lists {listed}, which is this product's build")

    price = float(paid.get("price") or 0)
    if not (1.0 <= price <= 10.0):
        log(f"the price ${price:.2f} is outside the $1-$10 rule, refusing")
        auditlog.blocked("publish-paid", job=slug,
                         reason=f"price ${price:.2f} is outside the $1-$10 rule",
                         evidence={"price": price})
        return 1

    changed = False
    for entry in family:
        if entry.get("published") is not True:
            entry["published"] = True
            changed = True

    if not changed:
        log(f"{slug} is already published")
        return 0

    CATALOG.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    log(f"{slug} is now live at ${price:.2f}")
    log(f"  free : {next((a.get('url') for a in family if a.get('tier') == 'basic'), '(none)')}")
    log(f"  full : {url}")
    # The one action in this repository that puts a product on sale for money
    # was the only one that wrote no audit event. Every failure path did, so
    # the trail showed attempts that all failed and never a sale.
    auditlog.succeeded("publish-paid", job=slug,
                       evidence={"price": price, "itch_url": url,
                                 "build": listed, "exit_code": 0})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())