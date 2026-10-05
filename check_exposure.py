"""Fail loudly if a paid edition has ever ended up in the published folder.

This is the check that would have caught the leak where old paid files stayed
tracked in git and the build republished them. It runs on every publish.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
APPS = SITE / "apps"


def main() -> int:
    catalog = json.loads((SITE / "apps.json").read_text(encoding="utf-8"))
    paid = [a["slug"] for a in catalog if a.get("tier") == "full"]
    basic = {a["slug"] for a in catalog if a.get("tier") == "basic"}

    problems = []
    for slug in paid:
        if (APPS / slug / "index.html").exists():
            problems.append(f"a paid edition is published: apps/{slug}")
    for d in sorted(APPS.iterdir()) if APPS.exists() else []:
        if not d.is_dir():
            continue
        if d.name.endswith("-basic-basic"):
            problems.append(f"a duplicated slug is published: apps/{d.name}")
        elif d.name not in basic:
            problems.append(f"apps/{d.name} is not a known basic edition")

    lic = SITE / "licenses"
    if lic.exists():
        problems.append("the public site contains a licenses folder")

    for a in catalog:
        if "-basic-basic" in str(a.get("url", "")):
            problems.append(f"{a['slug']} has a malformed url")

    if problems:
        print("[exposure] FAILED - the public site must not contain paid work:")
        for p in problems:
            print("  -", p)
        return 1

    print(f"[exposure] ok: {len(basic)} basic edition(s) published, "
          f"{len(paid)} paid edition(s) kept private")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())