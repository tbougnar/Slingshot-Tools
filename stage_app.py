"""Generate an app and stage it for verification. Publishes nothing.

Kept apart from the QA step on purpose: one model call budget is shared per
minute, so generating and verifying in the same minute starves the debugger.
The verifier runs an hour later on a fresh allowance.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_app
import auditlog

# How many times to ask for an app before giving up on the week. The gate
# refuses anything whose script will not parse, and a model has a bad run
# sometimes, so one refusal is not enough evidence to stop. Bounded because
# every attempt spends allowance the budget guard is watching.
ATTEMPTS = 5


def _rel(p: Path) -> str:
    """A path relative to the repo, or empty if it lives outside it.

    PyInstaller and NSIS write into dist/, which is inside the repo today but
    can be pointed elsewhere by a build flag. data/candidate.json is committed,
    so an absolute path in it publishes the build machine's own folder layout
    to every other machine that reads it, where it resolves to nothing.
    """
    try:
        return Path(p).resolve().relative_to(make_app.ROOT).as_posix()
    except ValueError:
        return ""


def _clear_stale_candidate() -> None:
    """Delete a candidate left behind by an earlier run.

    data/candidate.json is a tracked file. A run that produced nothing used to
    leave the previous run's candidate in place, so the verifier treated last
    week's app as this week's work and republished it: a live product came back
    with its differences wiped, its description replaced and its date bumped,
    and the catalog said a new tool had shipped when none had. A no-op week
    must reach the verifier as no candidate at all.
    """
    out = make_app.DATA / "candidate.json"
    try:
        if out.exists():
            out.unlink()
            try:
                shown = out.relative_to(make_app.ROOT).as_posix()
            except ValueError:
                # DATA is inside the repo in every real run; a test or a
                # redirected build can put it elsewhere, and logging that
                # must not be what stops the cleanup.
                shown = out.name
            make_app.log(f"removed the stale candidate from an earlier run: "
                         f"{shown}")
    except OSError as e:
        make_app.log(f"could not remove the stale candidate: {str(e)[:60]}")


def main() -> int:
    import buglog
    import tokenmeter
    import sizeguard

    lessons = ""
    if make_app.LESSONS.exists():
        lessons = make_app.LESSONS.read_text(encoding="utf-8")
    lessons = (lessons + "\n\nPAST BUGS - do not repeat these:\n"
               + buglog.brief(14))[:6000]
    money = ""
    earn = make_app.DATA / "earnings.json"
    if earn.exists():
        money = earn.read_text(encoding="utf-8")[:2500]

    # Wait for room rather than firing into a wall. The allowance is shared per
    # minute across the whole account, so starting too early wastes the run.
    #
    # The test is whether there is room for what this run needs, not whether
    # anything at all has been spent. The old loop waited whenever spent() was
    # greater than zero, so a run with ten tokens used would sit and wait out
    # the clock even though there were seven thousand left.
    limit = int(os.environ.get("TOKEN_LIMIT") or 8000)
    need = 4000                       # concept + a fresh app + one patch
    waited = 0
    while not tokenmeter.affordable(limit, need) and waited < 300:
        # An unreadable meter never resets, so waiting on it just burns five
        # minutes and then starts anyway. Say what is wrong and stop waiting.
        if tokenmeter.unknown():
            print("[stage] the token meter cannot be read, so there is no "
                  "allowance left to wait for; not waiting")
            break
        if waited == 0:
            print(f"[stage] allowance is {tokenmeter.spent()} tokens in, "
                  f"{tokenmeter.remaining(limit)} left, and this run needs "
                  f"{need}; waiting for it to reset")
        time.sleep(30)
        waited += 30
    if waited:
        print(f"[stage] waited {waited}s for the allowance to reset")
    if not tokenmeter.affordable(limit, need):
        if tokenmeter.unknown():
            print("[stage] the token meter is unreadable and "
                  f"{need} tokens are needed; this run may be cut off")
        else:
            print(f"[stage] only {tokenmeter.remaining(limit)} tokens left and "
                  f"{need} are needed, so starting anyway is the only option")

    concept = make_app.pick_concept(money)
    if not concept:
        # Every concept has been built. There is nothing new to make, and
        # that is a legitimate week, not a failure. The old code fell back to
        # the whole list and rebuilt a product that was already on the site,
        # which for a product on sale meant overwriting the edition a
        # customer was buying.
        print("[stage] there is nothing new to build: every concept has been "
              "made already")
        print("[stage] the site keeps what it has, and the week is a no-op")
        _clear_stale_candidate()
        return 0
    make_app.log(f"concept: {concept['title']} ({concept['slug']})")

    html = ""
    issues = []
    for attempt in range(1, ATTEMPTS + 1):
        # Ask for the file itself. The JSON path asks a model to wrap a large
        # document in an object, and that parse is the single thing every run
        # has been dying on, even though a working raw path already existed.
        try:
            html, mode, _ = make_app.build_html_raw(concept, lessons,
                                                    attempt=attempt)
        except RuntimeError as e:
            # build_html_raw retries internally and then raises. Nothing
            # caught it here, so the rejection block below never ran: no
            # NOT_VERIFIED event and no rejected script for the self-heal job.
            make_app.log(f"attempt {attempt}: the model produced nothing "
                         f"usable ({str(e)[:100]})")
            auditlog.retried("generate", job=concept["slug"],
                             reason=f"attempt {attempt} produced no usable app",
                             evidence={"error": str(e)[:200]})
            html = ""
            continue
        # The raw path asks the model for the file and nothing else, so the
        # product's name, the list of what the paid edition adds, and the two
        # descriptions all have to come from elsewhere. They used to be
        # empty strings, which published a paid edition with the same
        # description as the free one and an empty differences list: the
        # shop asked for three dollars and never said what the three
        # dollars were for.
        #
        # The app's own limit table says what the paid edition has, so it is
        # read from the generated file. No model call, which matters because
        # this path exists to spend as little allowance as possible.
        brand = str(concept.get("title") or "").strip()
        # The model escapes single quotes that are not inside a string, which
        # is not valid javascript, and whether one is an artefact or a real
        # escape cannot be told apart without parsing. So the variants are
        # tried and the first one that node accepts is used. This has to run
        # before the paid features are read, because a doubly-escaped limit
        # table does not parse and would look like "no paid features".
        html, parsed = make_app.best_variant(html)
        if not parsed:
            make_app.log(f"attempt {attempt}: no escaping variant of the "
                         f"script parses")
        issues = make_app.html_looks_fine(html)
        for note in getattr(make_app.html_looks_fine, "notes", []):
            make_app.log(f"note: {note}")
        if issues:
            make_app.log(f"attempt {attempt} rejected: {issues}")
            auditlog.retried("generate", job=concept["slug"],
                             reason=f"attempt {attempt} failed the staging gate",
                             evidence={"issues": issues, "bytes": len(html)})
            continue
        ok, why = sizeguard.verdict(len(html))
        if not ok:
            make_app.log(f"attempt {attempt} {why}")
            auditlog.retried("generate", job=concept["slug"], reason=why,
                             evidence={"bytes": len(html)})
            continue
        if why:
            make_app.log(f"attempt {attempt} warning: {why}")
        # The shop asks for money, so the product has to say what the money
        # buys. An empty list means the paid edition is the free one, which
        # used to be published with a generic description on both cards.
        diffs = make_app.paid_features(html)
        if not diffs:
            make_app.log(f"attempt {attempt} rejected: the paid edition adds "
                         f"nothing the free edition does not have")
            auditlog.retried("generate", job=concept["slug"],
                             reason=f"attempt {attempt} has no paid features "
                                    f"to sell",
                             evidence={"bytes": len(html)})
            continue
        free_blurb = (f"{brand} as a free offline tool: one job done "
                      f"properly, no account, and your data stays on your "
                      f"device.")
        paid_blurb = (f"Everything the free edition does, and "
                      f"{', '.join(diffs).lower()}.")
        make_app.log(f"attempt {attempt} ok ({len(html)} bytes, brand={brand!r})")
        auditlog.succeeded("generate", job=concept["slug"],
                           reason="the app passed the staging gate and the "
                                  "size guard",
                           tool="stage_app.py",
                           evidence={"attempt": attempt, "bytes": len(html),
                                     "concept": concept["slug"]})

        # write_app appends "-basic" itself for the basic tier, so passing an
        # already-suffixed slug produced "password-manager-basic-basic"
        try:
            basic_dir = make_app.write_app({**concept, "brand": brand},
                                           html, tier="basic")
            full_dir = make_app.write_app({**concept, "brand": brand}, html,
                                          tier="full")
        except RuntimeError as e:
            # The tier gate refuses to write an app whose free edition would
            # be the full product. Try another sample rather than publishing
            # an unlocked build.
            make_app.log(f"attempt {attempt} rejected by the tier gate: "
                         f"{str(e)[:120]}")
            auditlog.retried("generate", job=concept["slug"],
                             reason=f"attempt {attempt} failed the tier gate",
                             evidence={"error": str(e)[:200]})
            # The free edition may already have been written when the paid one
            # failed, and site/ is published. Nothing links to an uncatalogued
            # folder, but it still answers.
            make_app.discard_unpublished(concept["slug"])
            continue

        # Now the installer, in the same job.
        #
        # This was never called from here, which is why nothing has ever been
        # sellable: every Friday wrote a perfectly good paid app and then
        # stopped, leaving no .exe for itch.io to upload. build_paid_only.py
        # then looked for a Setup file that nobody had built, failed, and its
        # next step was printed as a list of things to do by hand.
        #
        # It is built here because this is already the Windows runner, so it
        # costs nothing extra, and because a paid edition with no installer is
        # a card with a price on it and nothing behind it.
        installer = None
        try:
            import build_exe as be
            title = concept.get("title") or concept["slug"]
            built = be.build_app(full_dir, title)
            if built:
                import build_installer_app as bi
                installer = bi.build_installer(built, title, full_dir)
        except Exception as e:  # noqa: BLE001
            make_app.log(f"installer build failed: {str(e)[:90]}")

        if installer and Path(installer).exists():
            make_app.log(f"installer ready: {installer}")
        else:
            # Not fatal. The free edition is still worth shipping, and a
            # missing installer is reported every week by e2e_product.py
            # rather than stopping a release that has value.
            make_app.log("no installer was produced; the paid edition will "
                         "have nothing to sell until this is fixed")

        # The verifier needs the candidate on disk plus enough context to judge
        # it. Nothing goes near site/, which is the published folder.
        stage = {
            "slug": concept["slug"],
            "brand": brand,
            "title": concept["title"],
            "tag": concept.get("tag", "productivity"),
            "differences": diffs,
            "free_blurb": free_blurb,
            "paid_blurb": paid_blurb,
            "candidate": (basic_dir / "app" / "index.html")
                           .relative_to(make_app.ROOT).as_posix(),
            "paid_dir": _rel(full_dir),
        }
        out = make_app.DATA / "candidate.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stage, indent=1), encoding="utf-8")
        make_app.log(f"candidate staged for verification: {out}")
        return 0

    make_app.log("no new product was produced this run")
    # Nothing was staged, so nothing of this concept may stay in the published
    # folder. An earlier attempt can have written the free half before the
    # paid half was refused.
    make_app.discard_unpublished(concept["slug"])
    # Not a failure of the release. This job generates one app a week; a week
    # where the model produced nothing usable should leave the previous week's
    # tool live and let the rest of the automation carry on, rather than
    # stopping the site deploy and every channel refresh behind it. The truth
    # is recorded rather than swallowed: the audit log gets a NOT_VERIFIED
    # event, and the rejected script is kept so the self-heal job can see what
    # the model actually wrote.
    _rejected = make_app.DATA / "rejected"
    try:
        _rejected.mkdir(parents=True, exist_ok=True)
        keep = _rejected / f"{concept['slug']}.js"
        if not keep.exists():
            keep.write_text(html or "", encoding="utf-8", errors="replace")
            make_app.log(f"  the script that would not parse is at "
                         f"{keep.relative_to(make_app.ROOT)}")
    except OSError as e:
        make_app.log(f"  could not keep the rejected script: {str(e)[:60]}")
    auditlog.not_verified(
        "generate", job=concept["slug"],
        reason="every attempt failed the staging gate, so no candidate was "
               "produced; the previous release stays live",
        evidence={"attempts": ATTEMPTS, "last_issues": issues})
    _clear_stale_candidate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())