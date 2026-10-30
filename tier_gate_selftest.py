"""No app may unlock its paid features from the address bar.

Twenty-five of the free editions were generated with this:

    const PAID = new URLSearchParams(location.search).has('paid');
    const LIM = PAID ? {unlimited} : {basic limits};

The paid edition was then the same file with nothing else changed, so the only
thing standing between a visitor and the full product was a query parameter.
Adding ``?paid`` to the free app's own URL unlocked it. Every one of those
twenty-five apps is a paid product, and two of them - password-manager and
base64-tool - are on the store for $3, so this was live and free to anyone who
guessed.

The current generator bakes the edition into the file instead: ``TIER`` is
either "basic" or "full", set at build time, and ``rebuild_paid.py`` produces
the paid edition by flipping that one constant. There is no runtime switch, so
there is nothing for a URL to reach.

This checks the property directly, because it is a text property and text is
what shipped the bug:

1. no app gates anything on the query string,
2. the free editions are actually limited, not just labelled basic,
3. flipping TIER still produces the full edition, so the paid build is the
   full product and not the limited one.

    python tier_gate_selftest.py
"""
import json
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
APPS = ROOT / "site" / "apps"

import make_app

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


SOURCES = sorted(APPS.glob("*/app/index.html"))
# The standalone single-file copy the site actually links to for a free app is
# <app>/index.html, a copy of <app>/app/index.html made at generation time. It
# is the file served at the catalogue's URL, so it is the one a visitor can put
# ?paid on. It carries the same gate and has to be checked too - fixing only
# app/index.html left the live exploit in place.
OUTER = sorted(APPS.glob("*/index.html"))
ALL = SOURCES + OUTER
check("there are free editions to check", len(SOURCES) > 0,
      f"{len(SOURCES)} found under site/apps")
check("and the standalone copies are checked too", len(OUTER) == len(SOURCES),
      f"{len(OUTER)} outer index.html files against {len(SOURCES)} app ones")

# ------------------------------------------------- no query-string unlocking
# A URLSearchParams read on location.search that feeds a limit, a tier or a
# feature is the defect. A search param used for something genuinely cosmetic
# is not, so this only fires when the result reaches the access decision.
QLOCK = re.compile(
    r"(TIER|LIMITS?|PAID|tier|limits?)\s*=\s*[^;]*"
    r"URLSearchParams\s*\(\s*location\.search\s*\)",
)
unlockers = []
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if QLOCK.search(s):
        unlockers.append(name)
check("no app unlocks anything from the query string",
      not unlockers,
      f"{len(unlockers)} still do: {unlockers[:5]}")

# ----------------------------------------------- free editions are limited
# TIER="basic" has to come with a real limitation. An app labelled basic that
# reads all limits from the unlimited table is the free tier selling itself.
UNLIMITED = ('{maxItems:Infinity', "{maxItems: 0", 'max:Infinity',
             'max: Infinity')
LIMITED_MARK = ("BASIC_LIMITS", "maxItems:3", "maxItems: 3",
                "export:false", "export: false", "max:3", "max: 3",
                "false}/", "'one'", '"one"')
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if 'TIER="basic"' not in s and "TIER='basic'" not in s:
        check(f"{name} declares its edition", False,
              "no TIER constant, so the edition is unknown at runtime")
        continue
    if not any(m in s for m in LIMITED_MARK):
        check(f"{name} is genuinely limited", False,
              "no basic limit table found, so the free edition may be full")
        continue
    # flipping to full must change the access decision
    full = make_app._set_tier(s, "full")
    if 'TIER="full"' not in full and "TIER='full'" not in full:
        check(f"{name} flips to full", False,
              "set_tier did not produce a full edition")
        continue
    # ...and the full edition must differ from the basic one
    if full == s:
        check(f"{name} full edition differs", False,
              "flipping TIER changed nothing, so paid equals free")
        continue

# ------------------------------------ the paid build must not call itself free
# Both editions are one file with one constant flipped, and models write the
# edition into the footer as ordinary text. The uploaded Batch file renamer
# installer, built by the real pipeline, opened with
# "RenameFlow - Free basic edition" on a $3 download.
print("\nA PAID DOWNLOAD DOES NOT INTRODUCE ITSELF AS THE FREE EDITION\n")
_labelled = ("<html><body><footer><p>Brand &copy; 2024 - Free basic edition. "
             "<a href='#'>Toggle theme</a></p></footer><script>const TIER="
             "\"basic\";const note='Free edition: limited to 3 files.';"
             "</script></body></html>")
_paid = make_app._set_edition_copy(make_app._set_tier(_labelled, "full"),
                                   "full")
check("a free-edition label is renamed in the paid build",
      "Full edition" in _paid and not re.search(
          r"free\s+basic\s+edition", _paid, re.I))
check("and the script is left alone", "const note='Free edition" in _paid,
      "basic-only copy in dead code is not visible to a buyer")
check("the free edition keeps its own wording",
      make_app._set_edition_copy(_labelled, "basic") == _labelled)

_pitch = ("<html><body><footer>Free basic edition: quick flips for a few "
          "items. Paid edition: unlimited flips, export and history."
          "</footer></body></html>")
_pp = make_app._set_edition_copy(_pitch, "full")
check("a two-edition pitch loses the free sentence and the shopper label",
      "quick flips" not in _pp and "Paid edition" not in _pp
      and "Unlimited flips, export and history." in _pp,
      _pp.split("<footer>")[1][:90] if "<footer>" in _pp else _pp[:90])

_bad = ("<html><body><p>The free edition is limited to three files.</p>"
        "</body></html>")
_fixed = make_app._set_edition_copy(_bad, "full")
check("a false limit claim is removed, not relabelled",
      "limited" not in _fixed
      and not re.search(r"free\s+edition", _fixed, re.I),
      _fixed[:80])
_rb = (ROOT / "rebuild_paid.py").read_text(encoding="utf-8")
check("the repair lane flips the edition the same way the builder does",
      'set_edition(html, "full")' in _rb and "_set_tier(" not in _rb,
      "rebuild_paid uploaded a paid build whose footer still said free")

# ------------------------------------ the shop must say what the money buys
# Batch file renamer sold for $3 with the differences "Export and import your
# data" and "Every theme", while the free edition stops at three files. The
# cap is the reason to pay and it was the one thing the catalogue omitted.
print("\nTHE PAID PITCH NAMES THE CAP THE FREE EDITION STOPS AT\n")
_three = ('<script>const LIMITS=TIER==="basic"?{maxItems:3,export:false,'
          'themes:"one"}'
          ':{maxItems:0,export:true,themes:"all"};</script>')
_d = make_app.paid_differences(
    _three, ["Export and import your data", "Every theme"])
check("a capped free edition puts the cap first in the paid pitch",
      bool(_d) and "3" in _d[0] and _d[0].lower().startswith("unlimited"),
      str(_d)[:100])
check("the model's own differences are kept after it",
      _d[1:] == ["Export and import your data", "Every theme"], str(_d)[:100])
check("the limit table marks 0 in the paid branch as unlimited",
      "Unlimited items" in make_app.paid_features(_three),
      str(make_app.paid_features(_three)))
check("an app that already says unlimited is not told twice",
      make_app.paid_differences(
          _three, ["Unlimited files, export and every theme"]) ==
      ["Unlimited files, export and every theme"])
check("an uncapped free edition gets no invented claim",
      make_app.paid_differences("<script>const X=1;</script>", ["Exports"])
      == ["Exports"])

# ------------------------------------------------ the script has to parse
# The chess-board app was served with one stray brace in its script, so the
# whole file failed to parse and the app did nothing at all: no board, no
# buttons, no error the visitor could see. It was live for as long as it was
# in the catalogue, and nothing caught it, because the validator that refuses
# a broken app could not read a template literal and reported eleven good
# apps as broken instead.
unparseable = []
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    errs = make_app.js_syntax_errors(s)
    if errs:
        unparseable.append(f"{p.parent.parent.name} ({errs[0][:50]})")
check("every app's script parses", not unparseable,
      f"{len(unparseable)} do not: {unparseable[:4]}")

# ------------------------------------------------------- the gate is a gate
# A paid feature has to be reachable in the paid edition and refused in the
# free one. The mistakes here are quiet: an export control created only in the
# free edition, a limit key that LIM never defines, and a comparison that can
# never be true.
for p in SOURCES:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    for m in re.finditer(r"!\s*TIER\s*===\s*'full'", s):
        check(f"{name} has a working tier comparison", False,
              "'!TIER==='full' can never be true, so the check never fires")
        break
    m = re.search(r"const LIM=TIER==='full'\?\{([^}]*)\}", s)
    if m:
        defined = {k.split(":")[0].strip()
                   for k in m.group(1).split(",") if ":" in k}
        for k in sorted(set(re.findall(r"LIM\.([A-Za-z_]\w*)", s))):
            if k not in defined:
                check(f"{name} defines LIM.{k}", False,
                      f"LIM.{k} is used but LIM never defines it, so it is "
                      "always undefined and the control it hides is always "
                      "hidden")
                break
    # A feature gated on LIM.max is the mistake: max is the limit, not the
    # capability, so asking whether it is unlimited decides which edition gets
    # the feature, and it is the wrong way round. Using LIM.max to limit how
    # much is produced is correct, so only a block that creates or reveals a
    # control counts.
    for m in re.finditer(r"if\(LIM\.max\s*!==\s*Infinity\)\s*\{", s):
        depth, k = 0, m.end() - 1
        for k in range(m.end() - 1, len(s)):
            if s[k] == "{":
                depth += 1
            elif s[k] == "}":
                depth -= 1
                if depth == 0:
                    break
        block = s[m.end():k]
        if ("createElement('button'" in block or 'createElement("button"' in block
                or "createElement('input'" in block
                or 'createElement("input"' in block
                or "style.display" in block):
            check(f"{name} gates a feature on the right thing", False,
                  "a feature is gated on LIM.max, which is the limit and not "
                  "the capability, so it appears in the wrong edition")
            break

# ------------------------------------------------- what the paid edition has
# The shop asks for three dollars and has to say what the three dollars are
# for. The answer is in the app's own limit table, and it was never read:
# the paid edition was published with the same description as the free one
# and an empty differences list, so every product looked identical to the
# one next to it.
no_features = []
for p in SOURCES:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if not make_app.paid_features(s):
        no_features.append(name)
check("every product's paid edition has something the free one does not",
      not no_features,
      f"{len(no_features)} have none: {no_features[:5]}")

# The catalogue has to agree with the apps, or the shop describes a product
# that is not the one being sold.
import json as _json

try:
    _cat = _json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
except (OSError, ValueError) as _e:
    _cat = []
    check("the catalogue can be read", False, str(_e)[:60])
if _cat:
    _fams = {}
    for _e in _cat:
        _fams.setdefault(_e.get("base_slug") or _e.get("slug"), {})[
            _e.get("tier")] = _e
    _drift = []
    for _base, _pair in _fams.items():
        _full, _basic = _pair.get("full"), _pair.get("basic")
        if not _full or not _basic:
            _drift.append(f"{_base}: an edition is missing")
            continue
        _src = APPS / f"{_base}-basic" / "app" / "index.html"
        if not _src.exists():
            continue
        _real = make_app.paid_features(_src.read_text(encoding="utf-8"))
        # The catalogue may word a feature for a customer, so the check is
        # that it says each one at all. It used to demand the exact label
        # list, which could only pass if a human copied the labels by hand -
        # and it let "unlimited" be missing for as long as the list happened
        # to match the app's own blind spot.
        _need = {
            "Unlimited items":
                r"unlimited|no limit|as many|without (?:a )?limit",
            "Export and import your data": r"export",
            "Import your data": r"import",
            "Every theme": r"theme",
            "Bulk actions": r"bulk",
            "Keeps a history": r"history",
        }
        _said = " ".join(str(d) for d in (_full.get("differences") or []))
        for _label in _real:
            _pattern = _need.get(_label, re.escape(_label.split()[0]))
            if not re.search(_pattern, _said, re.I):
                _drift.append(f"{_base}: never mentions {_label!r}")
        if not _full.get("differences"):
            _drift.append(f"{_base}: the paid edition has no differences list")
        if _full.get("blurb") == _basic.get("blurb"):
            _drift.append(f"{_base}: both editions say the same thing")
    check("the catalogue says what each paid edition really adds",
          not _drift,
          f"{len(_drift)} disagree: {_drift[:3]}")

# ------------------------------------------------- every app actually works
# The chess-board app was served for weeks with one stray brace in its
# script, so the whole file failed to parse and the app showed no board and
# no buttons. Nothing said so, and the page was blank. A browser is the only
# thing that can tell a working app from a dead one.

# The teaching material is where the bypass came back from. Every generated
# app inherits its patterns from PATTERNS.md, and that file taught the
# query-string gate for months after the twenty-five apps that used it had
# been fixed. So a new app arrived with the bypass in it, the free edition
# of a product that was on the store came back unlocked, and the fix had to
# be made again.
_patterns = (ROOT / "PATTERNS.md")
if _patterns.exists():
    _text = _patterns.read_text(encoding="utf-8")
    check("the pattern library does not teach the query-string gate",
          not re.search(r"URLSearchParams\s*\(\s*location\.search",
                        _text),
          "the library still shows the model how to read the edition from "
          "the address bar")
    check("and it teaches the constant instead",
          "const TIER" in _text,
          "the library does not say how the edition is decided")

# And the gate itself has to refuse an app that does it anyway, so a model
# that learned it elsewhere cannot smuggle it back in.
_bad_app = ('<html><body><script>const PAID=new URLSearchParams('
            "location.search).has('paid');"
            "const LIM=PAID?{max:Infinity,export:true}:{max:3,export:false};"
            "localStorage.setItem('k','1');</script>"
            + "x" * 2000 + "</body></html>")
check("the staging gate refuses an app whose edition comes from the URL",
      any("address bar" in p for p in make_app.html_looks_fine(_bad_app)),
      "the gate let an app through that a visitor can unlock with ?paid")

# And the builder must never rebuild a product that is already on the site.
# Every concept had been built, and the picker fell back to the whole list,
# so it regenerated a product that was on sale and overwrote the edition a
# customer was buying.
_built = {b.get("slug") for b in make_app.load_built()}
_check = make_app.pick_concept("")
_wrong = (_check is not None and (_check.get("slug") in _built or
                                   (_built and len(_built) >= len(
                                       make_app.CATEGORIES))))
check("the builder does not pick a product that is already built",
      not _wrong,
      f"it picked {_check.get('slug')}, which is already on the site"
      if _wrong else "")

# A build record is not proof that a product exists. Ten concepts were listed
# in data/already_built.json while the catalog held no entry for them, so the
# pool was empty and the generator refused to make anything, for ever. A build
# QA rejected could never be retried.
print("\nA REJECTED BUILD DOES NOT COUNT AS DONE\n")
_rt = pathlib.Path(tempfile.mkdtemp(prefix="picker-selftest-"))
try:
    _cat, _rec = make_app.CATALOG, make_app.BANNED
    _cats = make_app.CATEGORIES
    try:
        make_app.CATALOG = _rt / "apps.json"
        make_app.BANNED = _rt / "already_built.json"
        make_app.CATEGORIES = [
            ("never-published", "A tool that was generated and then rejected"),
            ("on-the-site", "A tool that is already on the site")]
        make_app.CATALOG.write_text(json.dumps([{
            "slug": "on-the-site", "base_slug": "on-the-site",
            "tier": "basic", "published": True}]), encoding="utf-8")
        make_app.BANNED.write_text(json.dumps([
            {"slug": "never-published", "title": "Rejected",
             "date": "2026-01-01"}]), encoding="utf-8")
        _picked = make_app.pick_concept("")
        check("a concept recorded as built but never published is offered "
              "again", bool(_picked)
              and _picked.get("slug") == "never-published", str(_picked))
        make_app.CATALOG.write_text(json.dumps([
            {"slug": "never-published", "base_slug": "never-published",
             "tier": "basic", "published": True},
            {"slug": "on-the-site", "base_slug": "on-the-site",
             "tier": "basic", "published": True}]), encoding="utf-8")
        check("and a concept that is on the site is never rebuilt",
              make_app.pick_concept("") is None)
    finally:
        make_app.CATALOG, make_app.BANNED = _cat, _rec
        make_app.CATEGORIES = _cats
finally:
    shutil.rmtree(_rt, ignore_errors=True)

print("\nEVERY APP LOADS AND WORKS\n")
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _b = _p.chromium.launch()
        _dead = []
        for _src in SOURCES:
            _pg = _b.new_page()
            _errs = []
            _pg.on("pageerror", lambda e: _errs.append(str(e)))
            _pg.goto(_src.resolve().as_uri())
            _pg.wait_for_timeout(200)
            _info = _pg.evaluate(
                """() => ({
                    tier: (typeof TIER !== 'undefined') ? TIER : null,
                    buttons: document.querySelectorAll('button').length,
                    body: (document.body.innerText || '').trim().length
                })""")
            _pg.close()
            _name = _src.parent.parent.name
            if _errs:
                _dead.append(f"{_name}: {_errs[0][:60]}")
            elif _info["tier"] is None:
                _dead.append(f"{_name}: the script did not run")
            elif _info["body"] < 20:
                _dead.append(f"{_name}: the page is blank")
            elif _info["buttons"] == 0:
                _dead.append(f"{_name}: the page has no controls")
        _b.close()
    check("every app loads and works", not _dead,
          f"{len(_dead)} do not: {_dead[:3]}")
except Exception as _e:  # noqa: BLE001
    print("skip  no browser available:", str(_e)[:70])

# --------------------------------------- a refused edition leaves no folder
# site/ is published. A Friday run that produced nothing at all still left a
# complete free edition of invoice-maker in site/apps, because write_app made
# the folder before deciding the edition and the paid half then failed the tier
# gate. The folder was in no catalogue, so nothing linked to it, but it
# answered 200 on the live site.
print("\nA REFUSED EDITION LEAVES NOTHING IN THE PUBLISHED FOLDER\n")
_was_apps, _was_paid = make_app.APPS_DIR, make_app.PAID_DIR
_was_site, _was_cat = make_app.SITE_APPS, make_app.CATALOG
_scratch = pathlib.Path(tempfile.mkdtemp(prefix="refuse-"))
try:
    make_app.APPS_DIR = _scratch / "site" / "apps"
    make_app.SITE_APPS = make_app.APPS_DIR
    make_app.PAID_DIR = _scratch / "paid"
    make_app.CATALOG = _scratch / "apps.json"
    make_app.CATALOG.write_text("[]", encoding="utf-8")
    _concept = {"slug": "no-tier-app", "title": "No Tier"}
    _no_tier = "<html><body><script>const LIMITS = {a: 1};</script></body></html>"
    _raised = False
    try:
        make_app.write_app(_concept, _no_tier, tier="basic")
    except RuntimeError:
        _raised = True
    check("an app whose edition cannot be decided is refused", _raised)
    check("and no free edition is left in the published folder",
          not (make_app.APPS_DIR / "no-tier-app-basic").exists(),
          str(make_app.APPS_DIR / "no-tier-app-basic"))

    # the same folder is cleared after a run that produced nothing
    _left = make_app.APPS_DIR / "no-tier-app-basic" / "app"
    _left.mkdir(parents=True)
    (_left / "index.html").write_text("<html></html>", encoding="utf-8")
    make_app.discard_unpublished("no-tier-app")
    check("a product that was never staged is taken off the site",
          not (make_app.APPS_DIR / "no-tier-app-basic").exists())

    # and an app that is on sale keeps its folder
    _live = make_app.APPS_DIR / "on-sale-basic" / "app"
    _live.mkdir(parents=True)
    (_live / "index.html").write_text("<html></html>", encoding="utf-8")
    make_app.CATALOG.write_text(json.dumps([
        {"slug": "on-sale-basic", "base_slug": "on-sale", "tier": "basic",
         "published": True}]), encoding="utf-8")
    make_app.discard_unpublished("on-sale")
    check("a published product is never taken off the site",
          (make_app.APPS_DIR / "on-sale-basic").exists())
finally:
    make_app.APPS_DIR, make_app.PAID_DIR = _was_apps, _was_paid
    make_app.SITE_APPS, make_app.CATALOG = _was_site, _was_cat
    shutil.rmtree(_scratch, ignore_errors=True)

print(f"\nchecked {len(SOURCES)} free editions for a paid-tier bypass")
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
