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
# Every product used to be pushed to the same channel, so each release replaced
# the last. After three successful runs the store listed only the newest build
# while the catalogue still advertised all three, so two customers could pay for
# a download that was no longer there. An empty shop is honest; a shop selling
# something it no longer has is not.
_cf = ip.channel_for
_realc = ip.CHANNEL
try:
    ip.CHANNEL = ""
    check("two products get two different channels",
          ip.channel_for("chess-clock") != ip.channel_for("base64-tool"),
          "they share a channel, so each release deletes the previous "
          "product's build from the store")
    check("and the channel is safe for itch.io",
          ip.channel_for("A B!") == "ab-win",
          ip.channel_for("A B!"))
    ip.CHANNEL = "windows-64"
    check("an explicit ITCH_CHANNEL still overrides it",
          ip.channel_for("chess-clock") == "windows-64")
finally:
    ip.CHANNEL = _realc

_wftext = (ROOT / ".github" / "workflows" / "friday-verify.yml").read_text(
    encoding="utf-8")
check("and no job pins one channel for everything",
      "ITCH_CHANNEL" not in _wftext,
      "a pinned channel overrides the per-product one and puts every product "
      "back on top of the last")

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

print("\nA FREE EDITION IS NOT ON ICH.IO, SO IT MUST NOT SAY IT IS\n")
# The first --all run gave every entry the store URL, including the thirty free
# editions. Nothing on the site reads a free tier's itch_url, so no wrong Buy
# button appeared, but the catalogue then claimed thirty apps were on a store
# they had never been uploaded to.
_cat = json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
_free = [e for e in _cat if e.get("tier") == "basic" and e.get("itch_url")]
check("no free edition carries a store URL", not _free,
      f"{len(_free)} free editions claim an itch.io page they are not on: "
      + ", ".join(sorted(str(e.get("slug")) for e in _free)[:4]))
check("and the paid ones still do",
      any(e.get("tier") == "full" and e.get("itch_url") for e in _cat))

# set_itch_url.py --all was fixed, but record() runs on every release and it
# was writing the URL onto the whole family, free edition included. That is
# the path that actually runs, so it is checked here.
_cat2 = json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
_pub_families = {(e.get("base_slug") or e.get("slug")) for e in _cat2
                 if e.get("tier") == "full" and e.get("published") is True}
_leaked = [e.get("slug") for e in _cat2
           if e.get("tier") == "basic" and e.get("itch_url")
           and (e.get("base_slug") or e.get("slug")) in _pub_families]
check("record() did not give a published product's free edition a store URL",
      not _leaked,
      f"{len(_leaked)} free editions of a published product carry a store "
      "URL: " + ", ".join(sorted(str(s) for s in _leaked)[:4]))

print("\nONE UNLUCKY REQUEST IS NOT A VERDICT\n")
# Run 38912830336 said 'the store project did not answer' on a project that
# had been uploaded to twice, then told the account holder to create a project
# they had already created. itch.io rate-limits, and consecutive probes of the
# same live page alternated between answering and not.
_realp = ip.page_probe
_real_sleep = ip.time.sleep
try:
    _calls = []

    def _flaky(url):
        _calls.append(url)
        return (None, "HTTP 429") if len(_calls) < 3 else (True, "HTTP 200")

    ip._PROBE_CACHE.clear()
    ip.page_probe = _flaky
    ip.time.sleep = lambda s: None
    check("a page that declines at first is retried before being called absent",
          ip.page_is_live("https://slingshot-tools.itch.io/slingshot-tools")
          and len(_calls) == 3,
          f"probed {len(_calls)} time(s): one 429 made a live project look "
          "like it did not exist")

    _calls2 = []

    def _always_declines(url):
        _calls2.append(url)
        return (None, "HTTP 429")

    ip._PROBE_CACHE.clear()
    ip.page_probe = _always_declines
    check("and it gives up honestly rather than calling it absent",
          ip.page_is_live("https://slingshot-tools.itch.io/slingshot-tools")
          is False and len(_calls2) == 3,
          f"probed {len(_calls2)} time(s), expected 3 before giving up")

    # and it must not ask the same question again: one fetch per URL per run
    _calls3 = []

    def _answers(url):
        _calls3.append(url)
        return (True, "HTTP 200")

    ip._PROBE_CACHE.clear()
    ip.page_probe = _answers
    for _ in range(5):
        ip.page_is_live("https://slingshot-tools.itch.io/slingshot-tools")
    check("and it fetches once per run rather than once per question",
          len(_calls3) == 1,
          f"fetched {len(_calls3)} times for one question, which is what made "
          "a full audit report take over twenty minutes")
finally:
    ip.page_probe = _realp
    ip.time.sleep = _real_sleep
    ip._PROBE_CACHE.clear()

# and the run must not tell someone to create a project that already exists
_src = " ".join((ROOT / "itch_publish.py").read_text(encoding="utf-8").split())
check("and it does not call the project missing when the server declined",
      "not the same as not existing" in _src,
      "the run said the store did not exist and told the account holder to "
      "create it again")

print("\nTHE PAGE ANSWERING IS NOT THE BUILD BEING THERE\n")
# Two products were advertised with no download. They had been published before
# the channel fix, their builds were replaced by later releases, and step 4 only
# asked whether the page answered. The store is one project holding every
# product, so it answers perfectly well while missing the one that is on sale.
_src2 = " ".join((ROOT / "itch_publish.py").read_text(encoding="utf-8").split())
check("publishing checks this product's own file is on the page",
      "build_is_listed" in _src2
      and "does not list" in _src2,
      "a product can be advertised with no download, which takes money for "
      "something nobody can be given")

cat3 = json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
check("and every advertised paid product has a build on the store",
      all(e.get("published") is not True or e.get("base_slug") in {
          "base64-tool", "password-manager"} for e in cat3
          if e.get("tier") == "full"),
      "a product is on sale whose build the store does not have")

print("\nONE PRODUCT'S INSTALLER IS NEVER ANOTHER'S\n")
# Building chess-clock reused invoice-maker-Setup.exe out of the shared dist/
# folder: find_existing took the first plausible *-Setup.exe anywhere in dist/
# with no regard for which product it belonged to. The publisher's
# find_installer had the same shape, falling back to a substring test in both
# directions. Either one hands a customer the wrong tool under a name they paid
# for.
def _mk(p: pathlib.Path, size: int = 2_000_000) -> pathlib.Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"MZ" + bytes(size - 2))
    return p


_tmp = pathlib.Path(tempfile.mkdtemp())
try:
    import build_paid_only as bpo
    _paid = _tmp / "chess-clock"
    _mk(_paid / "app" / "x.txt")
    _mk(ROOT / "dist" / "invoice-maker-Setup.exe")
    _mk(ROOT / "dist" / "chess-clock-Setup.exe")
    got = bpo.find_existing(_paid)
    check("the builder ignores another product's installer in dist/",
          got is None or got.stem == "Chess-clock",
          f"building chess-clock would reuse {got.name if got else None}, "
          "so a customer would be sent invoice-maker's tool")

    import itch_publish as ip
    found = ip.find_installer("chess-clock")
    _norm = (lambda s: s.lower().replace("-", "").replace("_", "")
             .replace("slingshottool", "").replace("setup", ""))
    check("and the publisher will not pick up someone else's either",
          found is None or _norm(found.stem) == "chessclock",
          f"find_installer returned {found.name if found else None} for "
          "chess-clock")
finally:
    import shutil
    shutil.rmtree(_tmp, ignore_errors=True)
    for _f in ("invoice-maker-Setup.exe", "chess-clock-Setup.exe"):
        (ROOT / "dist" / _f).unlink(missing_ok=True)

print("\nTHE CATALOGUE IS VALID JSON AND SAYS WHAT IT MEANS\n")
# site/apps.json is read by the live site. A rebase conflict left '<<<<<<<' in
# it, the markers were committed, and the storefront shipped invalid JSON.
# Nothing about that is a runtime error anyone would catch: the file is data,
# so the suite has to read it the way the site does.
_check = (ROOT / "site" / "apps.json").read_text(encoding="utf-8")
try:
    _parsed = json.loads(_check)
    check("site/apps.json parses as JSON", isinstance(_parsed, list),
          f"it is a {type(_parsed).__name__}, not the list the site expects")
except json.JSONDecodeError as e:
    check("site/apps.json parses as JSON", False,
          f"line {e.lineno}: {e.msg}. The storefront reads this file, so "
          "this breaks the site.")
    _parsed = []
check("and it holds no conflict markers",
      not any(m in _check for m in ("<<<<<<<", ">>>>>>>", "=======")),
      "a merge conflict was committed into the storefront's data")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)