"""Record the bugs found by the full-project pyflakes scan.

Same reason as record_update_lessons.py: the ids come from buglog so the
fixbook and lessons.txt cannot drift apart.
"""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import buglog

ENTRIES = [
    # ---- crashes
    ("counting the weekly ballot crashed with NameError when the bot could "
     "not read a channel",
     "the 403 branch logged an undefined name. The parameter is called "
     "channel, and name was left over from an older signature, so the "
     "graceful empty-list path was itself the thing that threw",
     "the branch logs the channel it actually failed to read, and every "
     "status now returns an empty list instead of raising",
     ["discord_post.py"],
     "checked by hand: 403, 200, 500 and 429 all return cleanly now"),

    ("the live key checker raised UnboundLocalError the instant it was run, "
     "so it never tested anything",
     "main() read _KEY and then assigned to it in the same function. That "
     "assignment made _KEY local, so the read above it had no value to come "
     "from",
     "the key arrives as a parameter, so there is nothing to shadow and the "
     "function reads only what it is given",
     ["groq_live_check.py"],
     "checked by hand: empty key, wrong prefix and a fake key all return "
     "the right thing instead of crashing"),

    ("re-enabling the video captions would have crashed the renderer with "
     "NameError on every frame",
     "caption() positioned itself with BAND_CAPTION, which was deleted when "
     "captions were removed from the videos. Nothing calls caption() so it "
     "sat there as dead code with a name that no longer exists",
     "the function was deleted rather than given a band, because captions "
     "are not wanted and a resurrected band would be a guess",
     ["shorts_render.py"],
     "pyflakes reports no undefined names anywhere in the project"),

    # ---- wrong behaviour
    ("a release could have been planned for a date that had already passed",
     "the plan wrote a fixed day of the month, so planning near the end of a "
     "month produced a date behind us and the countdown was skipped entirely",
     "this was caught and fixed with the release lane and is listed there "
     "again for completeness",
     ["update_plan.py"],
     "update_selftest.py: planning on the 27th and the 31st roll forward"),

    ("every Friday build waited for the model allowance even when there was "
     "almost nothing spent, and the check it computed was never used",
     "the loop waited whenever spent() was greater than zero, so ten tokens "
     "used meant waiting out the clock with seven thousand left. The limit "
     "and need were calculated and then discarded",
     "the loop asks tokenmeter.affordable(limit, need), which is the function "
     "that already existed for exactly this, and says so out loud when it "
     "starts anyway",
     ["stage_app.py"],
     "tokenmeter.affordable is asserted directly in selftest.py"),

    ("the coach's list of lessons to keep was calculated and then thrown "
     "away, so the model and the file could disagree",
     "the prompt asks for keep, add and drop, but only drop was honoured: "
     "the carried-over list was rebuilt by subtraction instead of taking the "
     "model's own answer",
     "keep wins when the model supplies it, and the subtraction is the "
     "fallback for when it does not",
     ["learn.py"],
     "both branches log which one was used, so a run shows it"),

    ("a run that could not build an app burned its allowance walking the "
     "whole model list on every single call",
     "the function declared global CHAT_MODEL and then only ever read it. "
     "A dead global like that is the fossil of a caching step, and without "
     "it a rate limited first model is retried before every generation",
     "the model that answered is remembered and tried first next time, so the "
     "run stops paying for models that have already failed",
     ["make_app.py"],
     "checked by hand with a stubbed provider: the second call goes straight "
     "to the working model"),

    # ---- data loss
    ("every Wednesday run would have deleted all 110 recorded bugs",
     "learn.py and buglog.py both wrote data/lessons.txt in different "
     "formats. buglog appends a line per entry, learn.py rewrites the whole "
     "file, so whichever ran last destroyed the other",
     "the coach writes its own file. The fixbook keeps lessons.txt, and the "
     "two records can no longer touch each other",
     ["learn.py", ".gitignore"],
     "learn.LESSONS and buglog.LESSONS are asserted to be different files"),

    ("the empty site/licenses folder left over from PayPal was about to be "
     "published, and the exposure check had started failing because of it",
     "paypal.py called LICENSE_DIR.mkdir() at module scope, so simply "
     "importing it created site/licenses. paypal_check.py imports it at module "
     "scope too. The folder is gitignored, so it never appeared in a diff, but "
     "GitHub Pages serves the working tree and check_exposure.py refuses the "
     "whole site when that folder exists, so an import could fail the release "
     "gate on its own",
     "the mkdir moved into save_key, where something is actually written. "
     "Reading and importing no longer touch the published site",
     ["paypal.py"],
     "scan_selftest.py imports every module in a fresh interpreter and fails "
     "if anything new appears under site/"),

    # ---- an audit that was not auditing
    ("the check that stopped an automated job committing a protected file "
     "never asked the guard, so it flagged workflows that merely mentioned "
     "one and passed ones that staged one",
     "weekly_guard was imported as _guard and then never called. The check "
     "was a substring test for a protected filename anywhere in the file, "
     "including inside comments, which is why the release workflow tripped it",
     "the guard is actually asked about every path a blanket git add stages, "
     "so the rule and the enforcement cannot drift apart",
     ["selftest_audit.py"],
     "checked by hand: a comment naming a protected file passes, a real "
     "blanket add of one is reported"),

    # ---- an unreadable file read as zero
    ("a corrupt token counter read as zero spent, so every call looked "
     "affordable and the pipeline spent the whole limit before it noticed",
     "load() caught the parse error and returned {}, and spent() reads an "
     "empty window as zero. In a counter zero is the answer that allows "
     "spending, so the one state that should stop a run was the state that "
     "permitted it. The same file also swallowed its own write errors in a "
     "bare except",
     "an unreadable or non-dict state is reported on stderr and read as "
     "unknown, and spent() returns a figure above any limit so affordable() "
     "is false. The write goes to a temporary file and is swapped in, so a "
     "job that dies halfway leaves the last good total",
     ["tokenmeter.py", "budget.py", "stage_app.py"],
     "audit_selftest.py writes a truncated, a list and a number to the state "
     "and checks each is reported unknown, is not read as zero, and leaves "
     "nothing affordable"),

    ("the monthly budget approved jobs on a month that had already spent "
     "every hour, and its own docstring said the hours were committed and "
     "could not quietly reset",
     "the identical fail-open shape as the token counter: a parse error "
     "returned an empty budget, which read as zero hours used. And commit "
     "380e29e had deliberately untracked budget.json for good security "
     "reasons, so the docstring was asserting a protection that no longer "
     "existed",
     "check() refuses outright when the recorded hours cannot be read, the "
     "write is atomic, and the docstring describes what is actually true: "
     "untracked on purpose, protected by refusing rather than by git",
     ["budget.py"],
     "audit_selftest.py checks a readable budget approves and that truncated, "
     "list and numeric budgets all refuse, and that the docstring no longer "
     "claims the state is committed"),

    ("a release could die on a PermissionError traceback and still have "
     "printed that it saved",
     "save() logged the success line before writing, and neither it nor "
     "publish_public() caught the write error, so an unattended job exited on "
     "a traceback and main() returned 0 either way",
     "both report whether they wrote, neither claims a save it cannot prove, "
     "and main() exits non-zero when either write failed",
     ["update_state.py"],
     "audit_selftest.py makes the state file read-only and checks there is "
     "no traceback, a non-zero exit, and no claim of a save"),

    ("every runner started its token allowance from the last runner's usage",
     "the Friday job's blanket git add committed data/token_usage.json. It is "
     "live rate-limit state for whichever machine is running, so each later "
     "run on another runner read a total it had not earned",
     "the file is ignored along with the temporary files the atomic writes "
     "leave behind, so a blanket add cannot sweep up live state again",
     [".gitignore"],
     "checked by hand: a blanket git add -A in a copy of the tree leaves no "
     "token_usage.json staged, verified by cleanroom_selftest.py"),
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