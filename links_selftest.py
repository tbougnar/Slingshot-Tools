"""Every href on the site must be one of the links in links.py.

A footer that disagrees with the Discord welcome and the YouTube description
is worse than no footer: it looks authoritative and sends people somewhere
else. This keeps the surfaces in agreement.
"""
import pathlib
import re
import sys

import links

ROOT = pathlib.Path(__file__).resolve().parent
SITE = ROOT / "site" / "index.html"

fails = []

if not SITE.exists():
    print("FAIL  site/index.html is missing")
    sys.exit(1)

html = SITE.read_text(encoding="utf-8")
known = {c["url"] for c in links.all_links()}

hrefs = re.findall(r'href="(https?://[^"]+)"', html)
print(f"  {len(hrefs)} external links on the page")

missing = [h for h in hrefs if h not in known]
for h in missing:
    print(f"  FAIL  not in links.py: {h}")
    fails.append(h)

for c in links.all_links():
    ok = c["url"] in html
    print(("  ok   " if ok else "  FAIL ") + f" {c['label']} is on the page")
    if not ok:
        fails.append(c["key"])

# the two primary destinations must be inside the footer, not elsewhere
foot = re.search(r"<footer.*?</footer>", html, re.S)
if foot:
    for key in ("itch", "website"):
        u = links.url(key)
        if u not in foot.group(0):
            print(f"  FAIL  {key} is not in the footer")
            fails.append(f"footer/{key}")
else:
    print("  FAIL  no footer")
    fails.append("footer")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)