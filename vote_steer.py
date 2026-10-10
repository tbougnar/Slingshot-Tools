"""Stop the bot by guessing which build it should ship.

Picks the concept the community voted for, falling back to an unused one. The
ballot winner is stored as winner_slug, and stored slugs win over labels so a
hand-written ballot still steers a build.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import discord_data as dd
from make_app import pick_concept


def main() -> int:
    closed = [p for p in dd.polls().values()
              if isinstance(p, dict) and p.get("status") == "closed"]
    closed.sort(key=lambda p: p.get("closed") or 0, reverse=True)
    print(f"ballots on record: {len(dd.polls())} "
          f"({len(closed)} closed, {len(dd.polls()) - len(closed)} open)")
    for p in closed[:3]:
        print(f"  {p['id']}: winner={p.get('winner')!r} "
              f"slug={p.get('winner_slug')!r}")

    winners = dd.recent_winners()
    print("steering candidates:", winners or "none")

    concept = pick_concept()
    print()
    print("next build:", concept["slug"], "-", concept["title"])
    for slug in winners:
        if slug == concept["slug"]:
            print(f"  -> came from the ballot winner ({slug})")
            break
    else:
        print("  -> no ballot winner applied, using the default rotation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())