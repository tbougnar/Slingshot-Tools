"""Follow the money the rest of the way, past what a customer can click.

The customer test stops when the buy link has nowhere to go. This asks the
other half of the question: if the link were fixed, would buying actually work?

A "full edition" that is a placeholder on disk, has no itch.io page, and no
installer is not a product. It is a card with a price on it.

    python e2e_product.py
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
PAID = ROOT / "paid"

rows: list[tuple[str, bool, str]] = []


def say(ok: bool, label: str, detail: str = "") -> bool:
    rows.append((label, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          + (f"\n        {detail}" if detail else ""))
    return ok


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    families: dict[str, list] = {}
    for a in catalog:
        families.setdefault(a.get("base_slug") or a.get("slug"), []).append(a)

    print("IS THERE ACTUALLY A PRODUCT TO BUY?\n")
    for base, entries in families.items():
        paid = next((a for a in entries if a.get("tier") == "full"), None)
        basic = next((a for a in entries if a.get("tier") == "basic"), None)
        print(f"{base}")
        print("-" * 60)

        if paid is None:
            say(False, "there is a paid edition at all", "no 'full' entry")
            continue

        say(True, "a paid edition exists in the catalog", paid.get("title", ""))

        # 1. is the paid app real?
        src = PAID / base / "app" / "index.html"
        if src.exists():
            n = src.stat().st_size
            text = src.read_text(encoding="utf-8", errors="replace")
            real = n > 2000 and ("<html" in text.lower()) \
                and ("localStorage" in text or "indexedDB" in text)
            say(real, "the paid app is a real application",
                f"{n} bytes" + ("" if real else
                                "  <- that is a placeholder, not an app"))
            say("<input" in text or "<button" in text,
                "the paid app has anything to click")
        else:
            say(False, "the paid app has been built", f"{src} does not exist")

        # 2. is it published where customers can reach it?
        live = ROOT / "site" / "apps" / paid.get("slug", "")
        say(not (live / "index.html").exists(),
            "the paid app is NOT sitting in the public site",
            "correct: a paid build must never be published" if
            not (live / "index.html").exists() else
            f"{live} is published, which would leak the paid edition")

        # 3. is there an installer?
        exes = list(PAID.glob(f"{base}/**/*.exe")) if PAID.exists() else []
        say(bool(exes), "there is an installer to hand over",
            f"{len(exes)} found" if exes else
            "no .exe, so there is nothing to download even if the page existed")

        # 4. is it for sale anywhere?
        url = str(paid.get("itch_url") or "")
        say(url.startswith("http"), "it is for sale on itch.io",
            f"itch_url={url!r}" + ("  <- nothing to buy"
                                    if not url.startswith("http") else ""))

        say(bool(paid.get("published")), "the catalog says it is published")

        # 5. does the free edition exist and work, since that is the funnel?
        if basic:
            b = ROOT / "site" / "apps" / basic.get("slug", "") / "app" / \
                "index.html"
            say(b.exists() and b.stat().st_size > 2000,
                "the free edition is a real application",
                f"{b.stat().st_size} bytes" if b.exists() else "missing")
        print()

    good = sum(1 for _, ok, _ in rows if ok)
    bad = [r for r in rows if not r[1]]
    print("=" * 62)
    print(f"{good} of {len(rows)} checks pass")
    if bad:
        print()
        print("NOT ACTUALLY A PRODUCT YET:")
        for label, _, detail in bad:
            print(f"  - {label}" + (f"\n      {detail}" if detail else ""))
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())