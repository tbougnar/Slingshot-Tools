"""Fail loudly if a paid edition has ever ended up in the published folder.

This is the check that would have caught the leak where old paid files stayed
tracked in git and the build republished them. It runs on every publish.

It also reports, separately, when a product is marked for sale but cannot be
bought. That is not a leak and nothing is unsafe, so it does not fail the
run unless ``--strict`` is passed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
APPS = SITE / "apps"


def _product_page(url: str) -> bool:
    """True when the URL names one itch.io product rather than an account.

    Imported from set_itch_url so there is one rule rather than two that can
    disagree, which is how the account page came to be stored in the first
    place.
    """
    from set_itch_url import valid
    return valid(url)


def check_tier_families(catalog):
    """Both tiers of a product must share one base_slug.

    If they drift apart the site renders two separate cards instead of a
    single product offering a free and a paid option.

    A published product showing only its free edition is allowed: that is what
    a tool looks like between its build and the moment somebody uploads it to
    itch.io. What must never happen is a product whose two entries have drifted
    onto different base_slugs, which is checked separately.
    """
    families = {}
    for a in catalog:
        key = a.get("base_slug") or a.get("slug")
        families.setdefault(key, []).append(a.get("tier"))

    problems = []
    for key, tiers in families.items():
        if "basic" in tiers and "full" in tiers:
            continue
        # a lone tier is only a problem when it is on sale and the other tier
        # exists nowhere in the catalog: the two would never regroup
        on_sale = [a for a in catalog
                   if (a.get("base_slug") or a.get("slug")) == key
                   and a.get("published") is not False]
        if len(on_sale) == 1 and len(tiers) == 1 and on_sale[0].get("tier") == "full":
            problems.append(f"{key} is on sale with no free edition beside it")

    return families, problems


def main() -> int:
    catalog = json.loads((SITE / "apps.json").read_text(encoding="utf-8"))
    paid = [a["slug"] for a in catalog if a.get("tier") == "full"]
    basic = {a["slug"] for a in catalog if a.get("tier") == "basic"}

    # The generate job commits the free edition an hour before the verifier
    # writes its catalog entry, so a freshly staged app is in site/apps/ but not
    # yet in apps.json. Reading that as exposure failed the release gate on
    # every run and would have blocked publishing the very app it was checking.
    staged = ROOT / "data" / "candidate.json"
    if staged.exists():
        try:
            got = json.loads(staged.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            got = None
        if isinstance(got, dict) and got.get("slug"):
            # Only the free edition's folder is exempt. The paid edition is
            # written to paid/<slug>/ and is never legitimately in site/,
            # and the generate job only ever creates site/apps/<slug>-basic,
            # so allowing the plain slug here let a paid build at
            # site/apps/<slug>/app/index.html through the gate: the check
            # below only looked for a flat index.html, and the directory
            # check treated the folder as a known basic edition.
            basic.add(f"{got['slug']}-basic")

    problems = []
    blockers = []
    for slug in paid:
        # The paid edition is paid/<slug>/app/index.html with a concept.json
        # beside it. There is no flat index.html, so a copy of the paid
        # folder into site/apps/ was invisible to the old check.
        if (APPS / slug / "index.html").exists() or \
                (APPS / slug / "app" / "index.html").exists():
            problems.append(f"a paid edition is published: apps/{slug}")
    for d in sorted(APPS.iterdir()) if APPS.exists() else []:
        if not d.is_dir():
            continue
        if d.name.endswith("-basic-basic"):
            problems.append(f"a duplicated slug is published: apps/{d.name}")
        elif d.name not in basic:
            problems.append(f"apps/{d.name} is not a known basic edition")
        # A folder that claims to be the free edition but holds a paid one is
        # exposure, and the tier constant is written into the file.
        _app = d / "app" / "index.html"
        if _app.exists():
            try:
                _head = _app.read_text(encoding="utf-8", errors="ignore")[:4000]
            except OSError:
                _head = ""
            if re.search(r'const\s+TIER\s*=\s*["\']full["\']', _head):
                problems.append(f"a paid edition is published: "
                                f"apps/{d.name}/app/index.html")

    lic = SITE / "licenses"
    if lic.exists():
        problems.append("the public site contains a licenses folder")

    # Development-only material must never reach a customer. A .bak written
    # beside an app while the QA loop worked on it was committed by the next
    # blanket git add and served by GitHub Pages as part of the release.
    # The binaries are here for the same reason: the paid product IS an
    # installer, and a copy of one anywhere under site/ is the one file
    # that must never be published.
    junk_suffixes = (".bak", ".trial.html", ".orig", ".rej", ".tmp",
                     ".py", ".log", ".bak.html")
    binary_suffixes = (".exe", ".msi", ".zip", ".7z", ".msix", ".appx")
    for f in sorted(SITE.rglob("*")):
        if not f.is_file():
            continue
        name = f.name
        if any(name.endswith(sfx) for sfx in junk_suffixes) or \
                ".r0" in name or re.search(r"\.r\d+\.", name):
            problems.append(f"a development file is published: "
                            f"{f.relative_to(SITE).as_posix()}")
        elif name.lower().endswith(binary_suffixes):
            problems.append(f"a binary is published: "
                            f"{f.relative_to(SITE).as_posix()}")
    if (SITE / "apps").is_dir():
        for f in sorted((SITE / "apps").rglob("*")):
            if f.is_file() and f.suffix.lower() in (".py", ".json.tmp"):
                problems.append(f"a development file is published: "
                                f"{f.relative_to(SITE).as_posix()}")

    for a in catalog:
        if "-basic-basic" in str(a.get("url", "")):
            problems.append(f"{a['slug']} has a malformed url")

    # A paid edition marked published but with no itch_url is a dead end: the
    # card renders a price, the button builds a checkout link with an empty
    # itch parameter, and the visitor has nowhere to go. Nothing else in the
    # pipeline catches this, because publish_paid.py refuses to set the flag
    # without a url but nothing checks the flag that is already there.
    #
    # Reported separately from the exposure failures, and only fatal when
    # asked for, because it is a different kind of problem: nothing is leaking
    # and nothing is unsafe, the shop is simply closed. Failing every release
    # over it would block the rest of the work indefinitely on something that
    # needs one person to open an itch.io page, and a gate nobody can pass is a
    # gate that stops being read.
    for a in catalog:
        url = str(a.get("itch_url") or "")
        # Any entry at all, published or not, must not carry a URL that is not
        # a product page. The account front page is a valid itch.io URL and was
        # accepted by the old validator, so it sat in the catalog as the
        # product URL. A run from before that was fixed put it back once.
        if url and not _product_page(url):
            problems.append(
                f"{a['slug']} has an itch_url that is not a product page: "
                f"{url} (a buy button must go to "
                f"https://yourslug.itch.io/the-product)")
        if a.get("tier") != "full" or a.get("published") is not True:
            continue
        if not url.startswith("http"):
            blockers.append(
                f"{a['slug']} is published for sale but has no itch_url, so "
                f"nobody can buy it (fix: python set_itch_url.py "
                f"{a.get('base_slug') or a['slug']} <itch url>)")

    families, family_problems = check_tier_families(catalog)
    problems.extend(family_problems)

    if problems:
        print("[exposure] FAILED - the public site must not contain paid work:")
        for p in problems:
            print("  -", p)
        return 1

    print(f"[exposure] ok: {len(basic)} basic edition(s) published, "
          f"{len(paid)} paid edition(s) kept private")
    if blockers:
        print("[exposure] the shop is closed - nothing is leaking, but "
              "nobody can buy:")
        for b in blockers:
            print(f"  - {b}")
        # --strict is for the job that must not finish while money is blocked
        return 1 if "--strict" in sys.argv else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())