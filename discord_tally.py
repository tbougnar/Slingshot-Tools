"""Count a ballot from the replies people leave under it.

Voting has to work without anything staying online, because the only thing that
runs on a schedule is a job. So the ballot is an ordinary message in `#polls`
and members vote by replying to it:

    2

    # or
    vote 2
    2 - because I need this one

The Monday job posts the ballot and remembers its message id. The Friday job
reads the replies through the REST API, counts them, and closes the ballot.
No bot has to be awake while anybody is voting.

Rules that matter:

- one vote per member: their latest reply wins, so changing your mind works
- the bot's own posts are never counted
- a tie is broken by choice, seeded from the ballot, so it is random but
  reproducible and the same ballot always resolves the same way
"""
from __future__ import annotations

import hashlib
import random
import re

import discord_post as dp

BALLOT_CHANNEL = "polls"
BOT_ID = "1558114060178821251"        # Slingshot Tools, so it never votes itself

# A reply is a vote if it starts with the option number, optionally after
# "vote", and may carry a short reason after a dash.
VOTE_RE = re.compile(
    r"^\s*(?:vote\s*)?(?:#\s*)?(\d{1,2})\s*(?:[-–—:.)].*)?$",
    re.IGNORECASE)


def log(msg: str) -> None:
    print(f"[tally] {msg}", flush=True)


def ballot_marker(pid: str) -> str:
    """An invisible marker so Friday can find this ballot's message again.

    A webhook returns no message id, and by Friday the newest message in the
    channel will not be the ballot, so it is found by content. Discord renders
    a spoiler invisibly, so members never see it.
    """
    return f"||ballot-{pid}||"


def parse_vote(text: str, options: int) -> int | None:
    """The option a reply votes for, or None if it is not a vote."""
    m = VOTE_RE.match((text or "").strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= options else None


def collect(pid: str, options: list, message_id: str = "") -> dict:
    """Count the replies under the ballot.

    Returns {option_label: votes}. One member counts once, on their most recent
    reply, so someone who changes their mind is not counted twice.
    """
    mid = message_id or dp.find_message(BALLOT_CHANNEL, ballot_marker(pid))
    if not mid:
        log(f"the message for ballot {pid} cannot be found, so there are no "
            f"votes to count")
        return {}

    # newest first, so the first hit for a member is their latest choice
    replies = dp.messages(BALLOT_CHANNEL, 100)

    labels = [o["label"] if isinstance(o, dict) else str(o) for o in options]
    counts = {label: 0 for label in labels}
    seen: dict[str, int] = {}

    for m in replies:
        author = str((m.get("author") or {}).get("id") or "")
        if not author or author == BOT_ID:
            continue
        content = m.get("content") or ""
        if ballot_marker(pid) in content:
            continue                      # the ballot itself
        choice = parse_vote(content, len(labels))
        if choice is None:
            continue
        if author not in seen:
            seen[author] = choice
            counts[labels[choice - 1]] += 1

    log(f"ballot {pid}: {len(seen)} voter(s), "
        f"{sum(counts.values())} vote(s) counted")
    return counts


def tie_breaker(pid: str, tied: list, labels: list) -> str:
    """Pick one of the tied options at random.

    Seeded from the ballot id, so it is random but the same ballot always
    resolves the same way. That keeps the build reproducible and stops a rerun
    quietly choosing a different tool.
    """
    if not tied:
        return ""
    if len(tied) == 1:
        return labels[tied[0] - 1]
    seed = int(hashlib.sha256(pid.encode("utf-8")).hexdigest()[:8], 16)
    pick = random.Random(seed).choice(tied)
    log(f"{len(tied)} options tied, choosing '{labels[pick - 1]}' at random")
    return labels[pick - 1]


def decide(counts: dict, labels: list, pid: str) -> tuple[str, bool]:
    """The winning label and whether it was decided by a coin toss.

    A tie is not a mandate, so rather than refusing to build anything, one of
    the tied options is chosen at random. The result is posted either way, so
    nobody has to wonder why their tool won or lost.
    """
    if not counts:
        return "", False

    rows = sorted(counts.items(), key=lambda kv: -kv[1])
    top = rows[0][1]
    if top <= 0:
        log("nobody voted, so the default rotation is used")
        return "", False

    tied = [i for i, label in enumerate(labels, 1) if counts.get(label, 0) == top]
    if len(tied) == 1:
        return rows[0][0], False
    return tie_breaker(pid, tied, labels), True


def report(counts: dict, labels: list) -> str:
    """The result as it is posted to the channel."""
    rows = sorted(((label, counts.get(label, 0)) for label in labels),
                  key=lambda kv: -kv[1])
    body = "\n".join(f"- **{label}** - {n} vote(s)" for label, n in rows)
    total = sum(n for _, n in rows)
    return f"{body}\n\n**{total} vote(s) in total.**"


if __name__ == "__main__":
    import discord_data as dd
    poll = dd.open_poll()
    if not poll:
        print("no ballot is open")
    else:
        c = collect(poll["id"], poll["options"], poll.get("message_id", ""))
        labels = [o["label"] for o in poll["options"]]
        print(report(c, labels))
        win, tossed = decide(c, labels, poll["id"])
        print(f"\nwinner: {win}" + (" (chosen at random from a tie)"
                                    if tossed else ""))