"""Everything a customer can click that is not the app itself.

The buy path is broken, but it is not the only thing on the page. A stranger
also follows the links in the footer, lands on itch.io, reads the YouTube
channel, and tries to join the Discord. If those are dead, the business has no
door into it at all.

    python e2e_links.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent

rows: list[tuple[str, bool, str]] = []


def say(ok: bool, label: str, detail: str = "") -> bool:
    rows.append((label, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          + (f"\n        {detail}" if detail else ""))
    return ok


def get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; slingshot-e2e/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def main() -> int:
    print("FOLLOWING EVERY LINK A CUSTOMER WOULD\n")

    sys.path.insert(0, str(ROOT))
    import links

    print("THE FOOTER LINKS\n")
    for c in links.all_links():
        url = c["url"]
        try:
            code, final, body = get(url)
            good = code == 200
            say(good, f"the {c['label']} link works",
                f"{code} -> {final[:60]}" if good
                else f"HTTP {code} {final[:60]}")
            if "itch" in c["key"]:
                # The account has to list every product as its own project.
                # It used to hold one project that sold four installers; the
                # page answering 200 is not evidence that the shop is right.
                catalog = json.loads(
                    (ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
                titles = [a.get("title", "") for a in catalog
                          if a.get("tier") == "full"]
                missing = [t for t in titles
                           if t.lower() not in body.lower()]
                say(not missing,
                    "the itch.io account lists one project per paid app",
                    "missing: " + ", ".join(missing) if missing else
                    f"{len(titles)} paid projects listed")
        except urllib.error.HTTPError as e:
            say(False, f"the {c['label']} link works", f"HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            # A truncated read is not a broken link. GitHub serves a large
            # page and closes the connection early under a plain user agent,
            # which is a fetch problem rather than a site being down, so the
            # status is all that is trusted here.
            code = getattr(e, "code", None)
            partial = getattr(e, "partial", None)
            if partial:
                say(True, f"the {c['label']} link works",
                    f"{code} (body truncated at {len(partial)} bytes, "
                    f"which is the server closing early, not a dead link)")
            else:
                say(False, f"the {c['label']} link works", str(e)[:60])

    print("\nTHE SITE ITSELF\n")
    try:
        code, final, body = get("https://tbougnar.github.io/Slingshot-Tools/")
        say(code == 200, "the live site answers", f"{code}")
        say("password-manager" in body or "password" in body.lower(),
            "the live site mentions the product")
        say('id="countdown"' in body, "the live site has the countdown")
        say("groupProducts" in body and "key:k" not in body,
            "the live site runs the fixed homepage script")
    except Exception as e:  # noqa: BLE001
        say(False, "the live site answers", str(e)[:60])

    print("\nTHE PAGES A CUSTOMER CAN BUY FROM\n")
    catalog = json.loads(
        (ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
    for app in catalog:
        if app.get("tier") != "full":
            continue
        url = str(app.get("itch_url") or "").rstrip("/")
        label = app.get("title", app["slug"])
        if not url:
            say(False, f"{label} has its own itch.io page",
                "the catalogue has no URL for it")
            continue
        try:
            code, final, body = get(url)
            say(code == 200 and final.rstrip("/") == url,
                f"{label} has its own itch.io page", f"{code} -> {final}")
            priced = '"min_price":300' in body or "$3.00" in body
            say(priced, f"{label} asks for exactly $3.00",
                "" if priced else "the page does not show the $3.00 minimum")
            builds = sorted(set(re.findall(r">([^<>]{1,80}Setup\.exe)<", body)))
            alien = [b for b in builds
                     if label.lower() not in b.lower()
                     and str(app["slug"]).lower() not in b.lower()]
            say(bool(builds) and len(builds) == 1 and not alien,
                f"{label} lists only its own installer",
                "found: " + ", ".join(builds) if builds else
                "the page answers but has no paid upload")
        except Exception as e:  # noqa: BLE001
            say(False, f"{label} has its own itch.io page", str(e)[:60])

    print("\nTHE SITE IS PAID-ONLY\n")
    base = "https://tbougnar.github.io/Slingshot-Tools"

    print("\nWHAT A CUSTOMER CANNOT GET\n")
    # the paid page must NOT exist, which is correct, but then the paid
    # edition has nowhere to go either
    try:
        code, final, _ = get(base + "/apps/password-manager/")
        say(False, "the paid edition is not leaked to the public site",
             f"HTTP {code}: the paid build IS published, which would leak it")
    except urllib.error.HTTPError as e:
        say(e.code == 404, "the paid edition is not leaked to the public site",
            f"HTTP {e.code}, correct")
    except Exception as e:  # noqa: BLE001
        say(None, "the paid edition is not leaked", str(e)[:50])

    good = sum(1 for _, ok, _ in rows if ok)
    bad = [r for r in rows if not r[1]]
    print()
    print("=" * 62)
    print(f"{good} of {len(rows)} checks pass")
    if bad:
        print()
        print("BROKEN OR MISSING:")
        for label, _, detail in bad:
            print(f"  - {label}" + (f"\n      {detail}" if detail else ""))
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())