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
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_paid_only
import make_app

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

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)