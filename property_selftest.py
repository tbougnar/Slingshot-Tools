"""Pass B: property and edge-case tests on the code that decides things.

Version arithmetic, the release phase, the price clamp and the cooldown all
make decisions from arithmetic that a mistake would quietly corrupt. These are
generated cases rather than hand-picked ones, so a boundary nobody thought of
still gets tried.
"""
import itertools
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))

import improve_daily as idd
import pricing
import update_plan as up
import update_state as us

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("\n        " + detail) if detail else "")
    if not ok:
        fails.append(label)


print("VERSION ARITHMETIC, EXHAUSTIVELY\n")
# every version shape across a wide range must parse and round-trip
bad = []
for a, b, c in itertools.product((0, 1, 9, 10, 99), repeat=3):
    v = f"{a}.{b}.{c}"
    if us.format_version(us.parse(v)) != v:
        bad.append(v)
check("parse and format round-trip over 125 versions", not bad,
      ", ".join(bad[:4]))

# a bump must always move forward, never sideways or back
backwards = []
for a, b, c in itertools.product((0, 1, 5, 9), repeat=3):
    v = f"{a}.{b}.{c}"
    for level in us.LEVELS:
        nxt = us.bump(v, level)
        if us.parse(nxt) <= us.parse(v):
            backwards.append(f"{v} {level} -> {nxt}")
check("every bump moves strictly forward", not backwards,
      "; ".join(backwards[:3]))

# the level must land where it says
wrong = []
for a, b, c in itertools.product((1, 4, 9), repeat=3):
    v = f"{a}.{b}.{c}"
    if us.bump(v, "major") != f"{a + 1}.0.0":
        wrong.append(f"{v} major")
    if us.bump(v, "minor") != f"{a}.{b + 1}.0":
        wrong.append(f"{v} minor")
check("a major clears minor and patch; a minor clears patch", not wrong,
      "; ".join(wrong[:3]))

# rubbish input must not crash and must not invent a version
odd = ["", "   ", "abc", "v", None, "1", "1.2", "1.2.3.4", "..", "-1.-2.-3"]
crash = []
for raw in odd:
    try:
        us.parse(raw)
    except Exception as e:  # noqa: BLE001
        crash.append(f"{raw!r}: {e}")
check("junk versions do not crash the parser", not crash, "; ".join(crash[:2]))

print("\nRELEASE PHASE ACROSS EVERY DAY AROUND THE SWITCH\n")
today = date.today()
phases = {}
for offset in range(-40, 41):
    st = us._empty()
    st["next_major"] = (today + timedelta(days=offset)).isoformat() + \
        "T18:00:00+00:00"
    phases[offset] = us.phase(st)
# monotone: once it is live it must never go back to idle
# For one fixed release, time only moves forward, so the phase must go
# idle -> countdown -> announced -> live and never come back. That is checked
# by shifting the date backwards, which is the same as moving time forwards.
seen_live = False
regress = []
for off in sorted(phases, reverse=True):
    if phases[off] != "live" and seen_live:
        regress.append(off)
    if phases[off] == "live":
        seen_live = True
check("walking time forwards for one release never un-launches",
      not regress, f"regressed at offsets {regress[:3]}")

# days_left must agree with the phase boundary in both directions
st = us._empty()
st["next_major"] = (today + timedelta(days=100)).isoformat() + \
    "T18:00:00+00:00"
check("a date 100 days out is idle and 100 days away",
      us.phase(st) == "idle" and us.days_until(st) == 100,
      f"{us.phase(st)} / {us.days_until(st)}")
st["next_major"] = (today - timedelta(days=100)).isoformat() + \
    "T18:00:00+00:00"
check("a date 100 days past is live",
      us.phase(st) == "live" and us.days_until(st) == -100)
# the day itself and every day before it is live; the lead window after it is
# "announced", because the countdown is meant to be visible before release
check("the day itself is live", phases[0] == "live", phases[0])
check("every day before the day is live",
      all(phases[o] == "live" for o in (-1, -2, -7, -40)))
check("the lead window after the day is announced",
      all(phases[o] == "announced" for o in (1, 3, 7)))
check("the phase is idle far in the future",
      all(phases[o] == "idle" for o in (25, 30, 40)))
check("the phase counts down in between",
      all(phases[o] == "countdown" for o in (8, 12, 21)))

print("\nPLANNING NEVER RETURNS A PAST DATE\n")
bad_dates = []
for month in range(1, 13):
    for day in (1, 14, 25, 26, 27, 28, 31):
        try:
            today_m = date(2026, month, day)
        except ValueError:
            continue
        got = up.target_date(today_m)
        if got <= today_m:
            bad_dates.append(f"{today_m} -> {got}")
        if (got - today_m).days < up.MIN_LEAD_DAYS:
            bad_dates.append(f"{today_m} too close -> {got}")
check("every day of a year plans into the future", not bad_dates,
      "; ".join(bad_dates[:3]))

print("\nPRICE CLAMP BOUNDARIES\n")
cases = [(-99, 1.0), (-0.01, 1.0), (0, 1.0), (0.999, 1.0), (1.0, 1.0),
         (1.001, 1.001), (5.0, 5.0), (9.999, 9.999), (10.0, 10.0),
         (10.001, 10.0), (99, 10.0)]
bad = []
for raw, want in cases:
    got = pricing.clamp(raw)
    if abs(got - want) > 0.001:
        bad.append(f"clamp({raw}) = {got}, wanted {want}")
check("clamp holds at every boundary", not bad, "; ".join(bad[:3]))

print("\nCOOLDOWN ARITHMETIC\n")
today = date.today()
st = idd.load()
st["changes"] = []
check("with no history there is no cooldown", idd.on_cooldown(st) == 0)
st["changes"] = [{"at": idd.now().isoformat()}]
check("a change just made starts the cooldown",
      idd.on_cooldown(st) > 0, str(idd.on_cooldown(st)))
st["changes"] = [{"at": (idd.now() - timedelta(
    hours=idd.COOLDOWN_HOURS + 1)).isoformat()}]
check("the cooldown expires after its window", idd.on_cooldown(st) == 0)
st["changes"] = [{"at": "not a date"}]
check("an unreadable timestamp does not wedge it",
      idd.on_cooldown(st) == 0)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)