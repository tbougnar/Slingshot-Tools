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
        return 1

    price = float(paid.get("price") or 0)
    if not (1.0 <= price <= 10.0):
        log(f"the price ${price:.2f} is outside the $1-$10 rule, refusing")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())