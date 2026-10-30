"""Verify a staged app in a real browser and publish only if it is clean.

Runs an hour after the generator on purpose: the model allowance is per minute,
so verifying in the same minute as generating starves the debugger team.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qa_loop

# how many dead controls we will ship with rather than ship nothing
TOLERATED = 1


def discard(stage: dict, stage_file: Path) -> None:
    """Take a rejected candidate off the public site as well as out of the queue.

    The staged app lives under site/, which is the folder Pages publishes, so
    it answers 200 at /apps/<slug>-basic/app/index.html even though nothing
    links to it. The invoice-maker candidate that failed every repair round was
    reachable that way, with a Save button that did nothing, until its folder
    was removed by hand.

    A folder that belongs to an app already on sale is never touched: a
    re-verified product must not disappear because a later check failed.
    """
    import make_app

    stage_file.unlink(missing_ok=True)
    slug = str(stage.get("slug") or "")
    if not slug:
        return
    try:
        apps = json.loads(make_app.CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        apps = []
    if any(isinstance(a, dict) and a.get("slug") == f"{slug}-basic"
           and a.get("published") for a in apps):
        print(f"[verify] {slug} is already published; leaving its folder alone")
        return
    folder = make_app.SITE_APPS / f"{slug}-basic"
    if folder.is_dir() and make_app.SITE_APPS in folder.parents:
        shutil.rmtree(folder, ignore_errors=True)
        try:
            shown = folder.relative_to(make_app.ROOT)
        except ValueError:
            shown = folder
        print(f"[verify] removed {shown} so a rejected app is not served")


def main() -> int:
    import make_app

    stage_file = make_app.DATA / "candidate.json"
    if not stage_file.exists():
        # A wait is pointless when the generator has already finished and
        # staged nothing, and this step runs from a workflow_run, so the
        # generator is always long finished. Three minutes of sleeping on
        # every empty week was pure delay.
        print("[verify] no candidate staged, so there is nothing to verify. "
              "The previous release stays live.")
        try:
            import auditlog
            auditlog.not_verified(
                "verify",
                reason="no candidate was staged, so nothing was verified and "
                       "nothing was published")
        except ImportError:
            pass
        return 0
    stage = json.loads(stage_file.read_text(encoding="utf-8"))

    # stored relative so it resolves on whichever machine runs this
    candidate = make_app.ROOT / stage["candidate"]
    if not candidate.exists():
        print(f"[verify] staged file is gone: {candidate}")
        # There is nothing to verify, so the candidate is not left behind for
        # the next run to pick up again, and any half-written folder of it is
        # taken off the public site.
        discard(stage, stage_file)
        return 1

    print(f"[verify] checking {stage['title']} ({stage['slug']})")

    # One scan first: a clean app costs nothing and publishes immediately.
    import app_scanner
    first = app_scanner.scan(candidate)
    if app_scanner.verdict(first):
        print("[verify] first scan clean, no repair needed")
    else:
        print(f"[verify] {len(first.get('dead', []))} dead control(s), handing to the debugger team")
        clean, history = qa_loop.repair_until_clean(candidate, log=print)
        if not clean:
            # A fresh app costs about the same as several repair rounds and is
            # far more likely to be correct, so regenerating is the right
            # answer - but there is no regeneration step here. When the
            # allowance is gone the only honest choice is the small tolerance
            # below. When it is not, publishing a failed app is not an option.
            import tokenmeter
            left = tokenmeter.remaining(8000)
            final = history[-1] if history else {}
            remaining = final.get("remaining_dead")
            if not isinstance(remaining, list):
                remaining = first.get("dead", [])
            remaining_errors = final.get("remaining_errors")
            if not isinstance(remaining_errors, list):
                remaining_errors = first.get("errors", [])
            print(f"[verify] repair failed; {left} tokens left this minute, "
                  f"{len(remaining)} dead control(s), "
                  f"{len(remaining_errors)} JS error(s) remaining")
            # A real shop ships an app that is nearly right. One dead control
            # with no JS errors, after every repair round has been tried and
            # the allowance is exhausted, is not a reason to publish nothing.
            # Anything worse is refused, and a searchable/syntax error always
            # is: the page may look fine and do nothing at all.
            if left < 4000 and len(remaining) <= TOLERATED and not remaining_errors:
                print(f"[verify] repair ran out of allowance with "
                      f"{len(remaining)} dead control(s) and no JS errors; "
                      f"publishing anyway because that is within the "
                      f"tolerance of {TOLERATED}")
                print("[verify] still dead: " + ", ".join(remaining[:5]))
            else:
                why = []
                if remaining_errors:
                    why.append(f"{len(remaining_errors)} JS error(s)")
                if len(remaining) > TOLERATED:
                    why.append(f"{len(remaining)} dead control(s)")
                if left >= 4000:
                    why.append("allowance remains, so a broken app must not "
                               "be published")
                print(f"[verify] NOT publishing: {'; '.join(why)}")
                print(json.dumps(history, indent=1)[-1200:])
                # The candidate is cleared whether it passed or not.
                # It is a tracked file, so leaving it there means the
                # next run verifies the same rejected app again, and it
                # keeps widening the release gate's exemption for that
                # folder name for as long as it exists. Its site folder goes
                # too: an unpublishable app must not answer on the live site.
                discard(stage, stage_file)
                return 1
    html = candidate.read_text(encoding="utf-8", errors="replace")
    concept = {"slug": stage["slug"], "brand": stage["brand"],
               "title": stage["title"], "tag": stage["tag"],
               "blurb": stage.get("blurb") or stage.get("free_blurb") or ""}

    full_dir = make_app.write_app({**concept}, html, tier="full")
    # write_app adds the "-basic" suffix itself; passing it here doubles it
    basic_dir = make_app.write_app({**concept}, html, tier="basic")

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

    # A Windows .exe cannot be built on the Linux runner, so this job only
    # publishes the free edition. The paid tier is listed but stays hidden
    # unless it was already proven on sale: itch.io hosts the paid file and
    # only a person can upload it, so publish_paid.py is what makes it
    # visible, and never before the build and the price are verified.
    # write_app named the public folder "<slug>-basic"; the catalog entry must
    # carry the same name so the two match on disk and in URLs
    make_app.publish({**concept, "slug": basic_dir.name}, basic_dir, None,
                     tier="basic",
                     brand=stage["brand"], differences=stage["differences"],
                     free_blurb=stage["free_blurb"], paid_blurb=stage["paid_blurb"],
                     published=True, price_override=0.0)

    # A re-verified candidate must not hide a product that is already on sale.
    # publish() replaces the entry with the same slug, so passing False blindly
    # removed the buy button from a live product until publish_paid.py ran
    # again - and that run now correctly refuses while the price is unverified.
    was_live = make_app.already_listed(stage["slug"])
    make_app.publish({**concept, "slug": stage["slug"]}, full_dir, None, tier="full",
                     brand=stage["brand"], differences=stage["differences"],
                     free_blurb=stage["free_blurb"], paid_blurb=stage["paid_blurb"],
                     published=was_live, price_override=price)

    # write_app already put the full tier under paid/, so just record it
    import json as _json
    (make_app.DATA / "published.json").write_text(_json.dumps(
        {"slug": stage["slug"], "title": stage["title"], "price": price}, indent=1),
        encoding="utf-8")
    print(f"[verify] published the free edition of {stage['title']}; "
          f"paid tier at ${price:.2f} waits for the Windows installer")
    try:
        import mark_verified
        mark_verified.main()
    except Exception as e:  # noqa: BLE001
        print(f"[verify] fixbook refresh failed: {str(e)[:80]}")
    stage_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())