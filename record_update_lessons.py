"""Record every bug found while building the monthly release lane.

Kept as a script rather than typed by hand so the ids are right: buglog.record
numbers the entries itself, and hand-numbering them is how the fixbook and the
lessons file drift apart.
"""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import buglog

ENTRIES = [
    # ---- the two that were live on the public site before this work
    ("the homepage showed 'The catalog loads on first build' to every visitor, "
     "so no app was listed at all",
     "groupProducts ended with key:k, but k is bound inside the forEach "
     "callback above it. The map callback that used it ran later, where k no "
     "longer existed, so it threw ReferenceError and took render() with it",
     "the family key is read from the pair itself, key:(full.base_slug||"
     "full.slug), which is always in scope where it is used",
     ["site/index.html"],
     "site_js_selftest.py: the key:k pattern is refused, and the function is "
     "executed in a real browser against a two-entry catalog"),

    ("clicking 'See options' on any product threw 'Unexpected end of input' "
     "and no purchase dialog would ever open",
     "the card button inlined JSON.stringify(item) into a double-quoted "
     "onclick attribute. The JSON contains double quotes, so the first one "
     "closed the attribute early and the browser parsed the rest as junk",
     "the button passes an index instead, openDialogByIndex(idx), and the "
     "handler looks the product up. No JSON is ever written into markup",
     ["site/index.html"],
     "site_js_selftest.py: JSON.stringify must not appear in render()"),

    ("the index passed to the card button came out as '$3.00' instead of a "
     "number",
     "render() already binds p to the formatted price string, so the "
     "interpolation wrote the price into the onclick where an index was meant "
     "to go, and openDialogByIndex looked up a product that does not exist",
     "the map callback takes (item, idx) and the button uses idx",
     ["site/index.html"],
     "site_js_selftest.py: the button may not interpolate the price variable"),

    # ---- the architecture this feature had to work around
    ("there was no version anywhere: the installer hardcoded 1.0.0 and the "
     "catalog had no version field, so an installed app could not be compared "
     "with a published one",
     "version was written into three unrelated places and none of them read "
     "the others, so they disagreed as soon as anything shipped",
     "update_state.py is the only place a version is stored or changed, and "
     "every other script reads it",
     ["update_state.py", "app_update.py"],
     "update_selftest.py: the parse, bump and compare boundaries"),

    ("a patch bump turned 1.9.9 into 1.9.0, which is older than what was "
     "already installed",
     "the bump added one to the last number, so any version ending in 9 or "
     "more carried backwards instead of forwards",
     "bump() parses into three integers and adds to the right one, so 1.9.9 "
     "becomes 1.9.10",
     ["update_state.py"],
     "update_selftest.py: 1.9.9 plus a patch is 1.9.10"),

    ("the update check said 1.10.0 was older than 1.9.0",
     "the versions were compared as strings, and '1.10.0' sorts before "
     "'1.9.0' alphabetically",
     "is_newer() compares parsed integer tuples",
     ["update_state.py", "app_update.py"],
     "update_selftest.py: 1.10.0 is newer than 1.9.0"),

    ("an app that could not reach the update file would have had to show an "
     "error, breaking the promise that an app always opens",
     "the check reads a file that is generated at deploy time, so it is "
     "absent on a fresh machine and unreachable offline",
     "every failure path returns no banner instead of an error, and the "
     "check is off by default when switched off",
     ["app_update.py", "native_launcher.py"],
     "update_selftest.py: a missing public file is not a crash"),

    ("an in-app update notice would have broken the promise that these apps "
     "never make network calls",
     "make_app.html_looks_fine rejects any app containing an external URL, and "
     "APP_SPEC says 'no network calls' twice. A fetch inside the app HTML "
     "would fail the build and break the privacy promise",
     "the check lives in native_launcher.py, which is the native shell and "
     "not the app, and injects the banner after load. The app HTML is "
     "unchanged and still passes html_looks_fine",
     ["app_update.py", "native_launcher.py"],
     "update_selftest.py plus the existing html_looks_fine check"),

    ("every rebuild would stack another update banner on top of the last",
     "inject() ran on every build and appended unconditionally, leaving two "
     "elements with the same id and two visible banners",
     "the injected block is detected by its id and a second injection is "
     "refused",
     ["app_update.py"],
     "update_selftest.py: injecting twice leaves exactly one banner"),

    ("the app file was left corrupted when it had no <body>",
     "inject() assumed a body tag and sliced the string anyway",
     "a document with no body is refused and left untouched",
     ["app_update.py"],
     "update_selftest.py: a page with no body is refused and unchanged"),

    # ---- the countdown
    ("the homepage kept announcing a release that had already shipped",
     "the date was written into the page once and never cleared, so a "
     "committed countdown file survives indefinitely",
     "the countdown is generated during the Pages deploy from the live state "
     "and is never committed. Outside the announcement window the file carries "
     "no date at all, so the banner hides itself",
     ["update_state.py", ".github/workflows/pages.yml"],
     "update_selftest.py: idle and live both publish a null date"),

    ("the Discord event id and other internal state were one copy-paste away "
     "from being published on the public site",
     "update.json is served to everyone, and it is written from the same "
     "state file that holds internal ids",
     "the published file is built field by field and never copies the raw "
     "state",
     ["update_state.py"],
     "update_selftest.py: no event id appears in the published file"),

    ("the countdown banner could have broken the homepage",
     "a broken or missing update.json would leave the fetch rejecting, and a "
     "throw inside that handler could stop the page rendering",
     "every step is guarded and the catch is empty, so the banner stays "
     "hidden and the rest of the page is unaffected",
     ["site/index.html"],
     "site_js_selftest.py: the fetch has an empty catch and escapes its text"),

    ("a release could be planned for a date that had already passed, which "
     "would skip the countdown entirely",
     "the 26th was used as a fixed day, so planning on the 28th produced a "
     "date in the past and the phase went straight to live",
     "target_date() rolls forward a whole month until there are at least ten "
     "days left",
     ["update_plan.py"],
     "update_selftest.py: planning on the 27th and the 31st both roll "
     "forward"),

    # ---- the plan and the event
    ("a month could have no plan at all, because the plan depended on the "
     "model being reachable",
     "the only source of the theme was a model call, and the account runs out "
     "of credits regularly",
     "there is a fixed menu of themes that can actually be built, and the "
     "model may only choose from it. If the model cannot be reached the menu "
     "decides instead",
     ["update_plan.py"],
     "update_selftest.py: fallback lands on the menu and avoids repeats"),

    ("the trailer could advertise a feature nobody built",
     "the model was free to invent a theme, and a title it wrote would become "
     "a promise in a video",
     "an id that is not on the menu is discarded rather than trusted, so only "
     "buildable themes ever reach the script or the trailer",
     ["update_plan.py", "update_trailer_script.py"],
     "update_selftest.py: the fallback and the menu agree"),

    ("re-running the announce step would create a second Discord event for "
     "the same release",
     "events are created by POST and have no natural key, so a retried job "
     "makes another one",
     "the event id is stored in the update state and reused; a stored id that "
     "no longer exists falls through to creating a fresh one rather than "
     "wedging the release",
     ["update_discord.py"],
     "update_selftest.py: existing() reads the stored id"),

    ("the weekly patch lane could have announced itself alongside a major "
     "release",
     "both write the same state file, and the weekly ran whatever day it fell "
     "on",
     "the weekly refuses to run while a major is already in the announced "
     "phase",
     ["update_weekly.py"],
     "checked by hand: with a major three days out the weekly exits without "
     "bumping"),

    ("a weekly release would have been announced as a major change",
     "both lanes bumped the same version field with no distinction recorded",
     "the weekly is hard coded to a patch bump, and update_selftest.py checks "
     "that major and minor are left alone",
     ["update_weekly.py"],
     "update_selftest.py: 1.4.2 becomes 1.4.3 and never 1.5.0 or 2.0.0"),

    # ---- the trailer
    ("the trailer could not reuse the Shorts renderer, because that file is "
     "pinned to a 1080x1920 phone frame",
     "W and H are module level constants used by every gradient, band and "
     "merge in shorts_render, so a landscape frame silently breaks them",
     "update_trailer_render.py draws its own landscape background and uses "
     "shorts_render only for helpers that take no size: font, wrap, ease, the "
     "logo and the screenshots",
     ["update_trailer_render.py"],
     "update_selftest.py: the trailer is landscape and the Shorts is not"),

    ("the trailer's headline was drawn twice, once as a shadow at the wrong "
     "offset, so a ghost of it showed through",
     "the shadow was drawn at a different y from the fill, so the two layers "
     "did not line up",
     "the shadow offsets are applied to the same position the fill uses",
     ["update_trailer_render.py"],
     "checked visually across four timestamps"),

    ("the app card sat on top of the trailer's headline and narration",
     "the card position was computed from the canvas centre while the text "
     "was wrapped to a width that assumed a much narrower frame",
     "the frame is a fixed two-column split: the card owns the right, the text "
     "is wrapped to the space on the left of it",
     ["update_trailer_render.py"],
     "update_selftest.py: every frame renders at the canvas size, and the "
     "split was checked visually"),

    ("the voiceover would have read '[upbeat music]' out loud",
     "the model returns stage directions and markdown often enough to matter, "
     "and the synthesiser speaks whatever it is given",
     "leading cues and markdown are stripped from every line before it is "
     "written",
     ["update_trailer_script.py"],
     "update_selftest.py: a leading cue and bold markers are removed"),

    # ---- the tests themselves
    ("shorts_script_selftest.py crashed with TypeError: sequence item 4: "
     "expected str instance, list found",
     "the test joined every value in the returned dict, and _clean now returns "
     "a 'tour' list alongside the string fields, so the join had a list in it",
     "the test joins only the string values, which is what it meant to check",
     ["shorts_script_selftest.py"],
     "the suite runs to completion again"),

    # ---- the guard
    ("the release workflows were not protected from the self-improvement job",
     "PROTECTED_WORKFLOWS listed the four original workflows, so a job that "
     "could edit its own schedule could edit these two as well",
     "both new workflows are in PROTECTED_WORKFLOWS and selftest_audit.py "
     "asserts they are protected",
     ["weekly_guard.py", "selftest_audit.py"],
     "selftest_audit.py: both are checked as protected"),
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