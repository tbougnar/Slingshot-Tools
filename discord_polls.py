"""Open and close community ballots, and steer builds by the result.

This is the AI-controlled half of the Discord server. After each release it:

1. picks the next candidates from the concepts that are not built yet,
2. opens a ballot in `#polls`,
3. later closes an aged ballot, posts the outcome, and leaves the winner in
   `data/polls.json`, where `make_app.pick_concept` reads it and builds that
   tool next.

Everything is a no-op when Discord is not configured, so the build pipeline
never depends on a working bot.
"""
from __future__ import annotations

import json
import os
import sys
import time

import discord_data as dd
import discord_post as dp

# a separate webhook per channel is optional; the bot resolves them by name
POLLS_WEBHOOK = os.environ.get("DISCORD_POLL_WEBHOOK_URL", "").strip()
RESULTS_WEBHOOK = os.environ.get("DISCORD_RESULTS_WEBHOOK_URL", "").strip()
BALLOT_SIZE = 5
BALLOT_CHANNEL = "polls"

sys.path.insert(0, ".")
try:
    from make_app import CATEGORIES, load_built
except Exception:  # noqa: BLE001
    CATEGORIES, load_built = [], (lambda: [])


def log(msg: str) -> None:
    print(f"[polls] {msg}", flush=True)


def ballot_marker(pid: str) -> str:
    """The call to discord_tally, re-exported so there is one source of truth."""
    import discord_tally as dt
    return dt.ballot_marker(pid)


def _post(channel: str, payload: dict, webhook: str = "") -> bool:
    return dp.post(channel, payload, webhook)


def candidates(limit: int = BALLOT_SIZE) -> list:
    """Unbuilt concepts, most specific description first."""
    try:
        taken = {b["slug"] for b in load_built()}
    except Exception:  # noqa: BLE001
        taken = set()
    pool = [c for c in CATEGORIES if c and c[0] not in taken]
    if not pool:
        pool = list(CATEGORIES)
    pool.sort(key=lambda c: (-len(c[1] or ""), c[0]))
    return pool[:limit]


def open_ballot(force: bool = False) -> dict | None:
    """Open a ballot for the next build, unless one is already running."""
    if dd.open_poll():
        log("a ballot is already open")
        return None

    opts = candidates()
    if len(opts) < 2:
        log("not enough unbuilt concepts to hold a ballot")
        return None

    pid = time.strftime("%Y-%m-%d")
    if pid in dd.polls():
        pid = f"{pid}-{len(dd.polls())}"

    labels = [c[0].replace("-", " ") for c in opts]
    dd.create_poll(
        pid,
        "What should Slingshot Tools build next week?",
        labels,
        notes=("One new tool every week. Reply with the number of the one "
               "you want and Friday builds exactly that."))

    # Record the concept slugs the labels stand for, and that voting happens by
    # reply. This has to edit the stored poll, not the dict create_poll
    # returned, or the reload inside _save_polls would drop them and the winner
    # could never be resolved.
    data = dd.polls()
    if pid in data and isinstance(data[pid], dict):
        data[pid]["slugs"] = [c[0] for c in opts]
        data[pid]["method"] = "reply"
        data[pid]["channel"] = BALLOT_CHANNEL
        dd._save_polls(data)
    poll = dd.polls().get(pid)

    if _post("polls", poll_message(poll), POLLS_WEBHOOK):
        log(f"posted ballot {pid}")
        remember_message(pid)
    else:
        log(f"ballot recorded locally (discord: {dp.describe()})")
    return poll


def remember_message(pid: str) -> str | None:
    """Store the ballot's message id once it can be found."""
    mid = dp.find_message(BALLOT_CHANNEL, ballot_marker(pid))
    if not mid:
        log("ballot posted but not yet findable; Friday will search for it")
        return None
    data = dd.polls()
    if isinstance(data.get(pid), dict):
        data[pid]["message_id"] = mid
        dd._save_polls(data)
        log(f"ballot message {mid} recorded")
    return mid


def find_ballot_message(poll: dict) -> str:
    """The ballot's message id: stored if possible, searched for otherwise."""
    return (poll or {}).get("message_id") or dp.find_message(
        BALLOT_CHANNEL, ballot_marker((poll or {}).get("id", "")))


def poll_message(poll: dict) -> dict:
    lines = [f"**{i}. {o['label']}**" for i, o in enumerate(poll["options"], 1)]
    # the marker goes in the footer, which is rendered dimmed rather than in
    # the middle of the options
    body = ("\n".join(lines)
            + f"\n\n{ballot_marker(poll.get('id',''))}\n"
            + f"{poll.get('notes','')}\n\n"
            + "**How to vote:** reply to this message with just the number, "
              "like `3`. You can change your mind by replying again, and only "
              "your last reply counts. The ballot closes on Friday and that "
              "is what gets built.")
# the marker is a Discord spoiler, so it is invisible once rendered
    return dp.embed_message({
        "title": poll["question"],
        "description": body[:4000],
        "color": BRAND(),
        "footer": {"text": f"Ballot {poll['id']} - closes Friday"},
    })


def BRAND() -> int:
    return 0xC1272D


def close_ballot(force: bool = False, pid: str = "") -> dict | None:
    """Close an open ballot, post the outcome, and record the winner.

    ``pid`` names the ballot to close; without it the live one is used.
    """
    poll = None
    if pid:
        poll = dd.polls().get(pid)
        if not isinstance(poll, dict):
            log(f"no ballot called {pid}")
            return None
    else:
        poll = dd.open_poll()
    if not poll:
        log("no ballot is open")
        return None
    if not force and not dd.expired(poll["id"]):
        log(f"ballot {poll['id']} is still open")
        return None

    # count the votes from the replies people left, so nothing had to be
    # running while they voted
    import discord_tally as dt
    labels = [o["label"] for o in poll.get("options", [])]
    counts = dt.collect(poll["id"], poll.get("options", []),
                        poll.get("message_id", ""))
    win_label, tie_broken = dt.decide(counts, labels, poll["id"])

    # write the counts onto the stored poll, so the result survives the runner
    data = dd.polls()
    if isinstance(data.get(poll["id"]), dict):
        for opt in data[poll["id"]].get("options", []):
            opt["votes"] = counts.get(opt.get("label"), 0)
        dd._save_polls(data)

    closed = dd.close_votes(poll["id"], counts, win_label, tie_broken,
                            find_ballot_message(poll))
    if not closed:
        return None

    # store the concept slug too, so the build step does not have to guess it
    # back out of the human-readable label
    slug = resolve_slug(closed)
    if slug:
        data = dd.polls()
        if isinstance(data.get(closed["id"]), dict):
            data[closed["id"]]["winner_slug"] = slug
            dd._save_polls(data)
            closed["winner_slug"] = slug
            log(f"ballot winner steers the next build: {slug}")

    body = dt.report(counts, labels)
    win = closed.get("winner")
    if win:
        tail = ("That is what gets built this week."
                + (" The vote was tied, so it was picked at random."
                   if tie_broken else ""))
    else:
        tail = ("Nobody voted, so the usual rotation is used and the next "
                "ballot decides.")
    body += f"\n\n**{win}** - {tail}" if win else f"\n\n{tail}"

    _post("results", dp.embed_message({
        "title": f"Ballot closed: {closed['question']}",
        "description": body[:4000],
        "color": 0x2ECC71,
    }), RESULTS_WEBHOOK)
    return closed


def resolve_slug(poll: dict) -> str:
    """Map a winning label back to the concept slug it stands for."""
    win = (poll or {}).get("winner")
    if not win:
        return ""
    label = str(win).strip().lower()
    for slug in (poll or {}).get("slugs", []):
        if str(slug).replace("-", " ").lower() == label or str(slug).lower() == label:
            return slug
    return ""


def main() -> int:
    # --dry-run shows what would be posted and changes nothing
    dry = "--dry-run" in sys.argv
    if dry:
        log(f"DRY RUN - discord is {dp.describe()}")
        poll = dd.open_poll()
        if poll:
            print(json.dumps(poll_message(poll), indent=2, ensure_ascii=False))
        else:
            log("no ballot is open; one would be created")
        return 0

    # close any aged ballot first, so a winner can steer the build that the
    # new ballot is being raised for
    closed = close_ballot()
    if closed:
        log(f"winner: {closed.get('winner') or 'tie'}")
    open_ballot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
