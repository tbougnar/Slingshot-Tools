"""The Short must find the paid app that was actually published.

A paid-only checkout has no public ``site/apps`` folder. The verifier uploads
the real interface as a private artifact, which the Shorts job restores into
``paid/`` before calling shots.py. These checks keep both locations visible,
keep the advertised product selected, and make a missing screenshot a warning
rather than a failed upload.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

import shots

fails = []


def check(name, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="shots-product-"))
(tmp / "data").mkdir()
for slug in ("alpha", "beta"):
    d = tmp / "paid" / slug / "app"
    d.mkdir(parents=True)
    (d / "index.html").write_text(f"<title>{slug} paid</title>", encoding="utf-8")
for slug in ("gamma-basic", "delta"):
    d = tmp / "site" / "apps" / slug / "app"
    d.mkdir(parents=True)
    (d / "index.html").write_text(f"<title>{slug} demo</title>", encoding="utf-8")
# A duplicate must resolve to the paid source, not to an older public copy.
dup = tmp / "site" / "apps" / "alpha" / "app"
dup.mkdir(parents=True)
(dup / "index.html").write_text("<title>alpha demo</title>", encoding="utf-8")
(tmp / "data" / "shorts_script.json").write_text(
    json.dumps({"slug": "beta", "name": "Beta"}), encoding="utf-8")

_real_root = shots.ROOT
_real_argv = sys.argv
_real_slug = os.environ.get("SHORTS_SLUG")
try:
    shots.ROOT = tmp
    sys.argv = ["shots.py"]
    os.environ.pop("SHORTS_SLUG", None)

    found = dict(shots.apps())
    check("paid and public app pages are both visible",
          set(found) == {"alpha", "beta", "gamma-basic", "delta"},
          str(sorted(found)))
    check("a duplicate resolves to the paid source",
          "paid" in found["alpha"].parts and
          found["alpha"].read_text(encoding="utf-8") == "<title>alpha paid</title>")

    check("the advertised product comes from the written script",
          shots.target_slug() == "beta", shots.target_slug())

    os.environ["SHORTS_SLUG"] = "ALPHA"
    check("an explicit slug is lowercased and wins",
          shots.target_slug() == "alpha", shots.target_slug())

    os.environ.pop("SHORTS_SLUG", None)
    sys.argv = ["shots.py", "--slug", "gamma-basic"]
    check("a command-line slug wins over the script",
          shots.target_slug() == "gamma-basic", shots.target_slug())

    # No browser is needed here: with no matching page the function returns
    # before it starts one.
    empty = pathlib.Path(tempfile.mkdtemp(prefix="shots-empty-"))
    (empty / "data").mkdir()
    shots.ROOT = empty
    sys.argv = ["shots.py"]
    shots.browser = lambda: "/bin/true"
    rc = shots.main()
    staged = empty / "data" / "shots.json"
    check("a missing screenshot does not fail the pipeline",
          rc == 0 and staged.exists() and
          json.loads(staged.read_text(encoding="utf-8")) == {},
          f"rc={rc}")
    shutil.rmtree(empty, ignore_errors=True)
finally:
    shots.ROOT = _real_root
    sys.argv = _real_argv
    if _real_slug is None:
        os.environ.pop("SHORTS_SLUG", None)
    else:
        os.environ["SHORTS_SLUG"] = _real_slug
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
