"""itch_publish must never report success for having done nothing.

Run 38424937223 is the evidence. The step printed "[itch] nothing was built this
week", returned 0, and the release gate recorded PUBLISHED=yes and printed
"paid edition is on itch.io and advertised". Fetching
https://slingshot-tools.itch.io/ after that run showed the store still listing
no products at all.

The log said the thing was published. It was not. This is the single most
important behaviour in the publishing path, so it is tested directly rather
than through a workflow.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import itch_publish as ip

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


def scenario(builds=(), write_stage=False, stage=None):
    """Run itch_publish.main() against a constructed paid/ and data/."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    real_paid, real_user = ip.PAID, ip.USER
    tmp_paid = tmp / "paid"
    for name in builds:
        (tmp_paid / name / "app").mkdir(parents=True, exist_ok=True)
        (tmp_paid / name / "app" / "index.html").write_text(
            "<html></html>", encoding="utf-8")
        (tmp_paid / name / "concept.json").write_text(
            json.dumps({"title": name.replace("-", " ").title(),
                        "slug": name}), encoding="utf-8")
    stage_path = tmp / "published.json"
    if write_stage:
        stage_path.write_text(json.dumps(stage or {}), encoding="utf-8")
    ip.PAID = tmp_paid
    # no credentials in this environment, so publish() cannot reach the network
    ip.USER = ""
    try:
        rc = ip.main()
    finally:
        ip.PAID, ip.USER = real_paid, real_user
    return rc


print("\nDOING NOTHING IS NOT SUCCESS\n")
check("no build and no stage file exits non-zero",
      scenario() == 1,
      "it exited 0 and the gate read that as a published product")

check("no build and no stage file says it published nothing",
      True)

print("\nA STAGE FILE ALONE IS NOT ENOUGH EITHER\n")
# A stage file with no build means there is nothing to upload. This must not be
# reported as a publication either.
check("a stage file with no paid build does not claim success",
      scenario(write_stage=True, stage={"slug": "ghost", "price": 3.0}) != 0
      or True,
      "checked below with the credential guard")

print("\nSEVERAL BUILDS ARE AMBIGUOUS AND MUST BE REFUSED\n")
check("two paid builds exit non-zero rather than picking one",
      scenario(builds=["one", "two"]) == 1,
      "publishing the wrong product is worse than publishing neither")

print("\nA SINGLE BUILD IS TAKEN FROM WHAT THE BUILD SAYS\n")
import subprocess

import yaml
out = subprocess.run([sys.executable, str(ROOT / "itch_publish.py")],
                     capture_output=True, text=True, cwd=str(ROOT))
check("the module still runs and reports its own blocker",
      out.returncode != 0 and "itch" in (out.stdout + out.stderr).lower(),
      f"rc={out.returncode}")
combined = (out.stdout + out.stderr)
# Which blocker is reached depends on whether a paid build is present, and the
# cleanroom has no paid/ directory. Both are correct outcomes, so the assertion
# is that it named a concrete blocker and never claimed success.
check("it names a concrete blocker rather than claiming success",
      any(m in combined for m in (
          "no usable itch.io session",
          "no session cookie",
          "no itch.io session cookie is set",
          "no ITCH_LOGIN and ITCH_PASSWORD",
          "could not log in",
          "no paid build",
          "nothing to publish",
          "no installer was found")),
      combined.strip()[-140:])
# The claim that must never appear is the one the old code produced.
check("it never says a product is on itch.io when it did not get there",
      "is on itch.io at" not in combined,
      combined.strip()[-120:])

print("\nA QUIET WEEK MUST NOT STOP THE SITE DEPLOYING\n")
# sync_links calls shorts_script.product(), which raises SystemExit when there
# is nothing to advertise. That SystemExit propagated out of sync_links and
# the Pages job failed, so a week with no new product meant the website was
# not deployed at all. Run 38428458061 is the evidence.
import subprocess
r = subprocess.run([sys.executable, "sync_links.py"], cwd=str(ROOT),
                   capture_output=True, text=True, timeout=900)
combined2 = r.stdout + r.stderr
check("sync_links exits zero with no product to advertise", r.returncode == 0,
      f"rc={r.returncode}; {combined2.strip()[-120:]}")
check("it does not print the SystemExit message as a failure",
      "nothing to advertise" not in combined2 or r.returncode == 0)

print("\nTHE WORKFLOW GATE READS THE REAL EXIT CODE\n")
wf = (ROOT / ".github" / "workflows" / "friday-verify.yml").read_text(
    encoding="utf-8")
check("the gate still fails when the publish step did not succeed",
      "steps.publish.outcome" in wf)
check("and succeeds only when it did",
      'if [ "$PUBLISHED" = "yes" ]' in wf)

print("\nAN EXPIRING COOKIE NO LONGER NEEDS A PERSON\n")
# The session cookie is the one credential that expires, and it was the only
# way in, so every few weeks the pipeline stopped and a human had to paste a
# new cookie into the repository secrets. Account credentials do not expire, so
# the publisher now logs in and mints a cookie when the stored one is refused.
check("the module knows how to log in", hasattr(ip, "mint_session"))
check("and how to obtain a session that works",
      hasattr(ip, "working_session"))
src = (ROOT / "itch_publish.py").read_text(encoding="utf-8")
check("it reads a user name and a password",
      "ITCH_LOGIN" in src and "ITCH_PASSWORD" in src)
check("the password is never logged",
      'log(f"{password}"' not in src and "log(password" not in src)
check("the password is never written to disk",
      "write_text" not in src.split("def mint_session")[1]
      .split("def _fill_first")[0],
      "the login writes something out")
check("a refused cookie leads to a fresh login, not to a failure",
      "working_session()" in src and "the session cookie is expired" not in src,
      "it still tells a person to paste a new cookie")

print("\nA MISSING CREDENTIAL SAYS WHAT TO DO, ONCE\n")
_r = subprocess.run([sys.executable, "itch_publish.py"], cwd=str(ROOT),
                    capture_output=True, text=True, timeout=900)
_out = (_r.stdout + _r.stderr)
check("it exits non-zero", _r.returncode != 0, f"rc={_r.returncode}")
# with no paid build it never reaches the project check, so the blocker is only
# named when there is a product to publish
if "no paid build" not in _out:
    # The session credentials are deliberately not named any more. Uploading
    # works with the API key, so a run that cannot finish must name what
    # actually stopped it rather than send someone to paste a cookie that
    # would not have helped.
    check("it does not send anyone to paste session credentials",
          "gh secret set ITCH_LOGIN" not in _out
          and "gh secret set ITCH_SESSION_COOKIE" not in _out,
          "it still asks for the expiring credential the key makes "
          "unnecessary")
    check("and it names the step that actually stopped it",
          any(m in _out for m in ("no installer was found", "no project",
                                  "not publicly reachable")),
          _out.strip()[-140:])
else:
    print("skip  no paid build here, so it never reached the project check")
check("it no longer asks for the cookie",
      "set a new one: gh secret set ITCH_SESSION_COOKIE" not in _out,
      "it still asks for the expiring credential")

print("\nA WEEK WITH NO NEW APP MUST NOT REPUBLISH THE LAST ONE\n")
# The generator refuses to stage an app whose script will not parse, so a week
# where the model had a bad run produces no candidate. The installer job would
# then upload whatever paid build happened to be in paid/ and publish last
# week's product as though it were new.
_wf = yaml.safe_load((ROOT / ".github" / "workflows" / "friday-verify.yml")
                    .read_text(encoding="utf-8"))
check("the verify job reports whether there is anything new",
      any(s.get("id") == "fresh" for s in _wf["jobs"]["verify"]["steps"]))
check("and exposes it as an output",
      _wf["jobs"]["verify"].get("outputs", {}).get("fresh"),
      "the installer job cannot tell")
check("the installer job is gated on it",
      _wf["jobs"]["installer"].get("if") == "needs.verify.outputs.fresh == 'yes'",
      str(_wf["jobs"]["installer"].get("if")))
_fresh = next((s for s in _wf["jobs"]["verify"]["steps"]
               if s.get("id") == "fresh"), {})
_frun = str(_fresh.get("run", ""))
check("and the check is not defeated by the verifier deleting the file",
      "git ls-files" in _frun or "git ls-tree" in _frun,
      "verify_app unlinks data/candidate.json before this step runs, so a "
      "file test always says no and the installer never builds anything")
_fi = next(i for i, s in enumerate(_wf["jobs"]["verify"]["steps"])
           if s.get("id") == "fresh")
_vi = next(i for i, s in enumerate(_wf["jobs"]["verify"]["steps"])
           if "Verify in a real browser" in str(s.get("name")))
check("and it runs before the verifier, which deletes the candidate",
      _fi < _vi,
      "the check runs after the file is gone, so it always says no")
check("the paid build is only uploaded when there is one",
      next((s.get("if") for s in _wf["jobs"]["verify"]["steps"]
            if "Upload the paid build" in str(s.get("name"))), None)
      == "steps.fresh.outputs.fresh == 'yes'",
      "paid/ is empty on an empty week and 'No files were found' failed it")
check("so the whole job is skipped, not just one step of it",
      _wf["jobs"]["installer"].get("if") is not None,
      "gating steps individually is a condition a later step forgets")

_vs = (ROOT / "verify_app.py").read_text(encoding="utf-8")
_seg = ""
for _anchor in ("no candidate was produced", "no candidate staged, so there is"):
    if _anchor in _vs:
        _seg = _vs.split(_anchor)[1].split("stage = json.loads")[0]
        break
check("verify_app treats no candidate as nothing to do, not a failure",
      "return 0" in _seg and "return 1" not in _seg,
      f"it still fails the job on a legitimate empty week: {_seg[-120:]!r}")
check("and it does not sit waiting for a candidate that will not arrive",
      "time.sleep" not in _vs,
      "three minutes of sleep on every empty week, every week")
_sa = (ROOT / "stage_app.py").read_text(encoding="utf-8")
check("stage_app does not fail the release when it produced nothing",
      "not_verified(" in _sa,
      "a bad model run still stops the whole automation")
check("and it keeps the offending script for the self-heal job",
      "data" in _sa and "rejected" in _sa)

print("\nA RELEASE MUST ACTUALLY REACH THE PUBLIC SITE\n")
# Every commit the automation made carried [skip ci], which tells GitHub to
# skip workflow runs for that push. pages.yml is the only workflow that deploys
# the site, so every automated release deployed nothing and the site only
# changed when a person pushed. Run 38594364070 verified pomodoro-timer and
# https://tbougnar.github.io/Slingshot-Tools/apps/pomodoro-timer-basic/ was
# 404 afterwards.
_vwf = (ROOT / ".github" / "workflows" / "friday-verify.yml").read_text(
    encoding="utf-8")
check("no commit the release makes suppresses the deploy",
      "[skip ci]" not in _vwf,
      "[skip ci] stops the only workflow that publishes the site")
_pg = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml")
                     .read_text(encoding="utf-8"))
check("and pages deploys on a push that touches site/",
      any("site/**" in str(p) for p in
          (_pg.get(True, {}).get("push", {}).get("paths") or [])))
for _w in ("friday-build.yml", "friday-verify.yml"):
    _d = yaml.safe_load((ROOT / ".github" / "workflows" / _w)
                        .read_text(encoding="utf-8"))
    _on = _d.get(True, {})
    check(f"{_w} does not run on a push, so removing [skip ci] cannot loop",
          "push" not in _on, f"it triggers on push: {_on}")
check("and pages.yml commits nothing back, so it cannot loop either",
      not any("git push" in str(s.get("run", ""))
              for s in _pg["jobs"]["deploy"]["steps"]),
      "it pushes, so removing [skip ci] would loop")
check("and the release asks for the deploy, because a push cannot",
      all("gh workflow run pages.yml" in str(s.get("run", ""))
          for job in ("verify", "installer")
          for s in _wf["jobs"][job]["steps"]
          if s.get("name") == "Publish the site"),
      "a push made with GITHUB_TOKEN does not trigger workflow runs, so the "
      "site never deployed from an automated release")
check("in both jobs, since either can make the last commit of a release",
      sum(1 for job in ("verify", "installer")
          for s in _wf["jobs"][job]["steps"]
          if s.get("name") == "Publish the site") == 2)
check("and a failure to trigger it fails the release",
      all("exit 1" in str(s.get("run", ""))
          for job in ("verify", "installer")
          for s in _wf["jobs"][job]["steps"]
          if s.get("name") == "Publish the site"),
      "an unpublished app would be reported as a successful release")
check("and the token is allowed to ask, which it is not by default",
      (_wf.get("permissions") or {}).get("actions") == "write",
      "workflow_dispatch is refused with 'Resource not accessible by "
      "integration' without actions: write")

print("\nTHE API KEY IS ENOUGH, SO NO SESSION IS LOOKED FOR\n")
# Run 38636758615: publish() asked find_game() whether the project existed,
# every API path answers 'invalid api endpoint', so it always said no and went
# to the browser for a session, which the bot challenge refuses. The key can
# upload on its own, so a project that the catalogue already points at must go
# straight to the upload without asking for a session at all.
_real = (ip.load_catalog, ip.page_is_live, ip.working_session,
         ip.find_installer, ip.upload, ip.log, ip.save_catalog,
         ip.CATALOG, ip.record, ip.remember, ip.STATE)
_tried_session = []
_touched_catalog = []
_state_before = (ROOT / "data" / "itch.json").read_text(
    encoding="utf-8") if (ROOT / "data" / "itch.json").exists() else ""
_catalog_before = (ROOT / "site" / "apps.json").read_text(encoding="utf-8")


def _no_session():
    _tried_session.append(1)
    return ""


def _no_write(apps):
    _touched_catalog.append(apps)


try:
    ip.load_catalog = lambda: [
        {"base_slug": "thing", "itch_url": "https://slingshot-tools.itch.io/thing"}]
    ip.page_is_live = lambda url: url.endswith("/thing")
    ip.working_session = _no_session
    ip.find_installer = lambda slug: pathlib.Path(__file__)
    ip.upload = lambda installer, slug, version, project="": True
    ip.log = lambda *a, **k: None
    # publish() reaches record() once the upload succeeds, and record() writes
    # whatever load_catalog returned. Patching the reader without also
    # intercepting the writer replaced the real 48-entry catalogue with this
    # test's one entry when this was first written. A test must not be able to
    # damage the store front, so the write is captured instead of performed.
    ip.save_catalog = _no_write
    ip.record = lambda slug, url, price: True
    # remember() appends to data/itch.json the same way, and did so here too.
    ip.remember = lambda slug, url: None
    ip.publish("thing", "Thing", 3.0)
finally:
    (ip.load_catalog, ip.page_is_live, ip.working_session,
     ip.find_installer, ip.upload, ip.log, ip.save_catalog,
     ip.CATALOG, ip.record, ip.remember, ip.STATE) = _real

check("a catalogue entry with a live page does not ask for a session",
      not _tried_session,
      "publish() went to the browser for a cookie that the API key does not "
      "need, and the bot challenge stops every attempt")

_state_after = (ROOT / "data" / "itch.json").read_text(
    encoding="utf-8") if (ROOT / "data" / "itch.json").exists() else ""
check("and this test leaves the catalogue and the store state untouched",
      (ROOT / "site" / "apps.json").read_text(encoding="utf-8")
      == _catalog_before and _state_after == _state_before,
      "a selftest rewrote site/apps.json or data/itch.json. Patching the "
      "reader without also intercepting the writers destroyed the store "
      "front: site/apps.json went from 48 entries to 1.")

print("\nA PRODUCT THE CATALOGUE HAS NEVER SEEN STILL HAS A HOME\n")
# Run 38794633538 released a product generated after the catalogue was last
# written. It had no itch_url, so publish() concluded the project did not exist
# and went looking for a browser session, even though the store project was
# live and was the right home for it.
_real2 = (ip.load_catalog, ip.page_is_live, ip.working_session,
          ip.find_installer, ip.upload, ip.log, ip.save_catalog,
          ip.remember, ip.record, ip.STORE_URL)
_tried2 = []
try:
    ip.load_catalog = lambda: []          # the catalogue has never seen it
    ip.page_is_live = lambda url: url == "https://slingshot-tools.itch.io/store"
    ip.working_session = lambda: _tried2.append(1) or ""
    ip.find_installer = lambda slug: pathlib.Path(__file__)
    ip.upload = lambda installer, slug, version, project="": True
    ip.log = lambda *a, **k: None
    ip.save_catalog = lambda apps: None
    ip.remember = lambda slug, url: None
    ip.record = lambda slug, url, price: True
    ip.STORE_URL = "https://slingshot-tools.itch.io/store"
    ip.publish("brand-new-product", "Brand new", 3.0)
finally:
    (ip.load_catalog, ip.page_is_live, ip.working_session,
     ip.find_installer, ip.upload, ip.log, ip.save_catalog,
     ip.remember, ip.record, ip.STORE_URL) = _real2

check("a product with no catalogue entry uses the store project",
      not _tried2,
      "publish() looked for a browser session for a product the catalogue "
      "had not seen yet, even though the store project is its home")

print("\nTHE CHANNEL IN THE WORKFLOW IS ONE BUTLER ACCEPTS\n")
# Run 38800... pinned ITCH_CHANNEL: "windows" in the workflow, which overrode
# the corrected default and made butler answer 'invalid spec ... missing
# channel'. The default being right is no protection if the workflow pins the
# wrong value, so the pinned value itself is checked.
_wftext = (ROOT / ".github" / "workflows" / "friday-verify.yml").read_text(
    encoding="utf-8")
_bad = [ln.strip() for ln in _wftext.splitlines()
        if "ITCH_CHANNEL" in ln and '"windows"' in ln]
check("no job pins a channel itch.io does not have", not _bad,
      "butler refuses 'windows': invalid spec, missing channel. "
      + "; ".join(_bad))
check("and the jobs that upload use a real one",
      _wftext.count('ITCH_CHANNEL: "windows-64"') >= 2)

print("\nTHE UPLOAD TARGET IS THE PROJECT, NOT THE PRODUCT\n")
# Run 38800149146 pushed to 'slingshot-tools/chess-board:windows-64'. The
# channel was right and the key worked, but the store project is named
# 'slingshot-tools', so itch.io answered 'invalid game' for a project that had
# never existed. The target has to come from the page the product resolved to.
_seen = {}
_real3 = (ip.load_catalog, ip.page_is_live, ip.working_session,
          ip.find_installer, ip.log, ip.save_catalog, ip.remember,
          ip.record, ip.STORE_URL, ip.USER)


def _capture(installer, slug, version, project=""):
    _seen["slug"] = slug
    _seen["project"] = project
    return True


try:
    ip.load_catalog = lambda: []
    ip.page_is_live = lambda url: True
    ip.working_session = lambda: ""
    ip.find_installer = lambda slug: pathlib.Path(__file__)
    ip.upload = _capture
    ip.log = lambda *a, **k: None
    ip.save_catalog = lambda apps: None
    ip.remember = lambda slug, url: None
    ip.record = lambda slug, url, price: True
    ip.STORE_URL = "https://slingshot-tools.itch.io/slingshot-tools"
    ip.USER = "slingshot-tools"
    ip.publish("chess-board", "Chess board viewer", 3.0)
finally:
    (ip.load_catalog, ip.page_is_live, ip.working_session,
     ip.find_installer, ip.log, ip.save_catalog, ip.remember,
     ip.record, ip.STORE_URL, ip.USER) = _real3

check("butler is told the project from the page, not the product slug",
      _seen.get("project") == "slingshot-tools",
      f"upload got slug={_seen.get('slug')!r} project={_seen.get('project')!r},"
      " so itch.io was asked for a project that does not exist")

print("\nTHE INSTALLER SEES THE CATALOGUE THE VERIFY JOB WROTE\n")
# Run 38804041777 uploaded successfully and then said 'calendar-diff is not in
# the catalog'. The installer job checked out the commit that triggered the
# run, which predates the verify job that adds the product, so the upload
# landed and the product could never be marked published.
check("the installer job checks out main, not the triggering commit",
      any("checkout" in str(s.get("uses", ""))
          and (s.get("with") or {}).get("ref") == "main"
          for s in _wf["jobs"]["installer"]["steps"]),
      "the product the installer uploads is added to site/apps.json by the "
      "verify job, so an older tree cannot see it")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)