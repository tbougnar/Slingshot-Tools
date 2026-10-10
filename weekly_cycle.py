"""Run the weekly cycle: vote Monday, review Wednesday, release Friday.

Three jobs, each one self-contained. Nothing waits for a human and nothing
runs on anybody's PC: the schedules in .github/workflows fire on their own.

    Monday    discord_polls.py        open this week's ballot
    Wednesday reputation + review     read the signals, write the coaching
    Friday    build_paid_only.py      build, verify, publish

Each job asks budget.py before it starts, so a month cannot quietly overspend,
and each checks weekly_guard.py before it commits, so the Wednesday review can
never rewrite the site, a price, or delete a product.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import budget
import weekly_guard as guard

# roughly what each stage costs, used to decide whether it may start
COSTS = {
    "monday": 0.15,
    "wednesday": 0.35,
    "friday": 1.20,
    "emergency": 0.75,
}


def run(args: list[str], label: str) -> int:
    """Run one script and report what it did."""
    print(f"\n{'=' * 62}\n[cycle] {label}: {' '.join(args)}\n{'=' * 62}",
          flush=True)
    try:
        r = subprocess.run([sys.executable, *args], cwd=ROOT, text=True)
        return r.returncode
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[cycle] {label} could not run: {e}")
        return 1


def monday() -> int:
    """Open the ballot for the week."""
    with budget.Timer("monday-vote"):
        return run(["discord_polls.py"], "monday")


def wednesday() -> int:
    """Read the outside world, then write the review."""
    with budget.Timer("wednesday-review"):
        # reputation first: it is what the review reasons about
        run(["reputation.py"], "wednesday/reputation")
        rc = run(["weekly_review.py"], "wednesday/review")

        # the review must not have touched anything it may not touch
        print(f"\n{'=' * 62}\n[cycle] wednesday/guard\n{'=' * 62}",
              flush=True)
        if guard.guard():
            print("[cycle] refusing to continue: the review changed a "
                  "protected file")
            return 1
        return rc


def friday() -> int:
    """Build the tool the ballot asked for, and publish it."""
    print("\n[cycle] what the community chose:", flush=True)
    run(["vote_steer.py"], "friday/steer")

    with budget.Timer("friday-build"):
        rc = run(["build_paid_only.py"], "friday/build")
        if rc != 0:
            print("[cycle] the build did not publish; the week closes with "
                  "nothing shipped")
            return rc
        return 0


def emergency() -> int:
    """Repair something already broken. Uses the reserve budget."""
    with budget.Timer("emergency", emergency=True):
        return run([sys.argv[2], *sys.argv[3:]], "emergency")


def status() -> int:
    s = budget.spent()
    print(json.dumps({
        "week": time.strftime("%Y-W%V", time.gmtime()),
        "budget": {
            "month": s["month"],
            "normal_used_h": s["normal"],
            "normal_limit_h": budget.MONTHLY_HOURS,
            "emergency_used_h": s["emergency"],
            "emergency_limit_h": budget.EMERGENCY_HOURS,
            "remaining_h": budget.remaining(),
        },
        "schedule": {
            "monday": "discord_polls.py, opens the ballot",
            "wednesday": "reputation.py + weekly_review.py, writes coaching",
            "friday": "build_paid_only.py, builds and publishes",
        },
        "guard": {
            "protected": sorted(guard.all_protected()),
        },
    }, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="the weekly cycle")
    ap.add_argument("stage", choices=["monday", "wednesday", "friday",
                                      "emergency", "status"])
    ap.add_argument("script", nargs="?", default="",
                    help="for the emergency stage: the script to repair with")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    if args.stage == "status":
        return status()

    if args.stage == "emergency":
        if not args.script:
            print("[cycle] emergency needs a script to run")
            return 1
        return emergency()

    rc = budget.check(args.stage, COSTS[args.stage])
    if rc != 0:
        print(f"[cycle] {args.stage} skipped: no budget left this month")
        return rc

    return {"monday": monday, "wednesday": wednesday,
            "friday": friday}[args.stage]()


if __name__ == "__main__":
    raise SystemExit(main())