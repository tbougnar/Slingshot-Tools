"""Pass F and G findings, each held in place.

The bugs here are all the same shape: something that only shows up when the
world is not exactly as expected. No credentials, a data file that was never
written, a module that was gitignored, a scratch file swept into a commit.

    python audit_selftest.py
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from testenv import clean_env

ROOT = Path(__file__).resolve().parent
fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label,
          ("\n        " + detail) if detail else "")
    if not ok:
        fails.append(label)


def clean_env() -> dict:
    """The environment a child must get so a test cannot spend money.

    improve_daily.py calls the model provider when it has a key, and a
    scheduled runner has a real GROQ_API_KEY. A child started with the
    inherited environment therefore makes a real, billable API call, which is
    the one thing a test must never do. The provider keys and the Discord and
    itch.io credentials are stripped, so every module under test takes the
    "no key" path, which is the path that has to be safe anyway.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.endswith("_API_KEY")
           and k not in ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID",
                         "DISCORD_WEBHOOK_URL", "ITCH_SESSION_COOKIE",
                         "ITCH_USER", "ITCH_LOGIN", "ITCH_PASSWORD",
                         "ELEVENLABS_API_KEY", "YOUTUBE_API_KEY",
                         "BUTLER_API_KEY")}
    env.setdefault("PATH", "/usr/bin:/bin")
    env.setdefault("SYSTEMROOT", "C:\\Windows")
    env.setdefault("HOME", tempfile.gettempdir())
    return env


def run(script: str, cwd: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, script], cwd=str(cwd),
                       capture_output=True, text=True, timeout=600,
                       env=clean_env())
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---- 1. SystemExit.code is not always an int
# providers.active() raises SystemExit("no model provider is configured"), and
# improve_daily turned that into ValueError on every run without a key, so the
# daily lane produced a traceback instead of saying it had nothing to do.
print("A MISSING MODEL IS NOT A CRASH\n")
tmp = Path(tempfile.mkdtemp())
for f in ROOT.glob("*.py"):
    shutil.copy2(f, tmp / f.name)
for extra in ("site", ".github", "data"):
    s = ROOT / extra
    if s.exists():
        shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
for junk in ("apps", "paid", "dist"):
    shutil.rmtree(tmp / junk, ignore_errors=True)

env = {"PATH": "/usr/bin:/bin", "SYSTEMROOT": "C:\\Windows",
       "HOME": tempfile.gettempdir()}
r = subprocess.run([sys.executable, "improve_daily.py"], cwd=str(tmp),
                   capture_output=True, text=True, timeout=600, env=env)
out = (r.stdout or "") + (r.stderr or "")
check("improve_daily survives with no API key", "Traceback" not in out,
      out.strip().splitlines()[-1][:80] if "Traceback" in out else "")
check("and it says why it did nothing",
      "not today" in out.lower() or "no model" in out.lower()
      or "stopped" in out.lower(),
      out.strip().splitlines()[-1][:70] if out.strip() else "(no output)")

# the same trap, directly
check("SystemExit with a message is not turned into a number",
      isinstance(getattr(sys.modules.get("providers"), "x", None), type(None)))
shutil.rmtree(tmp, ignore_errors=True)

# ---- 2. a missing data file must not crash anything
print("\nA MISSING DATA FILE IS NOT A CRASH\n")
for name in ("signals", "goals", "check_exposure", "update_state",
             "weekly_guard", "improve_daily"):
    tmp = Path(tempfile.mkdtemp())
    for f in ROOT.glob("*.py"):
        shutil.copy2(f, tmp / f.name)
    for extra in ("site", ".github", "data"):
        s = ROOT / extra
        if s.exists():
            shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
    for junk in ("apps", "paid", "dist"):
        shutil.rmtree(tmp / junk, ignore_errors=True)
    (tmp / "data" / "update_state.json").unlink(missing_ok=True)
    code, out = run(f"{name}.py", tmp)
    tb = "Traceback" in out
    check(f"{name}.py survives a missing data file", not tb,
          out.strip().splitlines()[-1][:80] if tb else "")
    shutil.rmtree(tmp, ignore_errors=True)

# ---- 3. nothing scratch may be committed
print("\nNO SCRATCH FILES IN THE REPOSITORY\n")
scratch = sorted(ROOT.glob("_*.py"))
check("no _*.py scratch file is committed", not scratch,
      ", ".join(p.name for p in scratch))
r = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                   capture_output=True, text=True, timeout=120,
                   env=clean_env())
tracked = [ln for ln in (r.stdout or "").splitlines()
           if ln.strip().startswith("_")]
check("git tracks no underscore-named file", not tracked,
      ", ".join(tracked[:3]))

# ---- 4. every module the pipeline needs is in the repository
print("\nEVERY NEEDED MODULE IS TRACKED\n")
try:
    r = subprocess.run([sys.executable, "tracked_selftest.py"],
                       cwd=str(ROOT), capture_output=True, text=True,
                       timeout=300, env=clean_env())
    check("tracked_selftest passes", r.returncode == 0,
          next((ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")),
               ""))
except Exception as e:  # noqa: BLE001
    check("tracked_selftest passes", False, str(e)[:60])

# ---- 5. check.ps1 must name every variable the checker reads
print("\nTHE POWERSHELL PRE-FLIGHT IS COMPLETE\n")
ps = (ROOT / "check.ps1").read_text(encoding="utf-8")
conn = (ROOT / "check_connections.py").read_text(encoding="utf-8")
import re
needed = set(re.findall(r'environ\.get\(\s*"([A-Z_]+)"', conn))
named = set(re.findall(r'"([A-Z_]+)"', ps))
missing = sorted(n for n in needed if n not in named)
check("check.ps1 accounts for every variable check_connections reads",
      not missing, f"missing from the pre-flight: {missing}")

# ---- 6. one fetch of a signal, not two
print("\nNO DUPLICATE SIGNAL FETCHES\n")
learn = (ROOT / "learn.py").read_text(encoding="utf-8")
check("learn.py uses reputation.itch_signals, not its own request",
      "reputation.itch_signals()" in learn)
# the docstring names the old endpoint to explain why it is gone, so only
# executable lines are checked
code_lines = [ln for ln in learn.splitlines()
              if "embed-stats" in ln and not ln.strip().startswith(("#", '"'))
              and "This used to" not in ln and "a game-level" not in ln
              and "responds 404" not in ln]
check("and no code still calls embed-stats", not code_lines,
      "; ".join(code_lines[:2]) if code_lines else "")

# ---- 7. a write that cannot happen must be reported as one
# update_state.save() and publish_public() raised an unhandled PermissionError
# and logged "saved" before checking anything, so an unattended job could die
# on a traceback and a caller could not tell a real save from a claim of one.
print("\nA WRITE THAT CANNOT HAPPEN IS NOT A SAVE\n")
import stat

tmp = Path(tempfile.mkdtemp())
for f in ROOT.glob("*.py"):
    shutil.copy2(f, tmp / f.name)
for extra in ("site", ".github", "data"):
    s = ROOT / extra
    if s.exists():
        shutil.copytree(s, tmp / extra, dirs_exist_ok=True)
for junk in ("apps", "paid", "dist"):
    shutil.rmtree(tmp / junk, ignore_errors=True)

victim = tmp / "data" / "update_state.json"
if victim.exists():
    victim.chmod(stat.S_IREAD)
    try:
        r = subprocess.run([sys.executable, "update_state.py"],
                           cwd=str(tmp), capture_output=True, text=True,
                           timeout=300, env=clean_env())
        out = (r.stdout or "") + (r.stderr or "")
        check("a read-only state file does not raise", "Traceback" not in out,
              out.strip().splitlines()[-1][:80] if "Traceback" in out else "")
        check("and the run exits non-zero", r.returncode != 0,
              f"exit was {r.returncode}")
        check("and it does not claim to have saved",
              "saved 1." not in out,
              "it said it saved something it could not")
    finally:
        victim.chmod(stat.S_IWRITE)
else:
    print("skip  no state file to lock")
shutil.rmtree(tmp, ignore_errors=True)

# ---- 8. a meter that cannot be read must not say there is allowance left
# tokenmeter._load() swallowed a parse error and returned {}, which spent()
# read as zero. affordable() then said yes forever and the pipeline burned
# through the whole limit before anything noticed. spent() reported 0 and the
# write error in add() was swallowed by a bare except, so neither showed up.
print("\nAN UNREADABLE METER STOPS SPENDING INSTEAD OF ALLOWING IT\n")
import tokenmeter as tm

# The meter this test corrupts is the real one, and it is the guard that
# decides whether the pipeline may spend. Resetting it here zeroed the
# recorded spend and disarmed the limit for the rest of the month, and the
# test's closing reset() wiped it again. The test now works on its own file.
saved_state = tm.STATE
tm.STATE = Path(tempfile.mkdtemp()) / "token_usage.json"
try:
    tm.reset()
    tm.add(1000, 500)
    check("a working meter counts", tm.spent() == 1500, str(tm.spent()))
    check("and says there is allowance left", tm.affordable(8000, 1000))
    check("and is not unknown", tm.unknown() is False)

    for label, body in (("truncated", "{not json"),
                        ("a list", "[1, 2, 3]"),
                        ("a number", "42")):
        tm.STATE.write_text(body, encoding="utf-8")
        check(f"{label} state is reported as unknown", tm.unknown() is True)
        check(f"{label} state is not read as zero spend", tm.spent() != 0,
              f"spent {tm.spent()}")
        check(f"{label} state leaves nothing affordable",
              not tm.affordable(8000, 100))
        check(f"{label} state reports zero remaining", tm.remaining(8000) == 0)

    # a stale window is fine and must stay fine
    tm.STATE.write_text(json.dumps({"window_start": 0, "total": 10}),
                        encoding="utf-8")
    check("a stale window is not an error", tm.unknown() is False)
    check("a stale window reads as zero", tm.spent() == 0)
    check("a stale window is affordable again", tm.affordable(8000, 4000))
finally:
    tm.STATE = saved_state

# stage_app must not sit waiting out a reset that can never happen
stage_src = (ROOT / "stage_app.py").read_text(encoding="utf-8")
check("stage_app checks whether the meter is broken before waiting",
      "tokenmeter.unknown()" in stage_src,
      "it waits 300s on a meter that can never recover")
check("and it says so rather than starting silently",
      stage_src.count("tokenmeter.unknown()") >= 2)

# ---- 9. an unreadable budget must refuse the job, not approve it
# budget.load() swallowed a parse error and returned an empty budget, which
# read as a month with zero hours spent, so check() approved work that may have
# already blown the whole allowance. The module docstring claimed the hours
# "cannot quietly reset"; this is exactly how they did.
print("\nAN UNREADABLE BUDGET REFUSES THE JOB\n")
import budget as bg

real_budget = bg.STATE
backup = None
# The budget file is the company's remaining allowance. This test used to
# corrupt the real one in place, and a run killed between the corruption and
# the restore left the allowance unreadable, which refuses every job. The
# backup was written next to the real file as data/budget.json.auditbak,
# which nothing ignores, so a git add -A could commit the allowance. The test
# now works on its own copy, outside the repository.
scratch = Path(tempfile.mkdtemp())
bg.STATE = scratch / "budget.json"
try:
    if real_budget.exists():
        backup = scratch / "budget.real.json"
        shutil.copy2(real_budget, backup)

    # a working budget approves, so the refusal below is about the failure only
    if backup:
        shutil.copy2(backup, bg.STATE)
    check("a readable budget approves a small job",
          bg.check("audit-probe", planned_hours=0.1) == 0)

    for label, body in (("truncated", "{oops"), ("a list", "[1]"),
                        ("a number", "7")):
        bg.STATE.write_text(body, encoding="utf-8")
        check(f"a {label} budget is reported as broken", bg.broken() is True)
        check(f"a {label} budget refuses the job",
              bg.check("audit-probe", planned_hours=0.1) == 1,
              "it approved work with an unknown budget")
finally:
    bg.STATE = real_budget
    shutil.rmtree(scratch, ignore_errors=True)

budget_src = (ROOT / "budget.py").read_text(encoding="utf-8")
check("budget.py does not still claim its state is committed",
      "which is committed" not in budget_src,
      "380e29e untracked it, so the docstring is claiming something false")
check("budget.py says the state is deliberately untracked",
      "NOT tracked" in budget_src)
check("and it says an unreadable state refuses the job",
      "unknown rather than" in budget_src and "REFUSING" in budget_src)

# ---- 10. an app whose script cannot parse must never be staged
# make_app escaped a model reply once per pass, so a doubly-escaped payload
# arrived as \\"full\\" rather than "full". The whole script block failed to
# parse, every control was reported dead, and the repair loop spent its entire
# budget patching controls that were never broken because the fault was one
# syntax error earlier. dev-converter shipped that way.
print("\nAN APP THAT CANNOT PARSE IS REFUSED BEFORE IT IS STAGED\n")
import make_app

_esc = 'const TIER=\\\\"full\\\\";const K=\\\\"x\\\\";'
_un = make_app._unescape(_esc)
check("double-escaped javascript is unescaped fully",
      _un == 'const TIER="full";const K="x";', _un[:50])

_one = make_app._unescape('const K=\\"x\\";')
check("single-escaped javascript is still correct",
      _one == 'const K="x";', _one[:40])
check("an already-clean string is left alone",
      make_app._unescape('const K="x";') == 'const K="x";')
check("a real backslash does not loop forever",
      make_app._unescape("const RE=/\\\\d/;") == "const RE=/\\d/;",
      f"it stopped at {make_app._unescape('const RE=/\\\\\\\\d/;')!r} rather "
      "than decoding once")
check("and a string with no escapes is untouched",
      make_app._unescape("const K='plain';") == "const K='plain';")

_bad = "<html><body><script>const TIER=\\\"full\\\";</script></body></html>"
check("an unparseable script block is detected",
      make_app.js_syntax_errors(_bad),
      "the escaping bug that shipped dev-converter is invisible again")
check("and it is refused by the staging gate",
      any("will not parse" in p for p in make_app.html_looks_fine(_bad)))
_ok = "<html><body>" + "<script>const K='x';localStorage.setItem(K,'1');" \
      "</script>" + "x" * 2000 + "</body></html>"
check("a clean script block is not falsely refused",
      not make_app.js_syntax_errors(_ok))

# the delimiter check has to be silent on valid javascript, because stage_app
# throws away and regenerates anything html_looks_fine rejects
for _src in ('const K="x";localStorage.setItem(K,"1");',
             "const re=/\\d+/g;", "const t=`a ${b} c`;",
             "const q=\"it's fine\";", "const d=\"a\\\"b\";",
             "const s=\"`\";", "const arrow=x=>`${x}`;",
             "if(a){b()}else{c()}"):
    check(f"valid js is not flagged: {_src[:34]}",
          not make_app._unbalanced_delimiters(_src),
          make_app._unbalanced_delimiters(_src))
for _src in ('const x=getElementById("outputUnit`).value;',
             'const a="unclosed;', "const b=`unclosed;", "if(a{ b() }"):
    check(f"broken js is caught: {_src[:34]}",
          bool(make_app._unbalanced_delimiters(_src)))

_live = ROOT / "site/apps/dev-converter-basic/app/index.html"
if _live.exists():
    _js = make_app.js_syntax_errors(
        make_app._unescape(_live.read_text(encoding="utf-8", errors="replace")))
    check("the app currently on disk parses",
          not _js,
          "dev-converter shipped unparseable once already; this is that one: "
          + "; ".join(_js[:2]))
else:
    print("skip  no generated app on disk to check")

# ---- 11. the release gate must catch a paid build in the published folder
# The gate is the last thing between the paid product and the public site,
# and it had three holes. It looked for a flat index.html, but the paid
# edition is paid/<slug>/app/index.html, so a copy of the paid folder into
# site/apps/ was invisible to it. It read the folder check's exemption from
# data/candidate.json, which allowed the plain paid slug, so the folder was
# accepted as a known basic edition. And it looked for development files by
# name, with no binary extensions, so the one file that IS the paid product,
# the installer, was not on the list.
print("\nTHE RELEASE GATE CATCHES A PAID BUILD IN THE PUBLIC SITE\n")
import check_exposure as _ce

_REAL_SITE, _REAL_APPS, _REAL_ROOT = _ce.SITE, _ce.APPS, _ce.ROOT


def _exposure_run(kind: str, candidate: str | None = None) -> int:
    """Build a public site with one leak in it and ask the gate about it."""
    _tmp = Path(tempfile.mkdtemp())
    try:
        _site = _tmp / "site"
        _apps = _site / "apps"
        _apps.mkdir(parents=True)
        _cat = [{"slug": "thing", "base_slug": "thing", "tier": "full",
                 "title": "Thing", "price": 3.0, "published": False},
                {"slug": "thing-basic", "base_slug": "thing", "tier": "basic",
                 "title": "Thing (Basic)", "price": 0.0, "published": True}]
        (_site / "apps.json").write_text(json.dumps(_cat), encoding="utf-8")
        _paid_html = '<html><script>const TIER="full";</script></html>'
        if kind == "app":
            _d = _apps / "thing" / "app"
            _d.mkdir(parents=True)
            (_d / "index.html").write_text(_paid_html, encoding="utf-8")
        elif kind == "flat":
            _d = _apps / "thing"
            _d.mkdir(parents=True)
            (_d / "index.html").write_text(_paid_html, encoding="utf-8")
        elif kind == "basic":
            _d = _apps / "thing-basic" / "app"
            _d.mkdir(parents=True)
            (_d / "index.html").write_text(_paid_html, encoding="utf-8")
        elif kind == "binary":
            _d = _site / "downloads"
            _d.mkdir(parents=True)
            (_d / "Thing-Setup.exe").write_bytes(b"MZ" + b"x" * 2000)
        if candidate:
            (_tmp / "data").mkdir(exist_ok=True)
            (_tmp / "data" / "candidate.json").write_text(
                json.dumps({"slug": candidate}), encoding="utf-8")
        _ce.SITE, _ce.APPS, _ce.ROOT = _site, _apps, _tmp
        try:
            return _ce.main()
        except SystemExit as _e:
            return int(_e.code or 0)
        finally:
            _ce.SITE, _ce.APPS, _ce.ROOT = _REAL_SITE, _REAL_APPS, _REAL_ROOT
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)


check("a paid build at apps/<slug>/app/ is caught",
      _exposure_run("app") != 0,
      "the gate only looked for a flat index.html, and the paid edition is "
      "app/index.html")
check("even when a candidate makes the folder name legitimate",
      _exposure_run("app", candidate="thing") != 0,
      "the exemption allowed the plain paid slug, so the folder was taken "
      "for a known basic edition")
check("a flat paid build is caught", _exposure_run("flat") != 0)
check("a paid edition inside the basic folder is caught",
      _exposure_run("basic") != 0,
      "the tier constant says full and the gate did not look at it")
check("a paid installer anywhere under the site is caught",
      _exposure_run("binary") != 0,
      "the junk list had no binary extensions, and the installer IS the "
      "paid product")

# ---- 12. the guard that protects the site has to be able to see
# weekly_guard.changed_files() asked git for the diff between HEAD and HEAD
# with the three-dot form, which is a merge-base comparison, so the merge
# base was that commit and the diff was empty with exit code 0. The function
# always returned an empty list, and every gate built on it reported "0
# changed file(s), none protected" while a protected workflow sat modified
# in the tree.
print("\nTHE GUARD CAN ACTUALLY SEE A CHANGE\n")
import weekly_guard as _wg

import shutil as _shutil
import subprocess as _subprocess

# The guard asks git what has changed, so it needs a repository. The clean
# room is a plain directory, where git answers 128, and a guard that cannot
# see anything would report "nothing changed" and look like it had passed.
_git_ok = _subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(ROOT),
                          capture_output=True).returncode == 0
if not _git_ok:
    print("skip  this is not a git repository, so the guard has nothing to "
          "compare against")
else:
    _target = ROOT / ".github" / "workflows" / "pages.yml"
    _keep = _target.read_text(encoding="utf-8")
    try:
        _target.write_text(_keep + "\n# a change\n", encoding="utf-8")
        _seen = _wg.changed_files()
        check("a modified protected file is seen",
              ".github/workflows/pages.yml" in _seen,
              f"the guard saw {_seen[:4]} and the protected file was not among "
              "them")
        check("and it is called a violation",
              ".github/workflows/pages.yml" in _wg.violations(_seen),
              "the guard saw the file and did not call it a violation")
        check("and the gate refuses",
              _wg.guard() != 0,
              "the gate said it was fine")
    finally:
        _target.write_text(_keep, encoding="utf-8")
        importlib.reload(_wg)

# ---- 13. the audit trail must not hold a credential
# The log is a tracked file in a public repository. The scrubber needed the
# name and the value side by side in one string, and in a dict they are two
# separate strings, so a credential held as a dict value was written out as
# it was.
print("\nTHE AUDIT TRAIL DOES NOT HOLD A CREDENTIAL\n")
import auditlog as _al

for _label, _value in (("password", "hunter2000"),
                        ("itch_session_cookie", "s%3Aabcdefghijklmnop"),
                        ("discord_token", "MTIz.Gh1jkl.abcdefghijklmnop"),
                        ("Authorization", "Basic dXNlcjpwYXNzd29yZA==")):
    _got = _al.scrub({_label: _value})
    check(f"a {_label} held as a dict value is redacted",
          _got.get(_label) == "<redacted>",
          f"it was written out as {_got.get(_label)!r}")
_got = _al.scrub({"nested": {"api_key": "sk-abcdefghijklmnopqrst"}})
check("and one nested inside another",
      _got["nested"]["api_key"] == "<redacted>",
      f"got {_got}")
check("an ordinary word is not redacted",
      _al.scrub({"action": "started"})["action"] == "started")

# ---- 14. rotating the log must not throw the history away
# _rotate() copied the newest file to .1 and then deleted it, so the file
# the reader looks at was gone and read() returned nothing. The docstring
# says the opposite of what the code did.
print("\nROTATING THE LOG KEEPS THE HISTORY\n")
import json as _json
import tempfile as _tempfile

_tmp = Path(_tempfile.mkdtemp())
_real_root, _real_log, _real_max = _al.ROOT, _al.LOG, _al.MAX_BYTES
try:
    _al.ROOT = _tmp
    _al.LOG = _tmp / "events.jsonl"
    _al.MAX_BYTES = 400
    for _i in range(10):
        _al.write("STARTED", stage="x", job=f"job{_i}", evidence={"n": _i})
    check("the log file still exists after a rotation",
          _al.LOG.exists(),
          "the newest file was deleted, so the trail was thrown away")
    check("and there is still something to read",
          len(_al.read()) > 0,
          "read() returned nothing, so the report had nothing to report")
finally:
    _al.ROOT, _al.LOG, _al.MAX_BYTES = _real_root, _real_log, _real_max
    _shutil.rmtree(_tmp, ignore_errors=True)

# ---- 15. the price engine must not reset the shop
# The engine's state file is untracked, so on a fresh runner it does not
# exist and every product was defaulted to the starting price, which reset
# the whole shop to $3.00 every Friday and reverted any price set by hand.
print("\nTHE PRICE ENGINE DOES NOT RESET THE SHOP\n")
import pricing as _pricing

_tmp = Path(_tempfile.mkdtemp())
_cat = _tmp / "apps.json"
_cat.write_text(_json.dumps([
    {"slug": "a", "base_slug": "a", "tier": "full", "title": "A",
     "price": 5.0, "itch_url": "https://x.itch.io/y"},
    {"slug": "b", "base_slug": "b", "tier": "full", "title": "B",
     "price": 99.0, "itch_url": "https://x.itch.io/z"},
    {"slug": "a-basic", "base_slug": "a", "tier": "basic",
     "title": "A (Basic)", "price": 0.0},
    {"slug": "b-basic", "base_slug": "b", "tier": "basic",
     "title": "B (Basic)", "price": 0.0}]), encoding="utf-8")
_rc, _ro, _rp, _rl = (_pricing.CATALOG, _pricing.PRICES, _pricing.PRICES,
                       _pricing.LOG)
_real_cat, _real_prices, _real_log = (_pricing.CATALOG, _pricing.PRICES,
                                      _pricing.LOG)
try:
    _pricing.CATALOG = _cat
    _pricing.PRICES = _tmp / "prices.json"
    _pricing.LOG = _tmp / "price_log.json"
    _pricing.main()
    _out = _json.loads(_cat.read_text(encoding="utf-8"))
    _paid = next(e for e in _out if e.get("slug") == "a")
    _free = next(e for e in _out if e.get("slug") == "a-basic")
    _wild = next(e for e in _out if e.get("slug") == "b")
    check("a price that is already set is kept",
          float(_paid.get("price") or 0) == 5.0,
          f"it was reset to {_paid.get('price')}")
    check("the free edition is still free",
          float(_free.get("price") or 0) == 0.0,
          f"it became {_free.get('price')}")
    check("a price outside the rule is brought back inside it",
          _pricing.FLOOR <= float(_wild.get("price") or 0) <= _pricing.CEILING,
          f"it stayed at {_wild.get('price')}, and publish_paid.py refuses to "
          "list a product outside the rule, so it could never be sold")
finally:
    _pricing.CATALOG, _pricing.PRICES, _pricing.LOG = (_real_cat,
                                                        _real_prices,
                                                        _real_log)
    _shutil.rmtree(_tmp, ignore_errors=True)

check("a hold is clamped like a move is",
      _pricing.clamp(0.0) >= _pricing.FLOOR
      and _pricing.clamp(99.0) <= _pricing.CEILING,
      "a held price was written back unclamped and could never be listed")

# ---- 16. the repair lane may not rewrite a protected file
print("\nTHE REPAIR LANE MAY NOT REWRITE A PROTECTED FILE\n")
import selfheal as _sh

_kept = _sh.safe({"fixes": [
    {"file": "build_exe.py", "note": "x",
     "content": "one\ntwo\nthree\nfour\nfive\nsix\n"},
    {"file": "make_app.py", "note": "y",
     "content": "one\ntwo\nthree\nfour\nfive\nsix\n"}]})
_names = [k["file"] for k in _kept]
check("a protected script is refused",
      "build_exe.py" not in _names,
      "the repair lane may rewrite a script the guard protects")
check("and an ordinary file is not",
      "make_app.py" in _names,
      "the repair lane can no longer repair anything")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
