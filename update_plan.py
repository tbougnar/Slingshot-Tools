"""Decide what the next big update is, and put a date on it.

The brief was "every month the AI makes a major update: a UI upgrade, liquid
glass, AI integration, whatever". The interesting part is not the model call,
it is what happens when the model is unavailable, because a schedule that only
works when the API is up is a schedule that quietly stops.

So the plan is written in two halves:

- ``themes()`` is a fixed, hand-written menu of things that can be built with
  the machinery this repo actually has. It is not a placeholder; it is the
  safety net, and it is what runs when the model cannot be reached.
- ``ask()`` picks one of those themes and writes a title and three notes.

The model is only ever allowed to choose from the menu. It cannot invent a
feature, because an invented feature is one nobody can build or test, and the
trailer would then advertise something that never ships.

    python update_plan.py            plan the next major update
    python update_plan.py --show     print the current plan
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import providers
import update_state as us

ROOT = Path(__file__).resolve().parent

# A major update goes out at the end of the month, and is announced a week
# before, so there is always time to build the trailer and warn people.
TARGET_DAY = 26
# If the end of the month is already inside the announcement window, aim for
# the same day next month rather than shipping tomorrow.
MIN_LEAD_DAYS = 10


def log(m: str) -> None:
    print(f"[plan] {m}", flush=True)


def themes() -> list[dict]:
    """The monthly menu.

    Each entry is something the existing pipeline can genuinely deliver: a
    change to the generator, the QA stack, or the packaging. None of them need
    a network call in the app, a framework, or a payment change, because those
    are exactly the things that would break the one-file rule and the exposure
    checks.
    """
    return [
        {"id": "ui-refresh",
         "title": "A whole new look",
         "notes": ["New spacing and type scale across every app",
                   "Rounder cards, softer shadows, clearer hierarchy",
                   "Light mode rebuilt to match the dark one"]},
        {"id": "glass",
         "title": "Liquid glass surfaces",
         "notes": ["Frosted, translucent panels over the app background",
                   "Backdrop blur on headers and dialogs",
                   "Kept to inline CSS so it stays one file"]},
        {"id": "accessibility",
         "title": "Accessibility everywhere",
         "notes": ["Every control reachable and visible by keyboard",
                   "Real focus rings and labels on every input",
                   "Text contrast checked in both themes"]},
        {"id": "speed",
         "title": "Faster and lighter",
         "notes": ["Smaller bundle per app, faster first paint",
                   "Rendering work moved off the main thread",
                   "Export and import on large vaults stays instant"]},
        {"id": "data",
         "title": "Own your data properly",
         "notes": ["Versioned export files that import cleanly later",
                   "Import preview before anything is written",
                   "A visible, plain-language data summary"]},
        {"id": "onboarding",
         "title": "A better first five minutes",
         "notes": ["An empty state that actually teaches the first step",
                   "Sensible defaults so nothing starts blank",
                   "A short inline tour, dismissible forever"]},
    ]


def target_date(today: date | None = None) -> date:
    """The day this month's update lands.

    Rolling forward a month when the date has effectively passed, because a
    plan dated in the past would put the site straight into the "live" phase
    and skip the countdown the whole feature exists to show.
    """
    today = today or date.today()
    when = today.replace(day=min(TARGET_DAY, 28))
    while (when - today).days < MIN_LEAD_DAYS:
        month = when.month + 1
        year = when.year + (1 if month > 12 else 0)
        when = date(year, 1 if month > 12 else month,
                    min(TARGET_DAY, 28))
    return when


def _model() -> str:
    return (providers.models("debug") or {}).get("debug", "") \
        or __import__("os").environ.get("GROQ_CHAT_MODEL", "")


def ask() -> dict | None:
    """Let the model choose a theme and write the wording.

    Returns None on any failure, which is the point: the caller falls back to
    the fixed menu rather than shipping a month with no plan.
    """
    menu = themes()
    if not providers.groq_available():
        log("no model available, using the fixed menu")
        return None

    listing = "\n".join(
        f"- {t['id']}: {t['title']}" for t in menu)
    try:
        raw = providers.chat(
            _model(),
            "You plan software releases. You pick from a fixed menu and write "
            "the wording. You never invent a feature.",
            "Pick ONE theme for this month's major update.\n\n"
            f"MENU:\n{listing}\n\n"
            'Reply with JSON only: {"id":"<one id from the menu>",'
            '"title":"<a punchy headline, under 60 chars>",'
            '"notes":["<one line>",3 lines total]. '
            "The headline must promise something concrete a user would notice, "
            "not say 'improvements'.",
            temperature=0.7, max_tokens=400, role="debug")
    except Exception as e:  # noqa: BLE001
        log(f"the model could not be reached: {str(e)[:80]}")
        return None

    try:
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError, AttributeError):
        log("the model did not return JSON, using the fixed menu")
        return None

    # The model may only pick from the menu. An invented id is discarded rather
    # than trusted, because a theme nobody can build becomes a trailer for a
    # feature that does not exist.
    chosen = next((t for t in menu if t.get("id") == d.get("id")), None)
    if not chosen:
        log(f"the model picked {d.get('id')!r}, which is not on the menu; "
            f"falling back")
        return None

    title = " ".join(str(d.get("title") or "").split())[:70].strip()
    notes = [str(n).strip() for n in (d.get("notes") or [])
             if str(n).strip()][:3]
    if not title:
        title = chosen["title"]
    if len(notes) < 2:
        notes = list(chosen["notes"])
    return {"id": chosen["id"], "title": title, "notes": notes,
            "chosen_by": "model"}


def fallback(seen: list[str] | None = None) -> dict:
    """Pick from the menu without the model, avoiding a repeat if it can."""
    menu = themes()
    done = set(seen or [])
    fresh = [t for t in menu if t["id"] not in done]
    pick = (fresh or menu)[0] if fresh else random.choice(menu)
    return {"id": pick["id"], "title": pick["title"],
            "notes": list(pick["notes"]), "chosen_by": "menu"}


def plan() -> dict:
    """Write the plan into the state. Never leaves the state without one."""
    state = us.load()
    when = target_date()

    prev = []
    hist = ROOT / "data" / "update_history.json"
    if hist.exists():
        try:
            prev = [str(x.get("id")) for x in
                    json.loads(hist.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, OSError, AttributeError):
            prev = []

    choice = ask()
    if not choice:
        choice = fallback(prev)

    # 18:00 UTC, so the countdown flips over at the same moment everywhere
    state["next_major"] = f"{when.isoformat()}T18:00:00+00:00"
    state["next_major_title"] = choice["title"]
    state["next_major_notes"] = choice["notes"]
    state["next_major_theme"] = choice["id"]
    us.save(state)
    us.publish_public(state)

    try:
        hist.parent.mkdir(parents=True, exist_ok=True)
        hist.write_text(json.dumps(
            [{"id": choice["id"], "title": choice["title"],
              "date": when.isoformat()}] +
            json.loads(hist.read_text(encoding="utf-8")), indent=2),
            encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        # history is a nicety; a plan without it is still a plan
        pass

    log(f"{choice['title']} on {when.isoformat()} "
        f"(picked by {choice['chosen_by']}, {us.phase(state)} phase)")
    return choice


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        state = us.load()
        print(json.dumps({
            "version": state.get("version"),
            "phase": us.phase(state),
            "days_left": us.days_until(state),
            "theme": state.get("next_major_theme"),
            "title": state.get("next_major_title"),
            "notes": state.get("next_major_notes"),
        }, indent=2))
        return 0

    plan()
    state = us.load()
    print()
    print(json.dumps({"title": state.get("next_major_title"),
                      "when": state.get("next_major"),
                      "phase": us.phase(state),
                      "days_left": us.days_until(state)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())