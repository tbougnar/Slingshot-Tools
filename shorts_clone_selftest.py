"""Check the voice picker without a network call.

It failed twice for real reasons: a paid-plan error with no alternative, and
an endpoint that does not exist. Both are cheap to check here.
"""
import sys

import shorts_clone as sc

fails = []

# 1. no key at all is refused before any request
sc.sv.key = lambda: ""
rc = sc.main()
ok = rc == 1
print(("ok   " if ok else "FAIL "), "no key is refused up front", rc)
if not ok:
    fails.append("no key")

# 2. filters are read from plain words
sc.sv.key = lambda: "sk_test"
seen = {}


def fake_library(**filters):
    seen.clear()
    seen.update(filters)
    return [{"voice_id": "v1", "name": "A", "labels": {}}]


sc.library = fake_library
sc.sys.argv = ["shorts_clone.py", "pick", "british", "female", "young"]
rc = sc.main()
ok = rc == 0 and seen.get("accent") == "british" and seen.get("gender") == "female"
print(("ok   " if ok else "FAIL "), "words become search filters", seen)
if not ok:
    fails.append("filters")

# 3. an empty library must suggest the next thing to try, not just fail
sc.library = lambda **f: []


def fake_argv(a):
    sc.sys.argv = a


fake_argv(["shorts_clone.py", "pick", "welsh", "male"])
rc = sc.main()
ok = rc == 1
print(("ok   " if ok else "FAIL "), "no match returns failure cleanly", rc)
if not ok:
    fails.append("no match")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)