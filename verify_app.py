"""Verify a staged app in a real browser and publish only if it is clean.

Runs an hour after the generator on purpose: the model allowance is per minute,
so verifying in the same minute as generating starves the debugger team.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paid_store
import qa_loop


def main() -> int:
    import make_app

    stage_file = make_app.DATA / "candidate.json"
    if not stage_file.exists():
        # a dispatch that ran before the generator finished would otherwise
        # report success having done nothing
        print("[verify] no candidate staged yet; waited 3 minutes for one")
        for _ in range(6):
            import time
            time.sleep(30)
            if stage_file.exists():
                break
        if not stage_file.exists():
            print("[verify] still no candidate - the generator must run first")
            return 1
    stage = json.loads(stage_file.read_text(encoding="utf-8"))

    candidate = Path(stage["candidate"])
    if not candidate.exists():
        print(f"[verify] staged file is gone: {candidate}")
        return 1

    print(f"[verify] checking {stage['title']} ({stage['slug']})")

    # One scan first: a clean app costs nothing and publishes immediately.
    import app_scanner
    first = app_scanner.scan(candidate)
    if app_scanner.verdict(first):
        print("[verify] first scan clean, no repair needed")
    else:
        print(f"[verify] {len(first.get('dead', []))} dead control(s), "
              f"handing to the debugger team")
        clean, history = qa_loop.repair_until_clean(candidate, log=print)
        if not clean:
            print("[verify] still broken after every round; publishing nothing")
            print(json.dumps(history, indent=1)[-1500:])
            return 1

    html = candidate.read_text(encoding="utf-8", errors="replace")
    concept = {"slug": stage["slug"], "brand": stage["brand"],
               "title": stage["title"], "tag": stage["tag"]}

    full_dir = make_app.write_app({**concept}, html, tier="full")
    basic_dir = make_app.write_app({**concept, "slug": f"{stage['slug']}-basic"},
                                   html, tier="basic")

    price = make_app.PRICE_START
    import pricing
    try:
        if pricing.PRICES.exists():
            saved = json.loads(pricing.PRICES.read_text(encoding="utf-8"))
            if isinstance(saved, dict) and saved.get("current"):
                price = float(saved["current"])
            elif isinstance(saved, list) and saved:
                last = saved[-1]
                price = float(last.get("price", price) if isinstance(last, dict) else last)
        else:
            decided, _why = pricing.decide(0, 0, price)
            price = float(decided)
    except Exception as e:  # noqa: BLE001
        print(f"[verify] pricing unavailable ({str(e)[:60]}), using {price}")
    price = max(make_app.PRICE_FLOOR, min(make_app.PRICE_CEILING, price))

    # the paid build has to exist and be in the store before we advertise it
    ok = make_app.stage_paid(full_dir, stage["slug"], None)
    if not ok:
        print("[verify] the paid build could not be produced; publishing nothing")
        return 1

    make_app.publish({**concept}, basic_dir, None, tier="basic",
                     brand=stage["brand"], differences=stage["differences"],
                     free_blurb=stage["free_blurb"], paid_blurb=stage["paid_blurb"],
                     published=True, price_override=0.0)
    make_app.publish({**concept, "slug": stage["slug"]}, full_dir, None, tier="full",
                     brand=stage["brand"], differences=stage["differences"],
                     free_blurb=stage["free_blurb"], paid_blurb=stage["paid_blurb"],
                     published=True, price_override=price)

    # tell the installer job which paid build to package
    import json as _json
    (make_app.DATA / "published.json").write_text(_json.dumps(
        {"slug": stage["slug"], "title": stage["title"]}, indent=1),
        encoding="utf-8")
    print(f"[verify] published {stage['title']} at ${price:.2f}")
    try:
        import mark_verified
        mark_verified.main()
    except Exception as e:  # noqa: BLE001
        print(f"[verify] fixbook refresh failed: {str(e)[:80]}")
    stage_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())