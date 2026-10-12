"""Record what building the signal sweep and the goal switch turned up."""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import buglog

ENTRIES = [
    ("nothing has ever been buyable: the paid edition is marked published "
     "but has no itch_url, so the buy button leads nowhere",
     "itch_url has never been set in this repository's history. "
     "publish_paid.py refuses to publish without one, but nothing checked the "
     "flag that was already there, so a published-but-unbuyable product sat "
     "there indefinitely and no gate noticed",
     "check_exposure.py now reports any published paid edition with no "
     "itch_url. It is a warning rather than a failure by default, because "
     "nothing is leaking and fixing it needs one person to open a page; "
     "--strict makes it fatal",
     ["check_exposure.py", "signals.py"],
     "check_exposure.py prints the slug and the command that fixes it, and "
     "exits 1 under --strict"),

    ("the paid build on this machine is a 59-byte placeholder, not an app",
     "paid/password-manager/app/index.html holds a single localStorage "
     "assignment. Nothing verifies that a paid build is a real application "
     "before the catalog calls it built",
     "reported rather than papered over: it is local and gitignored, so it was "
     "never published, but it means the paid edition has never actually been "
     "built and cannot be sold as it stands",
     ["itch_publish.py"],
     "no automatic check yet; signals.py reports catalog_on_sale, which is 0 "
     "until an itch_url exists"),

    ("conversion was reported as zero percent while five sales were recorded",
     "conversion() read the sales count from itch.io, which only returns one "
     "when ITCH_API_KEY is present. Without it the count was 0, and the "
     "recorded order count was fetched and then never used",
     "the order count stands in when itch has no sales of its own, and the "
     "result records which source it came from so the two can be compared",
     ["signals.py"],
     "growth_selftest.py: five orders against two hundred visits is 2.5%, and "
     "itch's own figure still wins when it has one"),

    ("the daily lane assumed two APIs that do not exist",
     "improve_daily called budget.affordable, which budget.py never had, and "
     "passed an argument to self_upgrade.main, which takes none. Both raised "
     "and were swallowed by the same handler, so the lane logged a failure "
     "and moved on every day without ever improving anything",
     "budget.remaining() is the real call and self_upgrade.main() takes no "
     "argument. The caught-and-carried-on handler stays, because a failing "
     "improver must not fail the job",
     ["improve_daily.py"],
     "the lane runs and reports a real reason instead of an AttributeError"),

    ("the self-improvement gate did not know about the new lanes",
     "TEST_SUITE was four scripts. A generator patch could have broken the "
     "thumbnail layout, the release countdown or the homepage JavaScript and "
     "still counted as an improvement, because none of those were in the "
     "suite that decides whether to keep it",
     "TEST_SUITE now includes every lane's selftest plus the link and exposure "
     "checks, so a patch that renders a broken card is discarded",
     ["self_upgrade.py"],
     "self_upgrade.TEST_SUITE is checked against the filesystem at runtime"),

    ("nothing stopped a self-improving job from rewriting the goal it is "
     "measured against",
     "the guard protected prices and the site but not goals.py or signals.py, "
     "so the lane could have edited the standard it is judged on, which is the "
     "same failure as a job that raises its own price ceiling",
     "goals.py, signals.py and improve_daily.py are in MONEY_AND_DEATH for the "
     "same reason pricing.py is, and selftest_audit asserts it",
     ["weekly_guard.py", "selftest_audit.py"],
     "selftest_audit.py: each of them is checked as protected"),
]


def main() -> int:
    existing = {e["symptom"][:60] for e in buglog.load()}
    added = 0
    for symptom, cause, fix, files, detects in ENTRIES:
        if symptom[:60] in existing:
            print(f"skip  {symptom[:60]}")
            continue
        buglog.record(symptom, cause, fix, files, detects)
        added += 1
        print(f"added {symptom[:60]}")
    print()
    print(f"{added} new entries, {len(buglog.load())} in the fixbook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())