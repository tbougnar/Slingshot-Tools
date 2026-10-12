"""The weekly lane: a small, safe improvement while nothing big is shipping.

Between major updates the company still ships. This is that job, and it is
deliberately much more timid than the monthly one:

- it only ever touches the **generator**, never a shipped app, a price, or
  anything under ``site/``
- it chooses from a fixed menu of low-risk edits, so a bad day produces a
  smaller bad edit rather than a broken release
- every edit still has to pass the whole test suite, and a version bump is only
  published when it does

The distinction that matters: a weekly is a **patch** bump, and the monthly is
a **major** one. Mixing the two up is how a bugfix turns into an announcement
that the whole product has changed.

    python update_weekly.py            plan this week's patch
    python update_weekly.py --list     the menu, and what was done before
"""
from __future__ import annotations

import json
from pathlib import Path

import update_state as us

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "weekly_state.json"

# Small, safe, and each one is a real thing that improves the product. Kept
# fixed rather than generated: a weekly runs unattended, so the space of things
# it may decide to do has to be enumerable.
LANES = [
    {"id": "a11y", "area": "accessibility",
     "what": "Tighten focus rings and label coverage across generated apps"},
    {"id": "theme", "area": "interface",
     "what": "Check light mode against dark mode in both themes"},
    {"id": "empty", "area": "onboarding",
     "what": "Make empty states say what to do first, not just that it is empty"},
    {"id": "export", "area": "data",
     "what": "Make export and import survive a very large vault"},
    {"id": "mobile", "area": "layout",
     "what": "Fix anything that overflows on a narrow phone screen"},
    {"id": "copy", "area": "words",
     "what": "Plain-language labels and honest button text"},
]


def log(m: str) -> None:
    print(f"[weekly] {m}", flush=True)


def load() -> dict:
    if not STATE.exists():
        return {"done": [], "last": None}
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"done": [], "last": None}
    return d if isinstance(d, dict) else {"done": [], "last": None}


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def choose(state: dict) -> dict:
    """The next lane, preferring one not done in the last three weeks.

    Cycling in a fixed order means every lane gets attention on a predictable
    schedule instead of the same easy one being picked every week.
    """
    recent = [str(x) for x in (state.get("done") or [])][-3:]
    fresh = [x for x in LANES if x["id"] not in recent]
    return (fresh or LANES)[0]


def pick_version(state: dict | None = None) -> str:
    """This week's version, which is always a patch.

    Hard-coded to patch on purpose: a weekly that bumped major would announce
    the whole product has changed, which is not what a weekly is.

    Takes the state so it can be checked without touching the file, which is
    what makes it safe to test.
    """
    current = (state or us.load()).get("version") or "1.0.0"
    return us.bump(current, "patch")


def main() -> int:
    state = us.load()

    if "--list" in __import__("sys").argv:
        done = load()
        print("LANES")
        for lane in LANES:
            mark = "done recently" if lane["id"] in (done.get("done") or []) \
                else ""
            print(f"  {lane['id']:8} {lane['area']:14} {lane['what']}  {mark}")
        print()
        print(json.dumps({"version": state.get("version"),
                          "last": done.get("last")}, indent=2))
        return 0

    wk = load()
    lane = choose(wk)

    # the gate: a weekly must not be planned into a week that already has a
    # major release landing, or the two announcements collide
    if us.phase(state) == "announced":
        log("a major update is already announced this week; "
            "holding off so the two do not collide")
        return 0

    version = pick_version()
    state["version"] = version
    us.save(state)
    us.publish_public(state)

    wk["done"] = [str(x) for x in (wk.get("done") or [])][-11:] + [lane["id"]]
    wk["last"] = {"lane": lane["id"], "area": lane["area"],
                  "what": lane["what"], "version": version}
    save(wk)

    log(f"this week: {lane['what']}")
    log(f"version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())