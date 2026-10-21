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
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import set_itch_url
import publish_paid

# This suite drives publish_paid through several failure paths on purpose, so
# it must not write BLOCKED and FAILED events into the real audit log. A log
# full of test failures is not evidence of anything.
import auditlog as _auditlog

_real_log = _auditlog.LOG
_auditlog.LOG = Path(tempfile.mkdtemp(prefix="itchurl-selftest-")) \
    / "events.jsonl"

# links.py deliberately links the store as navigation. That is correct, and it
# is not a product URL, so it is named rather than flagged.
ALLOWED_STORE_LINK = "links.py"


def sources_of(name: str) -> str:
    """File contents with comment-only lines removed.

    The comment explaining the old bug names the very URL that must no longer
    appear in code. Reading the raw file flags the explanation of the fix as if
    it were the fix.
    """
    lines = (ROOT / name).read_text(encoding="utf-8",
                                    errors="replace").splitlines()
    return "\n".join(ln for ln in lines
                     if not ln.lstrip().startswith("#"))


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

# The other direction, which is the one that matters for a free edition. A
# free edition is a download from this site; it has never been uploaded to
# itch.io, so a store URL on it is a claim that is not true, and the site
# then offers a buy button for something that is free. set_all() and
# itch_publish.record() both strip it, but set_url() did not, and that is
# the command the release instructions tell the operator to run.
free_with_store = [a["slug"] for a in catalog
                   if a.get("tier") == "basic" and a.get("itch_url")]
check("no free edition carries a store URL", not free_with_store,
      str(free_with_store[:4]))

print("\nNO CODE SUBSTITUTES AN ACCOUNT PAGE FOR A PRODUCT\n")
# pricing.py filled every entry without an itch_url with the account front page
# on every run, which put the dead end back within one cycle of it being fixed.
# A test on the validator alone would not have caught that. Searching source
# text for "itch.io" is useless here: the API host, the butler download and
# every log message mention it, and none of those is a product URL. So this
# looks at the one assignment that matters, through the syntax tree.
import ast

problems = []
for f in sorted(ROOT.glob("*.py")):
    if f.name.endswith("_selftest.py"):
        continue
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [ast.unparse(t) for t in node.targets]
        if not any("itch_url" in t for t in targets):
            continue
        # walk every string constant reachable from the assigned value
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                if re.match(r"^https://[a-z0-9\-]+\.itch\.io/?$", sub.value):
                    problems.append(f"{f.name}:{sub.lineno} assigns {sub.value}")

check("no module assigns an account front page to itch_url", not problems,
      "; ".join(problems[:3]))

# A store URL read from the environment is the same claim, and the test
# above cannot see it, because it looks for a literal URL and this is a
# value read at run time. pricing.py had one, and it applied to every entry
# including the free editions, so a single variable put a buy button on
# every free product in the catalogue.
env_fill = []
for f in sorted(ROOT.glob("*.py")):
    if f.name.endswith("_selftest.py"):
        continue
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [ast.unparse(t) for t in node.targets]
        if not any("itch_url" in t for t in targets):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr in ("get", "getenv"):
                if isinstance(sub.func.value, ast.Attribute) \
                        and sub.func.value.attr == "environ":
                    env_fill.append(f"{f.name}:{getattr(sub, 'lineno', '?')}")

check("no module fills itch_url from the environment", not env_fill,
      "; ".join(env_fill[:3]))

pricing_src = sources_of("pricing.py")
check("pricing.py has no hardcoded itch.io URL at all",
      "https://slingshot-tools.itch.io/" not in pricing_src,
      "it still names the account page somewhere in code")

check("the store navigation link is still there",
      "slingshot-tools.itch.io" in sources_of(ALLOWED_STORE_LINK),
      "linking your own store from the footer is correct and was not lost")

check("the release gate rejects a non-product itch_url",
      "is not a product page" in sources_of("check_exposure.py"),
      "nothing stops a bad URL being written")

_auditlog.LOG = _real_log

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)