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
_auditlog.LOG = pathlib.Path(tempfile.mkdtemp(prefix="paidbuild-selftest-")) \
    / "events.jsonl"

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

_auditlog.LOG = _real_log

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)