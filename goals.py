"""Decide what the company is trying to be this week.

There are two goals and they are not both worth chasing at once:

1. **Be found.** Until people can see the work, nothing else matters. A
   beautiful product nobody has heard of earns nothing, and a cheap one
   everybody has heard of earns nothing either. So the first goal is audience.
2. **Be worth buying.** Once there is a real audience, the goal changes to
   money: conversion, price, and getting the paid tier actually purchasable.

The switch is not a feeling, it is a threshold on numbers the company already
collects, and every part of it is written down here so the reasoning is
auditable. Two properties matter most:

- **It can only move forward.** Popularity first, money second. A bad sales
  week must never demote the company back into chasing stars, because that is
  how a business with revenue gets stuck advertising.
- **It cannot promote itself on its own.** Going from "make good things" to
  "sell harder" is a strategy change with a human on the other end of it, so
  it is recommended and recorded, never applied by an automated job. Money
  decisions stay behind the guard in weekly_guard.py.

    python goals.py            what is the goal, and why
    python goals.py --check    promote if the threshold is met, and say so
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "goals.json"
SIGNALS = ROOT / "data" / "signals.json"
HISTORY = ROOT / "data" / "goal_history.json"

# The bar for moving from "be found" to "be worth buying".
#
# These are deliberately low. The point is not to be strict, it is to be
# unambiguous: a number reached is a number the company can rely on, and a
# threshold set too high means the switch never happens and the second half of
# the plan is dead code.
AUDIENCE_TARGET = 50
SALES_TARGET = 5


def log(m: str) -> None:
    print(f"[goals] {m}", flush=True)


def _empty() -> dict:
    return {"phase": "reach", "since": None, "promoted_by": None,
            "notes": []}


def load() -> dict:
    if not STATE.exists():
        return _empty()
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty()
    base = _empty()
    if isinstance(d, dict):
        base.update(d)
    if not isinstance(base.get("notes"), list):
        base["notes"] = []
    return base


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def signals() -> dict:
    if not SIGNALS.exists():
        return {}
    try:
        d = json.loads(SIGNALS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return d if isinstance(d, dict) else {}


def progress(sig: dict | None = None) -> dict:
    """How close the company is to the switch, and what is still missing.

    Every number carries a "known" flag. A figure that could not be collected
    has to read as unknown rather than as zero, because a zero audience and an
    unmeasured audience call for opposite decisions.
    """
    sig = sig if sig is not None else signals()
    conv = sig.get("conversion", {}) or {}
    itch = sig.get("itch", {}) or {}

    audience_known = bool(sig.get("site", {}).get("available")) or \
        bool(sig.get("github", {}).get("available")) or \
        bool(sig.get("youtube", {}).get("available")) or \
        bool(sig.get("discord", {}).get("available"))
    audience_n = int(sig.get("audience") or 0)

    sales_known = bool(itch.get("available")) or \
        bool((sig.get("earnings") or {}).get("available"))
    sales_n = int(conv.get("sales") or 0) if isinstance(conv, dict) else 0
    if not sales_n:
        sales_n = int((sig.get("earnings") or {}).get("orders") or 0)

    return {
        "audience": audience_n,
        "audience_known": audience_known,
        "audience_target": AUDIENCE_TARGET,
        "audience_pct": _pct(audience_n, AUDIENCE_TARGET),
        "sales": sales_n,
        "sales_known": sales_known,
        "sales_target": SALES_TARGET,
        "sales_pct": _pct(sales_n, SALES_TARGET),
        "conversion": conv.get("rate") if isinstance(conv, dict) else None,
        "conversion_known": bool(isinstance(conv, dict) and conv.get("known")),
    }


def _pct(have: int, want: int) -> int:
    if want <= 0:
        return 100
    return max(0, min(100, int(round(have * 100 / want))))


def ready(state: dict, sig: dict | None = None) -> bool:
    """Is the evidence there to change goal?

    Both halves have to be measured. If sales cannot be read, a quiet week is
    indistinguishable from a busy one, and switching on missing data is how a
    company ends up optimising for money before it has a single customer.
    """
    p = progress(sig)
    return (p["audience"] >= AUDIENCE_TARGET
            and p["sales"] >= SALES_TARGET
            and p["audience_known"] and p["sales_known"])


def why_not(state: dict, sig: dict | None = None) -> list[str]:
    """Plain reasons the switch has not happened, for the weekly review."""
    p = progress(sig)
    out = []
    if not p["audience_known"]:
        out.append("audience has never been measured, so it cannot be judged")
    elif p["audience"] < AUDIENCE_TARGET:
        out.append(f"audience {p['audience']} of {AUDIENCE_TARGET} "
                   f"({p['audience_pct']}%)")
    if not p["sales_known"]:
        out.append("sales cannot be read, so a quiet week looks like a busy "
                   "one")
    elif p["sales"] < SALES_TARGET:
        out.append(f"sales {p['sales']} of {SALES_TARGET} "
                   f"({p['sales_pct']}%)")
    return out


def focus(state: dict, sig: dict | None = None) -> list[str]:
    """What the company should actually be doing, given the goal.

    This is the part that makes the goal mean something: a phase that does not
    change what the other jobs do is a label, not a strategy.
    """
    p = progress(sig)
    if state.get("phase") == "earn":
        return [
            "the free edition must lead somewhere buyable, so finish the "
            "itch.io listing and set itch_url before spending anything else",
            "conversion over traffic: a better landing page beats more visits "
            "while the buy button is dead",
            "hold the price steady while sales are thin"
            + (f"; conversion is {p['conversion'] * 100:.2f}%"
               if p.get("conversion_known") and p.get("conversion") is not None
               else ""),
            "fix the paid build: a placeholder app is worth nothing to sell",
        ]
    return [
        f"reach {AUDIENCE_TARGET} people first; currently {p['audience']}"
        + ("" if p["audience_known"] else " (unmeasured)"),
        "ship in public and say where it is, because reach comes from being "
        "linked to more than the ballot",
        "a free tool that people actually keep is the advertisement",
        "do not tune price yet: there is no audience to price against",
    ]


def check(apply: bool = False) -> dict:
    """Recommend the switch, and apply it only if explicitly asked.

    An automated job calls this with apply=False and records the
    recommendation. Promotion stays a human decision, because it is the one
    place where being wrong costs money rather than pride.
    """
    state = load()
    sig = signals()
    p = progress(sig)

    # The phase is a decision, and decisions have to outlive the runner that
    # made them. Without this the file is only written on promotion, so a
    # promotion made by hand would vanish the next time CI ran and the company
    # would go back to chasing reach with no way to tell that had happened.
    if not STATE.exists():
        state.setdefault("phase", "reach")
        save(state)

    out = {
        "phase": state.get("phase", "reach"),
        "ready": ready(state, sig),
        "progress": p,
        "blockers": why_not(state, sig),
        "focus": focus(state, sig),
    }

    if out["phase"] == "earn":
        out["recommendation"] = "stay on earning; the switch is done"
        return out

    if out["ready"] and apply:
        state["phase"] = "earn"
        state["promoted_by"] = "automatic"
        state["notes"] = (state.get("notes") or [])[-9:] + [
            "promoted to earning: audience and sales both cleared"]
        save(state)
        _record("earn", f"audience {p['audience']}, sales {p['sales']}")
        out["phase"] = "earn"
        out["recommendation"] = "PROMOTED to earning"
    elif out["ready"]:
        out["recommendation"] = ("READY to switch to earning; an automated job "
                                 "will not do it on its own")
    else:
        out["recommendation"] = "stay on reach"
        if not p["audience_known"] or not p["sales_known"]:
            out["recommendation"] += (
                " (not enough data to judge either way, which is the honest "
                "answer)")
    out["focus"] = focus(load(), sig)
    return out


def _record(phase: str, why: str) -> None:
    rows = []
    if HISTORY.exists():
        try:
            rows = json.loads(HISTORY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            rows = []
    from datetime import datetime, timezone
    rows.append({"at": datetime.now(timezone.utc).isoformat(),
                 "phase": phase, "why": why})
    HISTORY.write_text(json.dumps(rows[-40:], indent=2), encoding="utf-8")


def main() -> int:
    args = [a.strip().lower() for a in os.sys.argv[1:]]
    got = check(apply="--apply" in args)
    print(f"GOAL: {got['phase'].upper()}")
    print()
    print(f"  audience      : {got['progress']['audience']} of "
          f"{got['progress']['audience_target']} "
          f"({got['progress']['audience_pct']}%)"
          + ("" if got["progress"]["audience_known"] else "  [unmeasured]"))
    print(f"  sales         : {got['progress']['sales']} of "
          f"{got['progress']['sales_target']} "
          f"({got['progress']['sales_pct']}%)"
          + ("" if got["progress"]["sales_known"] else "  [unmeasured]"))
    print("  conversion    : "
          + (f"{got['progress']['conversion'] * 100:.2f}%"
             if got["progress"]["conversion_known"] else "unknown"))
    print()
    print(f"  decision      : {got['recommendation']}")
    for b in got["blockers"]:
        print(f"    - {b}")
    print()
    print("  FOCUS")
    for f in got["focus"]:
        print(f"    - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())