"""A failed verification must never publish, and the edition must really flip.

Three faults this suite exists to catch, all of which shipped:

1. verify_app only made a decision when the token meter was nearly empty. With
   allowance left it fell through and published an app that had failed every
   repair round.
2. The tolerance decision read the scan taken BEFORE the repair, so an app
   that ended with a JavaScript error looked clean because the first scan had
   no dead controls.
3. The edition flip only matched double quotes, so a generated
   ``const TIER = 'full'`` shipped the paid limits inside the free folder.

    python verifygate_selftest.py
"""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import make_app

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, ("\n        " + detail) if detail else "")
    if not ok:
        fails.append(label)


print("\nTHE EDITION FLIPS WHATEVER QUOTE STYLE THE MODEL USED\n")
for label, html in (
        ("double quotes", '<html><script>const TIER = "full";</script></html>'),
        ("single quotes", "<html><script>const TIER = 'full';</script></html>"),
        ("no const", '<html><script>TIER = "full";</script></html>'),
        ("let binding", '<html><script>let TIER = "full";</script></html>'),
        ("compact", '<html><script>const TIER="full";</script></html>'),
):
    got = make_app._set_tier(html, "basic")
    check(f"{label} becomes the basic edition",
          make_app._tier_value(got) == "basic", got[:100])

check("the paid build still flips back to full",
      make_app._tier_value(make_app._set_tier(
          "<script>const TIER = 'basic';</script>", "full")) == "full")
check("a comparison is not mistaken for the assignment",
      make_app._set_tier("<script>const PAID = TIER === 'full';</script>",
                         "basic") ==
      "<script>const PAID = TIER === 'full';</script>")

print("\nAN APP WITH NO EDITION CONSTANT IS REFUSED\n")
no_tier = ("<html><body><script>localStorage.setItem('k','1');</script>"
           + "x" * 2000 + "</body></html>")
problems = make_app.html_looks_fine(no_tier)
check("the staging gate says the free edition cannot be limited",
      any("TIER" in p for p in problems), str(problems))

_real_apps, _real_paid = make_app.APPS_DIR, make_app.PAID_DIR
_scratch = pathlib.Path(tempfile.mkdtemp(prefix="verifygate-"))
make_app.APPS_DIR = _scratch / "site" / "apps"
make_app.PAID_DIR = _scratch / "paid"
try:
    try:
        make_app.write_app({"slug": "no-tier", "title": "No Tier"},
                           no_tier, tier="basic")
        check("write_app refuses to publish an unlocked free edition", False,
              "the unlocked app was written to the public folder")
    except RuntimeError as e:
        check("write_app refuses to publish an unlocked free edition",
              "TIER" in str(e), str(e)[:80])

    concept = {"slug": "quote-test", "title": "Quote Test"}
    basic = make_app.write_app(
        concept, "<html><script>const TIER = 'full';</script></html>",
        tier="basic")
    full = make_app.write_app(
        concept, "<html><script>const TIER = 'basic';</script></html>",
        tier="full")
    basic_html = (basic / "app" / "index.html").read_text(encoding="utf-8")
    full_html = (full / "app" / "index.html").read_text(encoding="utf-8")
    check("the public folder holds the basic edition",
          make_app._tier_value(basic_html) == "basic", basic_html[:80])
    check("the paid folder holds the full edition",
          make_app._tier_value(full_html) == "full", full_html[:80])
finally:
    make_app.APPS_DIR, make_app.PAID_DIR = _real_apps, _real_paid
    import shutil
    shutil.rmtree(_scratch, ignore_errors=True)


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


print("\nA FAILED VERIFICATION CANNOT FALL THROUGH TO PUBLISH\n")
_verify = source("verify_app.py")
check("the tolerance is limited to an exhausted allowance",
      "left < 4000" in _verify and "TOLERATED" in _verify)
check("a JavaScript error is never tolerated",
      re.search(r"not remaining_errors", _verify) is not None,
      "the publish condition excludes JS errors")
check("the decision uses the scan taken after the repair",
      'final.get("remaining_dead")' in _verify
      and "remaining_errors" in _verify,
      "verify_app judges the post-repair scan")
check("every failed branch returns instead of falling through",
      _verify.count("stage_file.unlink(missing_ok=True)") >= 1)

print("\nA JAVASCRIPT ERROR IS ACTUALLY HANDED TO A REPAIR\n")
_qa = source("qa_loop.py")
check("the error-only path asks for a full-file repair",
      "debug_team.fix" in _qa and "only JS errors present" in _qa,
      "the patcher is no longer called with zero controls")
check("that repair must reduce the errors to be kept",
      "fewer" in _qa and "no_worse" in _qa)

print("\nTHE SCANNER REPORTS INABILITY INSTEAD OF CRASHING\n")
import app_scanner
_missing = pathlib.Path(tempfile.mkdtemp(prefix="verifygate-gone-")) / "nope.html"
try:
    _result = app_scanner.scan(_missing)
    check("a page that cannot be opened is a result, not a traceback",
          isinstance(_result, dict) and _result.get("unavailable") is True,
          str(_result)[:120])
    check("and it is not a pass", app_scanner.verdict(_result) is False)
except Exception as e:  # noqa: BLE001
    check("a page that cannot be opened is a result, not a traceback", False,
          f"raised {type(e).__name__}: {str(e)[:100]}")

print("\nTHE STAGER KEEPS A REFUSAL INSTEAD OF ABORTING\n")
_stage = source("stage_app.py")
check("a model that produces nothing is caught",
      "except RuntimeError" in _stage and "produced nothing usable" in _stage)
check("the rejection block always has a script and issues to report",
      re.search(r"^    html = \"\"$", _stage, re.M) is not None
      and re.search(r"^    issues = \[\]$", _stage, re.M) is not None,
      "html/issues are defined before the first attempt")

print("\nA NO-OP WEEK CANNOT REPUBLISH LAST WEEK'S CANDIDATE\n")
# data/candidate.json is tracked. A run that produced nothing left the previous
# run's candidate in the tree, the verifier treated it as this week's work, and
# a live product was rewritten with an empty differences list and a new date.
check("the stager deletes a stale candidate when it makes nothing",
      _stage.count("_clear_stale_candidate()") >= 2,
      "both the no-op branch and the all-attempts-failed branch must clear it")
check("and that cleanup removes the candidate file itself",
      'out = make_app.DATA / "candidate.json"' in _stage
      and "out.unlink()" in _stage)
_rt = pathlib.Path(tempfile.mkdtemp(prefix="stale-candidate-"))
try:
    import stage_app
    _old_data = make_app.DATA
    try:
        make_app.DATA = _rt
        (_rt / "candidate.json").write_text("{}", encoding="utf-8")
        stage_app._clear_stale_candidate()
        check("the cleanup actually deletes it",
              not (_rt / "candidate.json").exists())
    finally:
        make_app.DATA = _old_data
finally:
    import shutil
    shutil.rmtree(_rt, ignore_errors=True)
_verify_yml = source(".github/workflows/friday-verify.yml")
_verify_step = re.search(
    r"- name: Verify in a real browser.*?\n(.*?)\n      - name:", _verify_yml,
    re.S)
check("the verifier only runs when there is a fresh candidate",
      _verify_step is not None
      and "steps.fresh.outputs.fresh == 'yes'" in _verify_step.group(1),
      "without the gate a no-op week verifies and publishes the stale file")

# ------------------------------------------------- a rejection must clean up
# site/ is the published folder. The invoice-maker candidate failed every
# repair round, and its file still answered 200 at
# /apps/invoice-maker-basic/app/index.html because only candidate.json was
# deleted. Nothing linked to it, but a broken app was live.
print("\nA REJECTED APP IS TAKEN OFF THE PUBLIC SITE\n")
import json as _json
import shutil as _shutil

import verify_app

_reject = pathlib.Path(tempfile.mkdtemp(prefix="reject-selftest-"))
_real_apps, _real_cat = make_app.SITE_APPS, make_app.CATALOG
try:
    make_app.SITE_APPS = _reject / "site" / "apps"
    make_app.CATALOG = _reject / "apps.json"
    make_app.CATALOG.write_text("[]", encoding="utf-8")

    _folder = make_app.SITE_APPS / "bad-app-basic"
    (_folder / "app").mkdir(parents=True)
    (_folder / "app" / "index.html").write_text("<html></html>",
                                                encoding="utf-8")
    _stage_file = _reject / "candidate.json"
    _stage_file.write_text("{}", encoding="utf-8")
    verify_app.discard({"slug": "bad-app"}, _stage_file)
    check("a rejected candidate's site folder is removed",
          not _folder.exists())
    check("and the candidate file is gone", not _stage_file.exists())

    _live = make_app.SITE_APPS / "live-app-basic"
    (_live / "app").mkdir(parents=True)
    (_live / "app" / "index.html").write_text("<html></html>",
                                              encoding="utf-8")
    make_app.CATALOG.write_text(
        _json.dumps([{"slug": "live-app-basic", "published": True}]),
        encoding="utf-8")
    _stage2 = _reject / "candidate2.json"
    _stage2.write_text("{}", encoding="utf-8")
    verify_app.discard({"slug": "live-app"}, _stage2)
    check("a published app is never removed by a failed check", _live.exists())
    check("but its candidate file is still cleared", not _stage2.exists())
finally:
    make_app.SITE_APPS, make_app.CATALOG = _real_apps, _real_cat
    _shutil.rmtree(_reject, ignore_errors=True)
check("a failed verification still commits its cleanup",
      re.search(r"- name: Commit verification results\n        if: always\(\)",
                _verify_yml) is not None,
      "a rejection used to skip the commit, leaving the failed app on the site")

print("\nTHE INSTALLER REPORTS THE PRODUCT, NOT THE VENDOR\n")
_nsi = source("build_installer_app.py")
check("the product name is templated", 'Name "{name}"' in _nsi)
check("the version is read from the bundle",
      "_product_meta" in _nsi and '"{quad}"' in _nsi)
check("a missing icon is refused, not passed to makensis",
      "not Path(icon).exists()" in _nsi)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
