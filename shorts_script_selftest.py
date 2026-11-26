"""The narration must never carry the brand name or a price.

Both are on screen where they belong. Spoken, a brand name is a name the
viewer does not care about yet, and a spoken price fights the voice for
attention and is forgotten. The model is told to avoid both; this checks that
it actually did, because a model that ignores an instruction silently is the
normal case, not the exception.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

import shorts_script as ss

fails = []

RECORD = {"name": "Password Manager", "title": "Offline password manager",
          "price": 3.0}

cases = [
    ("brand in the hook", {
        "hook": "Password Manager keeps your logins safe.",
        "problem": "You reset forgotten passwords every week.",
        "proof": "It stores them offline on your own disk.",
        "ask": "Download it free to try."}),
    ("price in the proof", {
        "hook": "Forgotten passwords are brutal.",
        "problem": "You lose logins and reset emails every week.",
        "proof": "It stores everything offline for $3.",
        "ask": "Download it free to try."}),
    ("both", {
        "hook": "Password Manager costs $3.",
        "problem": "You keep losing logins.",
        "proof": "It saves them offline.",
        "ask": "Try it free."}),
]

for label, payload in cases:
    d = ss._clean(json.dumps(payload), RECORD)
    blob = " ".join(str(v) for v in d.values() if isinstance(v, str))
    bad = []
    if "password manager" in blob.lower():
        bad.append("brand")
    if "$3" in blob or "3 dollars" in blob.lower():
        bad.append("price")
    ok = not bad
    print(("ok   " if ok else "FAIL "), f"{label}: {d['hook'][:46]}")
    if not ok:
        print(f"        leaked {bad}")
        fails.append(label)

# a good script must survive untouched
good = {"hook": "Forgotten passwords are brutal.",
        "problem": "You lose logins and reset emails every week.",
        "proof": "This one keeps everything offline.",
        "ask": "Download it free to try."}
d = ss._clean(json.dumps(good), RECORD)
ok = (d["hook"] == good["hook"] and d["proof"] == good["proof"]
      and len(ss.lines(d)) == 4)
print(("ok   " if ok else "FAIL "), "a clean script is not mangled")
if not ok:
    fails.append("clean script")

# A fresh Actions checkout has no gitignored published.json. The Shorts job
# must still find the newest product that is genuinely on sale, and must not
# fall back to a draft just because it has a later date.
_tmp = pathlib.Path(tempfile.mkdtemp(prefix="shorts-product-"))
(_tmp / "site").mkdir(parents=True)
(_tmp / "site" / "apps.json").write_text(json.dumps([
    {"slug": "older", "base_slug": "older", "tier": "full",
     "published": True, "itch_url": "https://example.test/p",
     "date": "2026-01-01", "title": "Older", "price": 3.0},
    {"slug": "newer", "base_slug": "newer", "tier": "full",
     "published": True, "itch_url": "https://example.test/p",
     "date": "2026-11-25", "title": "Newer", "price": 3.0},
    {"slug": "draft", "base_slug": "draft", "tier": "full",
     "published": False, "date": "2026-12-01", "title": "Draft", "price": 3.0},
]), encoding="utf-8")
_real_root, _old_slug = ss.ROOT, os.environ.get("SHORTS_SLUG")
try:
    ss.ROOT = _tmp
    os.environ["SHORTS_SLUG"] = ""
    got = ss.product()
    ok = got.get("slug") == "newer" and got.get("price") == 3.0
    print(("ok   " if ok else "FAIL "),
          "a fresh checkout finds the newest product on sale")
    if not ok:
        fails.append("catalog fallback")

    os.environ["SHORTS_SLUG"] = "older"
    got = ss.product()
    ok = got.get("slug") == "older"
    print(("ok   " if ok else "FAIL "),
          "an explicit slug picks that published product")
    if not ok:
        fails.append("explicit slug")

    os.environ["SHORTS_SLUG"] = "draft"
    refused = False
    try:
        ss.product()
    except SystemExit:
        refused = True
    ok = refused
    print(("ok   " if ok else "FAIL "),
          "a product that is not on sale is never advertised")
    if not ok:
        fails.append("draft refused")
finally:
    ss.ROOT = _real_root
    if _old_slug is None:
        os.environ.pop("SHORTS_SLUG", None)
    else:
        os.environ["SHORTS_SLUG"] = _old_slug
    shutil.rmtree(_tmp, ignore_errors=True)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)