"""A buy button must never point at a page with nothing on it.

The site advertised a paid edition marked published, whose itch_url was the
account's own front page. That URL is a perfectly valid itch.io URL: the
validator required at least one path segment, and "".split("/") is [""],
which has length one. So the check passed, the tier was marked published, and
a customer clicking Buy arrived at a store listing nothing.

The real itch.io store was fetched and confirmed empty during the audit, so
this is not a theoretical shape problem.

publish_paid.py now refuses on two independent grounds: the URL has to name a
product rather than an account, and the page has to be fetched and shown to
contain a purchase or download section.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import set_itch_url
import publish_paid

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


print("\nONLY A PRODUCT PAGE IS A VALID ITCH URL\n")
cases = [
    ("https://slingshot-tools.itch.io/", False, "the account front page"),
    ("https://slingshot-tools.itch.io", False, "no path at all"),
    ("https://slingshot-tools.itch.io/", False, "trailing slash only"),
    ("https://slingshot-tools.itch.io/pm", True, "a product page"),
    ("https://slingshot-tools.itch.io/pm/", True, "a product page, trailing slash"),
    ("http://x.itch.io/pm", False, "not https"),
    ("https://evil.com/pm", False, "not itch.io"),
    ("https://itch.io/pm", False, "the bare itch.io domain"),
]
for url, want, why in cases:
    got = set_itch_url.valid(url)
    check(f"{'accepts' if want else 'rejects'} {url:44s} ({why})",
          got == want, f"valid() returned {got}")

print("\nPUBLISHING REFUSES AN ACCOUNT PAGE\n")
tmp = Path(tempfile.mkdtemp())
real_catalog = publish_paid.CATALOG
publish_paid.CATALOG = tmp / "apps.json"
try:
    catalog = [
        {"slug": "thing", "tier": "full", "price": 3.0, "published": False,
         "itch_url": "https://shop.itch.io/"},
        {"slug": "thing-basic", "tier": "basic", "price": 0, "published": True,
         "base_slug": "thing"},
    ]
    publish_paid.CATALOG.write_text(json.dumps(catalog), encoding="utf-8")

    sys.argv = ["publish_paid.py", "thing"]
    rc = publish_paid.main()
    check("refuses to mark an account page as on sale", rc == 1, f"rc={rc}")

    after = json.loads(publish_paid.CATALOG.read_text(encoding="utf-8"))
    paid = next(a for a in after if a["tier"] == "full")
    check("and the catalog is left unpublished", paid.get("published") is False,
          f"published={paid.get('published')}")

    # the file must not even have been rewritten
    check("and nothing was written", paid.get("itch_url") == "https://shop.itch.io/")

    # a product URL that does not answer is NOT_VERIFIED, not a silent pass
    catalog[0]["itch_url"] = "https://slingshot-tools.itch.io/does-not-exist-xyz"
    publish_paid.CATALOG.write_text(json.dumps(catalog), encoding="utf-8")
    rc = publish_paid.main()
    after = json.loads(publish_paid.CATALOG.read_text(encoding="utf-8"))
    paid = next(a for a in after if a["tier"] == "full")
    check("a page that does not answer is not published",
          paid.get("published") is False, f"rc={rc}")
finally:
    publish_paid.CATALOG = real_catalog

print("\nTHE LIVE CATALOG DOES NOT CLAIM SOMETHING IS ON SALE\n")
catalog = json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
lying = [a["slug"] for a in catalog
         if a.get("tier") == "full" and a.get("published") is True
         and not a.get("itch_url")]
check("no paid tier is published without an itch_url", not lying, str(lying))

account_only = [a["slug"] for a in catalog
                if a.get("itch_url") and not set_itch_url.valid(a["itch_url"])]
check("no catalog entry holds an itch_url that is not a product page",
      not account_only, str(account_only))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)