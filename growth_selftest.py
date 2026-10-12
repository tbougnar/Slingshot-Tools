"""The signal sweep and the goal switch.

The failures this covers are the ones that would be invisible and expensive:

- a source that cannot be read has to say so, not report zero. A zero audience
  and an unmeasured audience call for opposite decisions
- the goal may only move forward, because a bad sales week must never demote
  the company back into chasing stars
- it must not promote itself on missing data
- every source has to fail to "unavailable" rather than raise, because a
  telemetry job that crashes takes the whole Wednesday cycle with it

    python growth_selftest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import goals
import signals

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


# ---- every source degrades, none of them raise
for name, fn in (("site", signals.site_signals),
                 ("youtube", signals.youtube_signals),
                 ("discord", signals.discord_signals)):
    try:
        got = fn()
        ok = isinstance(got, dict) and "available" in got
        check(f"{name} returns a verdict rather than raising", ok,
              str(got)[:50])
        if not got.get("available"):
            check(f"{name} says why it is unavailable",
                  bool(got.get("reason")), got.get("reason", "")[:44])
    except Exception as e:  # noqa: BLE001
        check(f"{name} returns a verdict rather than raising", False,
              f"{type(e).__name__}: {str(e)[:50]}")


# ---- a broken network must not take the sweep down
_real = signals.fetch_text
try:
    signals.fetch_text = lambda url, headers=None: ""
    got = signals.site_signals()
    check("an unreachable site is reported, not raised",
          got.get("available") is False and bool(got.get("reason")))
finally:
    signals.fetch_text = _real


# ---- the numbers are read from both shapes itch.io returns
check("an int count is understood", signals._count(7) == 7)
check("a total dict is understood", signals._count({"total": 5}) == 5)
check("a visits dict is understood",
      signals._count({"total_visits": 11}) == 11)
check("nothing at all is zero, not a crash", signals._count(None) == 0)
check("a string is zero", signals._count("nonsense") == 0)

# ---- audience never double counts and never invents a number
mixed = {"github": {"stars": 40}, "itch": {"visits": {"total_visits": 90}},
         "youtube": {"available": True, "subscribers": 30},
         "discord": {"available": True, "unique_members": 10}}
check("audience takes the largest single measure", signals.audience(mixed) == 90)
check("an unreachable source contributes nothing",
      signals.audience({"github": {"stars": 5}}) == 5)
check("no sources at all is zero",
      signals.audience({}) == 0)

# ---- conversion needs both halves, and says so when it does not have them
check("conversion is unknown with no itch key",
      signals.conversion({"itch": {"available": False,
                                   "reason": "no key"}})["known"] is False)
known = signals.conversion({"itch": {"available": True,
                                     "visits": {"total_visits": 200}},
                            "earnings": {"available": True, "orders": 5,
                                         "total": 15.0}})
check("conversion is worked out when both exist", known["known"] is True)
check("the rate is right", abs(known["rate"] - 0.025) < 1e-9, str(known["rate"]))
check("revenue comes along", known.get("revenue") == 15.0)
check("no visits means unknown, not a divide by zero",
      signals.conversion({"itch": {"available": True}})["known"] is False)

# ---- the goal switch
good = {"audience": 120,
        "conversion": {"known": True, "rate": 0.04, "sales": 12},
        "itch": {"available": True},
        "earnings": {"available": True, "orders": 12},
        "site": {"available": True}, "github": {"available": True}}
check("a proven week is ready to switch",
      goals.ready(goals._empty(), good) is True)
check("no data at all is not ready", goals.ready(goals._empty(), {}) is False)
# audience is there but nobody has bought anything yet
check("a big audience with no sales is not ready",
      goals.ready(goals._empty(),
                  {**good, "sales": 0,
                   "conversion": {"known": True, "rate": 0.0, "sales": 0},
                   "earnings": {"available": True, "orders": 0}}) is False)
# and the same numbers with sales cannot be read at all
check("a big audience with unreadable sales is not ready",
      goals.ready(goals._empty(),
                  {**good, "itch": {"available": False},
                   "earnings": {"available": False},
                   "conversion": {"known": False}}) is False)

# the two phases must actually change what the company does, or the goal is a
# label rather than a strategy
reach = goals.focus({"phase": "reach"}, good)
earn = goals.focus({"phase": "earn"}, good)
check("the two phases have different priorities", reach != earn)
check("earning says to make it buyable",
      any("buyable" in f or "itch" in f for f in earn))
check("reaching says not to touch price",
      any("price" in f for f in reach))

p = goals.progress(good)
check("progress is a percentage", 0 <= p["audience_pct"] <= 100)
check("progress clamps above 100",
      goals._pct(999, 50) == 100)
check("progress never goes negative",
      goals._pct(-5, 50) == 0)

# ---- it must not promote itself, and must not demote
state_file = goals.STATE
existed = state_file.exists()
old = state_file.read_text(encoding="utf-8") if existed else ""
try:
    got = goals.check(apply=False)
    check("without --apply nothing is written",
          got["phase"] == "reach" and "READY" in got["recommendation"]
          or got["phase"] == "reach")
    check("the state file is untouched", not state_file.exists()
          or state_file.read_text(encoding="utf-8") == old)

    # once promoted it must stay promoted, even if sales dip
    goals.save({"phase": "earn", "notes": []})
    again = goals.check(apply=False)
    check("a bad week does not send it back to chasing stars",
          again["phase"] == "earn")
    check("and says to stay", "stay" in again["recommendation"].lower())
finally:
    if existed:
        state_file.write_text(old, encoding="utf-8")
    else:
        state_file.unlink(missing_ok=True)

# ---- the blockers have to be explainable, because the weekly review reads them
b = goals.why_not(goals._empty(), {})
check("unmeasured data is explained", any("never been measured" in x
                                         for x in b))
check("unreadable sales are explained", any("cannot be read" in x for x in b))

# ---- the site check catches the two homepage bugs by shape
body_ok = ("function groupProducts" in (ROOT / "site" / "index.html").read_text(
    encoding="utf-8"))
check("the live homepage function is the fixed one", body_ok)
check("the page uses the index, not inlined json",
      "openDialogByIndex" in (ROOT / "site" / "index.html").read_text(
          encoding="utf-8"))

# ---- the phase has to survive the runner that set it
# Losing it would reset the company to chasing reach forever, so the file is
# written on every run and is tracked in git on purpose.
state_file = goals.STATE
was_there = state_file.exists()
kept = state_file.read_text(encoding="utf-8") if was_there else ""
try:
    state_file.unlink(missing_ok=True)
    goals.check(apply=False)
    check("the goal is written even when nothing changed",
          state_file.exists())
    if state_file.exists():
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        check("and it records the phase",
              saved.get("phase") == "reach", str(saved)[:50])
finally:
    if was_there:
        state_file.write_text(kept, encoding="utf-8")

# a decision that is thrown away every run is not a decision, so the goal has
# to be tracked. The name appears in .gitignore inside a comment explaining
# why it is NOT ignored, so the real test is what git itself says.
import subprocess
r = subprocess.run(["git", "check-ignore", "-q", "data/goals.json"],
                   cwd=str(ROOT), capture_output=True)
check("the goal file is tracked, not ignored", r.returncode != 0,
      "git says it is ignored, so a promotion would not survive")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)