"""The narration must never carry the brand name or a price.

Both are on screen where they belong. Spoken, a brand name is a name the
viewer does not care about yet, and a spoken price fights the voice for
attention and is forgotten. The model is told to avoid both; this checks that
it actually did, because a model that ignores an instruction silently is the
normal case, not the exception.
"""
import json
import sys

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
    blob = " ".join(d.values())
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

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)