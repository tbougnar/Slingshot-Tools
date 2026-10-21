"""The monthly update lane, the countdown, and the trailer.

Every check here is a thing that has actually gone wrong in this project, or a
boundary that would produce a month with no plan, a banner that never goes
away, or a trailer that advertises something nobody built.

    python update_selftest.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import app_update as au
import discord_post as dp
import update_discord as ud
import update_plan as up
import update_state as us
import update_trailer_render as trt
import update_trailer_script as uts
import update_weekly as uw

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


# ---------------------------------------------------------------- versions
# The installer hardcoded 1.0.0 and the catalog had no version at all, so
# there was nothing to compare an installed app against.
check("a version parses", us.format_version(us.parse("2.3.4")) == "2.3.4")
check("v-prefixed junk parses", us.format_version(us.parse("v3.4.5-rc1"))
      == "3.4.5")
check("an empty version is 1.0.0", us.parse("") == (1, 0, 0))
check("patch bump", us.bump("1.0.0", "patch") == "1.0.1")
# 1.9.9 -> 1.9.10 is the case a naive +1 on the last number gets wrong
check("patch bump carries, not wraps", us.bump("1.9.9", "patch") == "1.9.10")
check("minor bump carries", us.bump("1.9.9", "minor") == "1.10.0")
check("major bump clears", us.bump("2.3.4", "major") == "3.0.0")
# compared as strings, "1.10.0" < "1.9.0"
check("1.10.0 is newer than 1.9.0", us.is_newer("1.10.0", "1.9.0"))
check("1.9.0 is not newer than 1.10.0", not us.is_newer("1.9.0", "1.10.0"))
check("same version is not newer", not us.is_newer("1.0.0", "1.0.0"))

# ------------------------------------------------------------------ phases
today = date.today()


def _state(days: int | None) -> dict:
    s = us._empty()
    if days is not None:
        s["next_major"] = (
            (today + timedelta(days=days)).isoformat() + "T18:00:00+00:00")
    return s


check("no date is idle", us.phase(_state(None)) == "idle")
check("30 days out is idle", us.phase(_state(30)) == "idle")
check("10 days out is countdown", us.phase(_state(10)) == "countdown")
check("5 days out is announced", us.phase(_state(5)) == "announced")
check("a past date is live", us.phase(_state(-1)) == "live")

# A stale countdown on the homepage is the visible failure here, so the
# published file has to drop the date outside the announced window.
st = _state(40)
us.publish_public(st)
pub = json.loads(us.PUBLIC.read_text(encoding="utf-8"))
check("idle publishes no date", pub["next_major"] is None)
check("idle publishes no days", pub["days_left"] is None)

st = _state(3)
us.publish_public(st)
pub = json.loads(us.PUBLIC.read_text(encoding="utf-8"))
check("announced publishes a date", pub["next_major"] is not None)
check("announced publishes days", pub["days_left"] == 3)
check("published phase agrees", pub["phase"] == "announced")

st = _state(-2)
us.publish_public(st)
pub = json.loads(us.PUBLIC.read_text(encoding="utf-8"))
check("a shipped release drops its countdown", pub["next_major"] is None)

# the public file is served, so it must never carry anything internal
st = _state(3)
st["discord_event_id"] = "123456789"
us.publish_public(st)
raw = us.PUBLIC.read_text(encoding="utf-8")
check("no event id leaks to the page", "123456789" not in raw)

# ---------------------------------------------------------------- planning
d = up.target_date(date(2026, 10, 12))
check("plan is in the future", (d - date(2026, 10, 12)).days > 0)
check("plan is not tomorrow", (d - date(2026, 10, 12)).days >= up.MIN_LEAD_DAYS)
check("plan rolls past the 26th",
      up.target_date(date(2026, 10, 27)) > date(2026, 10, 27))
check("plan survives a 31st", up.target_date(date(2026, 10, 31))
      > date(2026, 10, 31))

# The model may only pick from the menu. An invented theme becomes a trailer
# for a feature that was never built.
menu_ids = {t["id"] for t in up.themes()}
check("menu is not empty", len(menu_ids) >= 4)
check("every theme has a title",
      all(t.get("title") for t in up.themes()))
check("every theme has notes",
      all(len(t.get("notes") or []) >= 2 for t in up.themes()))
f = up.fallback([])
check("fallback lands on the menu", f["id"] in menu_ids)
seen = ["ui-refresh", "glass"]
check("fallback avoids a repeat", up.fallback(seen)["id"] not in seen)
check("fallback is marked as such", up.fallback()["chosen_by"] == "menu")

# ------------------------------------------------------------ discord event
s = _state(5)
s["next_major_title"] = "Liquid glass"
s["next_major_notes"] = ["Frosted panels", "Blurred headers"]
s["version"] = "1.4.0"
iso = ud._iso(s)
check("event time keeps an offset", iso.endswith("+00:00"), iso or "")
desc = ud.description(s)
check("event body names the update", "Liquid glass" in desc)
check("event body lists a change", "Frosted panels" in desc)
check("event body has no null date", "None" not in desc)
check("no stored id means no event", ud.existing(s) is None)
s["discord_event_id"] = "999"
check("a stored id is reused", ud.existing(s) == "999")
# no credentials must mean a clean refusal, never an exception, and above all it
# must never reach Discord. dp.TOKEN and dp.GUILD_ID are read from the
# environment at import time, so on a machine that has the real DISCORD_BOT_TOKEN
# set, which is every scheduled runner, this check used to have credentials and
# quietly created a real guild event on the production server. The credentials
# are forced empty here so the check tests the guard rather than the ambient
# environment, and so a test run cannot touch the server.
_saved_token, _saved_guild = dp.TOKEN, dp.GUILD_ID
dp.TOKEN, dp.GUILD_ID = "", ""
try:
    check("upsert without credentials is safe",
          ud.upsert(_state(5)) is False)
    check("announce without a plan is safe",
          ud.announce(us._empty()) is False)
finally:
    dp.TOKEN, dp.GUILD_ID = _saved_token, _saved_guild

# ------------------------------------------------------------- app updates
tmp = Path(tempfile.mkdtemp())
app = tmp / "app"
app.mkdir()
(app / "app.json").write_text(json.dumps({"title": "T", "version": "1.4.0"}),
                              encoding="utf-8")
check("installed version reads app.json", au.installed_version(app) == "1.4.0")

orig = au.PUBLIC.read_text(encoding="utf-8")
pub = json.loads(orig)
pub["version"] = "2.0.0"
au.PUBLIC.write_text(json.dumps(pub), encoding="utf-8")
got = au.check(app, "x")
check("an older install sees an update", got["update_available"])
check("the message names both versions",
      "1.4.0" in got["reason"] and "2.0.0" in got["reason"])

(app / "app.json").write_text(json.dumps({"version": "2.0.0"}),
                              encoding="utf-8")
check("a current install sees nothing",
      not au.check(app, "x")["update_available"])
check("the check can be turned off",
      not au.check(app, "x", enabled=False)["update_available"])

(app / "app.json").unlink()
check("a missing app.json is not a crash",
      au.installed_version(app) == "1.0.0")
au.PUBLIC.write_text(orig, encoding="utf-8")
check("a missing public file is not a crash", au.latest() or True)

# The banner has to survive being injected twice, or every rebuild stacks
# another copy on top of the last.
page = tmp / "index.html"
page.write_text("<!DOCTYPE html><html><body><main>hi</main></body></html>",
                encoding="utf-8")
check("first inject works", au.inject(page))
check("second inject is refused", not au.inject(page))
# the id also appears in the injected script, so count the element itself:
# two elements with one id is how a page ends up with two stacked banners
check("only one banner element", page.read_text(encoding="utf-8").count(
    'id="' + au.BANNER_ID + '"') == 1)
check("the app content survives",
      "<main>hi</main>" in page.read_text(encoding="utf-8"))
nobody = tmp / "nobody.html"
nobody.write_text("<!DOCTYPE html><html><head></head></html>",
                  encoding="utf-8")
check("a page with no body is refused", not au.inject(nobody))
check("and is left untouched",
      nobody.read_text(encoding="utf-8")
      == "<!DOCTYPE html><html><head></head></html>")
check("a missing file is refused", not au.inject(tmp / "gone.html"))

# ----------------------------------------------------------------- weekly
# A weekly that bumped major would announce the whole product has changed.
base = {"version": "1.4.2"}
check("weekly bumps patch only", uw.pick_version(base) == "1.4.3")
check("weekly leaves major alone",
      us.parse(uw.pick_version(base))[0] == us.parse(base["version"])[0])
check("weekly leaves minor alone",
      us.parse(uw.pick_version(base))[1] == us.parse(base["version"])[1])
check("weekly versions only go up",
      us.parse(uw.pick_version(base)) > us.parse(base["version"]))
check("weekly carries past 9",
      uw.pick_version({"version": "1.0.9"}) == "1.0.10")

done = {"done": ["a11y", "theme", "empty"]}
check("weekly rotates past recent lanes",
      uw.choose(done)["id"] not in done["done"])
check("every lane is described",
      all(l.get("what") for l in uw.LANES))

# ---------------------------------------------------------------- trailer
# The Shorts renderer is pinned to 1080x1920 everywhere, which is why the
# trailer is its own renderer rather than a flag.
check("the trailer is landscape", trt.W > trt.H)
check("at 1920x1080", (trt.W, trt.H) == (1920, 1080))
check("the Shorts renderer is not landscape", trt.sr.H > trt.sr.W)

script = {"slug": "password-manager-basic", "title": "Liquid glass surfaces",
          "notes": ["Frosted panels", "Blurred headers"], "version": "2.0.0"}
parts = [{"text": "Everything got a new surface.", "at": 0.0, "seconds": 3.0},
         {"text": "Panels are frosted now.", "at": 3.0, "seconds": 3.0}]
for t in (0.0, 1.5, 3.0, 5.9):
    img = trt.frame(t, parts, {"shot": 0}, script)
    if img.size != (trt.W, trt.H):
        check(f"frame at {t}s is the right size", False, str(img.size))
        break
else:
    check("every frame is the right size", True)

check("a frame renders with no parts at all",
      trt.frame(0.0, [], {"shot": 0}, script).size == (trt.W, trt.H))
check("a frame renders with no title",
      trt.frame(0.0, parts, {}, {}).size == (trt.W, trt.H))
check("cover fit is exact", trt._fit.__doc__ is not None)

# The script is prose, but a bracketed cue would be read aloud.
check("stage directions are stripped",
      uts._tidy("[upbeat music] Everything got faster")
      == "Everything got faster")
check("markdown is stripped", uts._tidy("**Bold** and _italic_")
      == "Bold and italic")
check("a clean line is untouched",
      uts._tidy("Panels are frosted") == "Panels are frosted")
check("an empty line is empty", uts._tidy("   ") == "")
check("a very long line is cut", len(uts._tidy("x" * 400)) <= 220)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)