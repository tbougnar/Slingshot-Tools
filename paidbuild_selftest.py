"""The installer job must build the upload it was actually given.

Two dispatches in quick succession produced a catalog holding unit-converter
while data/published.json still named dev-converter. The installer job took the
slug from published.json, looked for paid/dev-converter, did not find it, and
failed with "no paid build at .../dev-converter" while the correct build sat
right there under another name. The paid edition was never published because of
a stale field in a file the verifier writes.

A single uploaded build is unambiguous and is used, with the mismatch said
out loud. Two or more is ambiguous and must be refused rather than guessed.
"""
import json
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_paid_only
import make_app

# These scenarios deliberately drive the builder into every failure path, so
# they would otherwise fill the real audit log with BLOCKED and FAILED events
# that no run produced. A log full of test failures is not evidence of
# anything, so every event from this suite goes to a temporary file.
import auditlog as _auditlog

_real_log = _auditlog.LOG
_log_dir = pathlib.Path(tempfile.mkdtemp(prefix="paidbuild-selftest-"))
_auditlog.LOG = _log_dir / "events.jsonl"

# Restore on the way out even when a scenario raises. Without this a failure
# left every later audit write in this process pointing at the temp file, so
# the real log silently stopped recording.
import atexit


def _restore_log():
    _auditlog.LOG = _real_log
    shutil.rmtree(_log_dir, ignore_errors=True)


atexit.register(_restore_log)

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


def scenario(named, uploaded, write_stage=True):
    """Run build_paid_only --check against a paid/ tree built for the test."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    real_paid_dir, real_data = make_app.PAID_DIR, make_app.DATA
    real_staged = getattr(build_paid_only, "PAID", None)
    make_app.PAID_DIR = tmp / "paid"
    make_app.DATA = tmp / "data"
    make_app.DATA.mkdir(parents=True, exist_ok=True)
    if write_stage:
        (make_app.DATA / "published.json").write_text(
            json.dumps({"slug": named, "title": named, "price": 3.0}),
            encoding="utf-8")
    for name in uploaded:
        (make_app.PAID_DIR / name / "app").mkdir(parents=True, exist_ok=True)
        (make_app.PAID_DIR / name / "app" / "index.html").write_text(
            "<html><body>app</body></html>", encoding="utf-8")
        # find_existing also looks in dist/, which is not copied into the
        # cleanroom. Each scenario therefore supplies its own installer, so the
        # answer depends on which build was chosen rather than on whatever
        # happens to be lying around on the machine running the test.
        (make_app.PAID_DIR / name).mkdir(parents=True, exist_ok=True)
        (make_app.PAID_DIR / name / f"{name}-Setup.exe").write_bytes(
            b"MZ" + b"\0" * (3 * 1024 * 1024))
    if real_staged is not None:
        build_paid_only.PAID = tmp / "paid"
    try:
        rc = build_paid_only.main()
    finally:
        make_app.PAID_DIR, make_app.DATA = real_paid_dir, real_data
        if real_staged is not None:
            build_paid_only.PAID = real_staged
        shutil.rmtree(tmp, ignore_errors=True)
    return rc


print("\nTHE NAMED BUILD IS USED WHEN IT EXISTS\n")
sys.argv = ["build_paid_only.py", "--check"]
check("a build under the recorded slug is found",
      scenario("thing", ["thing"]) == 0)

print("\nA STALE SLUG FALLS BACK TO THE ONE UPLOAD\n")
check("one build under a different name is still built",
      scenario("dev-converter", ["unit-converter"]) == 0,
      "this is the failure the audit found")

print("\nAN AMBIGUOUS UPLOAD IS REFUSED, NOT GUESSED\n")
check("two builds and a stale slug is refused",
      scenario("nope", ["one-app", "two-app"]) == 1)

check("a stale slug with no builds at all is refused",
      scenario("nope", []) == 1)

print("\nNO STAGE FILE AT ALL, WHICH IS THE CI CASE\n")
# data/published.json is untracked, so the installer job's fresh checkout has
# none of it. The old code returned 0 here, so the step reported a successful
# build while producing no installer at all.
check("an uploaded build with no stage file is still built",
      scenario("", ["unit-converter"], write_stage=False) == 0,
      "this is the run that reported success and shipped nothing")

check("no build and no stage file is refused, not reported as success",
      scenario("", [], write_stage=False) == 1,
      "it returned 0 here and claimed a build it had not made")

print("\nNOTHING READS A STAGE FIELD THAT MAY NOT BE THERE\n")
# build() read stage["slug"] and publish() read it too, so with the stage file
# gone the installer job raised KeyError after it had already selected the
# right build. Reading a dict key is only safe when the key is guaranteed.
for name in ("build_paid_only.py",):
    body = (ROOT / name).read_text(encoding="utf-8", errors="replace")
    bad = [ln.strip() for ln in body.splitlines()
           if re.search(r'stage\["', ln) and not ln.strip().startswith("#")]
    check(f"{name} never indexes the stage dict directly", not bad,
          "; ".join(bad[:2]))

print("\nTHE TITLE COMES FROM THE BUILD WHEN THERE IS NO STAGE FILE\n")
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "concept.json").write_text(
    json.dumps({"title": "Colour Picker", "slug": "color-picker"}),
    encoding="utf-8")
check("a title is read out of the shipped concept.json",
      build_paid_only._title_from_build(tmp) == "Colour Picker")
(tmp / "concept.json").write_text("{not json", encoding="utf-8")
check("a corrupt concept.json yields no title rather than raising",
      build_paid_only._title_from_build(tmp) == "")

print("\nTHE CATALOG AND THE BUILD AGREE IN THE REPOSITORY\n")
# published.json is deliberately untracked now, so it only exists on a machine
# that has just run the verifier. When it does, it must name the build that is
# actually present; when it does not, there is nothing to disagree about.
stage = ROOT / "data" / "published.json"
if stage.exists():
    got = json.loads(stage.read_text(encoding="utf-8")).get("slug")
    paid = make_app.PAID_DIR / str(got)
    built = sorted(p.name for p in make_app.PAID_DIR.glob("*")
                   if p.is_dir()) if make_app.PAID_DIR.is_dir() else []
    check("the recorded slug is the one that has a build, or there are none",
          (not built) or paid.exists(),
          f"published.json names {got!r}; builds present: {built}")
else:
    print("skip  published.json is untracked and absent, which is correct "
          "between runs")

print("\nTHE FREE EDITION'S FOLDER IS NAMED ONCE\n")
# The free edition lives in site/apps/<slug>-basic, and that is the folder the
# catalogue links to. write_app adds the "-basic" suffix, so the slug it is
# given is the product's own slug. One caller passed an already-suffixed slug
# and produced "<slug>-basic-basic": the inner app file landed there, the
# published copy stayed stale, a duplicated slug went to GitHub Pages, and the
# release gate refused the build. Both forms have to give the same folder.
_html = ("<html><body><script>const TIER=\"basic\";</script></body></html>"
         * 30)
_tmp3 = pathlib.Path(tempfile.mkdtemp())
_real_apps, _real_paid = make_app.APPS_DIR, make_app.PAID_DIR
try:
    make_app.APPS_DIR = _tmp3 / "site" / "apps"
    make_app.PAID_DIR = _tmp3 / "paid"
    _concept = {"slug": "widget", "title": "Widget"}
    _plain = make_app.write_app({**_concept, "brand": "Widget"},
                                 _html, tier="basic")
    _suffixed = make_app.write_app({**_concept, "brand": "Widget",
                                    "slug": "widget-basic"},
                                   _html, tier="basic")
    check("the free edition's folder ends in -basic exactly once",
          _plain.name == "widget-basic" and _suffixed.name == "widget-basic",
          f"got {_plain.name!r} and {_suffixed.name!r}")
    check("and the app file is inside it",
          (_plain / "app" / "index.html").exists(),
          "the published copy the catalogue links to would be stale")
    check("the recorded slug matches the folder",
          json.loads((_plain / "concept.json").read_text(
              encoding="utf-8")).get("slug") == "widget-basic",
          "the catalogue would name a folder that does not exist")
finally:
    make_app.APPS_DIR, make_app.PAID_DIR = _real_apps, _real_paid
    shutil.rmtree(_tmp3, ignore_errors=True)

print("\nTHE REBUILD TOOL CAN ACTUALLY REBUILD\n")
# rebuild_paid.py exists to bring a product whose paid build is missing back
# on sale. It called build_exe.main(), which does not exist, so it died with
# an AttributeError after it had already written the product out, and the
# installer it could not build left the product off sale with a traceback
# instead of a sentence.
_rp = (ROOT / "rebuild_paid.py").read_text(encoding="utf-8")
# the comment in the file explains the mistake, so only the code is read
_rp_code = "\n".join(ln for ln in _rp.splitlines()
                     if not ln.strip().startswith("#"))
check("it does not call a function that does not exist",
      "build_exe.main()" not in _rp_code,
      "it calls build_exe.main(), and build_exe has no main()")
check("it builds the installer the way the Friday job does",
      "build_paid_only.build(" in _rp_code,
      "it does not use the build path that has been exercised")
check("and it accepts an installer named after the title",
      "concept.get(\"title\")" in _rp_code or "concept.get('title')" in _rp_code,
      "it compares the slug against the file name, and the installer is "
      "named after the title, so it refuses the correct one")
check("butler is given a project slug and not a URL",
      "STORE_PROJECT.rstrip(\"/\").rsplit(\"/\", 1)[-1]" in _rp_code,
      "the target is user/project:channel, and a URL in the project part "
      "is not a project")

print("\nSECOND PASS: STATE, PACKAGING, CAPTIONS AND FRAMES\n")
# Found by an independent audit pass, all reproduced before being fixed.
import update_state as us2

_tmp2 = pathlib.Path(tempfile.mkdtemp())
_real_state = us2.STATE
try:
    us2.STATE = _tmp2 / "update_state.json"
    us2.STATE.write_text(json.dumps(
        {"version": "2.0.0", "apps": {"password-manager": "1.4.0"}}),
        encoding="utf-8")
    _st = us2.load()
    check("load() keeps the per-app version map as a dict",
          isinstance(_st.get("apps"), dict)
          and _st["apps"].get("password-manager") == "1.4.0",
          f"apps is {type(_st.get('apps')).__name__}: {_st.get('apps')}")
    check("app_version() returns the recorded version, not the company one",
          us2.app_version(_st, "password-manager") == "1.4.0",
          str(us2.app_version(_st, "password-manager")))
    try:
        us2.set_app_version(_st, "recipe-scaler", "3.2.1")
        check("set_app_version() does not raise after load()", True)
    except TypeError as e:
        check("set_app_version() does not raise after load()", False, str(e))
    check("next_major_notes is still coerced to a list",
          isinstance(_st.get("next_major_notes"), list))
finally:
    us2.STATE = _real_state

import shorts_voice as svoice

for _dur, _txt in ((3.0, "one two three four five six"), (10.0, "a b c")):
    _m = svoice._words_from_text(_txt, _dur)
    check(f"captions for a {_dur}s line stay inside the clip",
          bool(_m) and all(x["offset"] <= _dur for x in _m),
          f"last offset {_m[-1]['offset'] if _m else None}")

_mux = (ROOT / "shorts_mux.py").read_text(encoding="utf-8")
check("the frame adjustment happens on disk, not on a discarded list",
      "frames_dir.glob(\"*.jpg\")" in _mux
      and "frames = frames + [frames[-1]]" not in _mux,
      "the padded list was never read by ffmpeg")
check("padding continues the ffmpeg numbering rather than overwriting",
      "have + i + 1" in _mux,
      "starting at have overwrites the last real frame")

_nsis = (ROOT / "build_installer_app.py").read_text(encoding="utf-8")
check("the NSIS return code is checked", "r.returncode != 0" in _nsis)
check("the previous installer is removed before the build",
      _nsis.find("unlink(missing_ok=True)") < _nsis.find("subprocess.run"),
      "a stale installer can be returned as this week's")

# A $3 download that opens a UAC box is the biggest drop-off a small app can
# have, and the per-machine folder is not writable, so a tool that keeps its
# data beside the exe breaks there. Per-user, like the free launcher.
check("the installer installs for the current user, without an admin prompt",
      "RequestExecutionLevel user" in _nsis
      and "RequestExecutionLevel admin" not in _nsis,
      "it still asks for elevation")
check("and it installs under the user's own programs folder",
      'InstallDir "$LOCALAPPDATA\\Programs\\Slingshot Tools\\{name}"' in _nsis,
      "it still writes into Program Files")
check("and the files land in that folder, not a folder inside it",
      'SetOutPath "$INSTDIR"' in _nsis
      and 'SetOutPath "$INSTDIR\\{name}"' not in _nsis,
      "install dir and file dir differ, so the app ends up one level deeper")
check("and the shortcuts follow the same folder",
      '"$INSTDIR\\{name}\\{exe}"' not in _nsis,
      "a shortcut points at the nested folder")

# The frozen launcher reads app/app.json for the window title and the update
# slug. No build step wrote one, so every paid app opened as "Slingshot Tool"
# and the update check asked the catalogue about an empty slug.
_meta_dir = pathlib.Path(tempfile.mkdtemp(prefix="paidmeta-selftest-"))
(_meta_dir / "app").mkdir()
(_meta_dir / "concept.json").write_text(
    json.dumps({"slug": "password-manager", "title": "Offline password manager"}),
    encoding="utf-8")
import build_exe as _be

_be.write_meta(_meta_dir, "Offline password manager")
_meta = json.loads((_meta_dir / "app" / "app.json").read_text(encoding="utf-8"))
check("the paid bundle carries the product's own title",
      _meta.get("title") == "Offline password manager", str(_meta))
check("and its catalogue slug, not the title with dashes", _meta.get("slug")
      == "password-manager", str(_meta))
check("and a version", bool(_meta.get("version")), str(_meta))

(_meta_dir / "app" / "app.json").write_text(
    json.dumps({"title": "Kept", "version": "2.1.0"}), encoding="utf-8")
_be.write_meta(_meta_dir, "Offline password manager")
_meta = json.loads((_meta_dir / "app" / "app.json").read_text(encoding="utf-8"))
check("a metadata file the build already wrote is not overwritten",
      _meta.get("title") == "Kept" and _meta.get("version") == "2.1.0"
      and _meta.get("slug") == "password-manager", str(_meta))

_auditlog.LOG = _real_log

# Re-publishing must not drop what another step proved. verify_app re-publishes
# the full entry with published=was_live, and a rebuild that lost itch_url left
# a "published for sale" product with no page to buy from, which the exposure
# gate refuses.
print("\nRE-PUBLISHING KEEPS THE STORE URL AND THE BUILT MARK\n")
_keep_dir = pathlib.Path(tempfile.mkdtemp(prefix="republish-selftest-"))
_real_cat = make_app.CATALOG
try:
    make_app.CATALOG = _keep_dir / "apps.json"
    make_app.CATALOG.write_text(json.dumps([{
        "slug": "dev-converter", "base_slug": "dev-converter",
        "tier": "full", "title": "Unit converter", "tag": "convert",
        "blurb": "old", "tags": ["convert"], "url": "", "price": 3.0,
        "free": False, "published": True,
        "itch_url": "https://slingshot-tools.itch.io/slingshot-tools",
        "built": True, "date": "2026-01-01"}]), encoding="utf-8")
    make_app.publish({"slug": "dev-converter", "base_slug": "dev-converter",
                      "title": "Unit converter", "tag": "convert",
                      "blurb": "new", "tags": ["convert"]},
                     _keep_dir, None, tier="full", published=True,
                     price_override=3.0)
    _kept = json.loads(make_app.CATALOG.read_text(encoding="utf-8"))[0]
    check("a re-published paid entry keeps its itch.io page",
          _kept.get("itch_url")
          == "https://slingshot-tools.itch.io/slingshot-tools", str(_kept))
    check("and still says a build exists", _kept.get("built") is True,
          str(_kept))
finally:
    make_app.CATALOG = _real_cat
    shutil.rmtree(_keep_dir, ignore_errors=True)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)