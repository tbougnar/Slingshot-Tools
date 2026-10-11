"""Check that the clone script explains a paid refusal instead of dead-ending.

The first run failed with `paid_plan_required` and offered nothing. A person
sitting in front of that has no idea a free route exists, which is the whole
point of this check.
"""
import sys

import shorts_clone as sc

fails = []

# a refusal from the API must name the free alternative
def fake_post(path, payload):
    raise SystemExit(
        "[clone] refused: instant voice cloning is not in the free plan\n"
        "it needs Starter at $6 a month:\n"
        "  https://elevenlabs.io/app/subscription\n"
        "\n"
        "meanwhile, design a voice instead, which is free:\n"
        "  python shorts_clone.py design")

sc._post = fake_post
sc.sv.key = lambda: "sk_test"

try:
    rc = sc.main()
    ok = rc == 1
    print(("ok   " if ok else "FAIL "),
          "a paid refusal returns failure, not a stack trace", rc)
    if not ok:
        fails.append("paid refusal")
except SystemExit:
    print("FAIL  a paid refusal escaped as an exception")
    fails.append("paid refusal")

# the design path must not depend on the paid endpoint
called = []


def fake_design(text=sc.DESCRIBE, name=sc.NAME):
    called.append(text)
    return "voice_abc123"


sc.design = fake_design
sc.main.__globals__["sys"].argv = ["shorts_clone.py", "design"]
rc = sc.main()
ok = rc == 0 and called and called[0] == sc.DESCRIBE
print(("ok   " if ok else "FAIL "),
      "design creates a voice and reports the id")
if not ok:
    fails.append("design")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)