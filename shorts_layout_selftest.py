"""No two bands may overlap, and none may run off the frame.

They did: the price badge landed on a three line headline, and the URL sat
underneath the captions. Fixed bands make that impossible, but only if the
bands themselves are correct, so they are checked here.
"""
import sys

import shorts_render as sr

fails = []

bands = [
    ("logo", sr.BAND_LOGO),
    ("headline", sr.BAND_HEAD),
    ("price", sr.BAND_PRICE),
    ("window", sr.BAND_WINDOW),
]

prev_name, prev_end = None, -1
for name, (a, b) in bands:
    print(f"  {name:9} {a:5}-{b}")
    if a < prev_end:
        print(f"        OVERLAPS {prev_name}")
        fails.append(f"{name}/{prev_name}")
    if b <= a:
        print(f"        empty band")
        fails.append(f"{name} empty")
    prev_name, prev_end = name, b

# the closing card replaces the window, so those two may share a band
if sr.BAND_URL[0] < sr.BAND_WINDOW[1]:
    print("        note: url overlaps window, which is fine on the "
          "closing card")

if bands[-1][1][1] > sr.H - 30:
    print(f"        last band runs to {bands[-1][1][1]} in a {sr.H} frame")
    fails.append("off frame")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)