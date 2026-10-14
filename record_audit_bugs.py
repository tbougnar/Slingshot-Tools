"""Load every defect this audit has confirmed, into the tracker.

The audit runs across many sessions and contexts. Keeping the findings in code
rather than in a markdown table means they are replayable, reviewable, and
cannot drift from the schema. Running this twice is a no-op: entries are
matched by their symptom and existing ids are preserved, so a status update is
never undone by a re-run.
"""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import bugtrack

# id, symptom, severity, component, files, status, root cause, evidence, repro,
# fix, regression test, verification, uncertainty
FOUND = [
    # ---- the automation could not publish anything at all
    ("gitignore hid the deployed free catalogue",
     "HIGH", "repository", [".gitignore", "stage_app.py"], "VERIFIED_FIXED",
     "The ignore patterns were written as \"apps/\" and \"paid/\" with no "
     "leading slash, and git matches an unanchored pattern at every depth. "
     "site/apps/ is the deployed free catalogue, so the Friday job's "
     "\"git add -A\" silently skipped the entire directory.",
     "git check-ignore site/apps/probe/app/index.html returned 0 (ignored). "
     "Run 38311010124 committed data/candidate.json and no app.",
     "git check-ignore site/apps/probe/app/index.html",
     "Anchored both patterns as /apps/ and /paid/.",
     "selftest_audit.py",
     "selftest_audit passes; the guard was confirmed by reverting .gitignore "
     "and watching it report the problem.", ""),

    ("committed state carried the build machine's absolute paths",
     "MEDIUM", "repository", ["stage_app.py", "data/candidate.json"],
     "VERIFIED_FIXED",
     "stage_app stored paid_dir and installer with str(path.resolve()), while "
     "the candidate field beside them was correctly relative. data/"
     "candidate.json is committed, so the Friday runner's own folder layout was "
     "published to every other machine, where it resolves to nothing.",
     "data/candidate.json in 0274226 held \"D:\\a\\Slingshot-Tools\\Slingshot-"
     "Tools\\paid\\dev-converter\".",
     "git show 0274226:data/candidate.json",
     "Both stored relative to the repo via _rel(), which reports a path "
     "outside the repo as empty rather than absolute.",
     "selftest_audit.py checks no tracked state file holds a Windows absolute "
     "path.",
     "selftest_audit reports 0 problems and the committed file now reads "
     "paid/dev-converter.", ""),

    ("NSIS installed but makensis was not on PATH",
     "HIGH", "ci", [".github/workflows/friday-build.yml",
                    ".github/workflows/friday-verify.yml"], "VERIFIED_FIXED",
     "choco install nsis succeeds and writes the machine PATH, but a GitHub "
     "Actions step runs with the PATH it started with, so the install is "
     "invisible to the step that asked for it.",
     "Run 38385940018: \"The term 'makensis' is not recognized\" on the line "
     "immediately after \"The install of nsis was successful\".",
     "gh run view 38385940018 --log-failed",
     "Both jobs resolve makensis.exe from its install location, print where it "
     "was found, fail with a real message if absent, and add the directory to "
     "GITHUB_PATH.",
     "verified by the next run reaching the installer step",
     "Run 38401429866 generated and committed; the generate job completed with "
     "makensis resolved.", ""),

    ("rate limit backoff spent the whole retry budget inside one window",
     "HIGH", "orchestrator", ["providers.py"], "VERIFIED_FIXED",
     "A 429 slept 10s then 20s, but the allowance is per minute, so every "
     "attempt landed inside the same window and received the same refusal. The "
     "verifier then reported the app as unrepairable.",
     "Run 38401720935: rounds 2 to 4 each failed with 429 on "
     "openai/gpt-oss-120b and ended \"4 controls still dead\".",
     "gh run view 38401720935 --log-failed",
     "_rate_limit_wait() waits out the meter's own window plus a margin, still "
     "growing so an exhausted key does not spin.",
     "stubbed sender: a 429 on the first two attempts returns the third "
     "successfully, after 65s then 90s",
     "verified locally with a stubbed provider", ""),

    ("exposure gates refused the app the pipeline had just staged",
     "HIGH", "release gate", ["check_repo_hygiene.py", "check_exposure.py"],
     "VERIFIED_FIXED",
     "The generate job commits the free edition an hour before the verifier "
     "writes its catalog entry, so in between the app is in site/apps/ and in "
     "no catalog. Both gates read that as a leak and failed the run before the "
     "verifier could ever run.",
     "Run 38400432942: \"site/apps/dev-converter-basic is not a known free "
     "edition and must not be public\".",
     "python check_repo_hygiene.py against the freshly generated app",
     "Both now read data/candidate.json and accept the app it names. Anything "
     "else, including a leftover from a retired product, is still reported.",
     "check_repo_hygiene.py and check_exposure.py both pass with the staged app "
     "present",
     "both scripts report ok", ""),

    ("a generated app could not parse, so every control looked dead",
     "CRITICAL", "generation", ["make_app.py"], "VERIFIED_FIXED",
     "Three separate faults. make_app undid the model's JSON escaping one "
     "level at a time, so a doubly escaped reply kept its backslashes. "
     "Decoding only the quotes still left template literal markers escaped, "
     "which closes the template early. Independently, the model mistyped one "
     "closing delimiter. In each case the script block failed to parse, so no "
     "handler ran, so every control was reported dead, so the repair loop spent "
     "its budget patching controls that were never broken.",
     "app_scanner on dev-converter: pageerror \"Invalid or unexpected token\", "
     "6 of 6 controls dead.",
     "app_scanner.scan on the generated file",
     "_unescape() decodes the escapes a JSON string uses and repeats until "
     "stable; js_syntax_errors() checks every script block, using node when the "
     "runner has it and escaping plus delimiter checks when it does not; "
     "html_looks_fine() refuses to stage an app that cannot parse.",
     "jscheck_selftest.py proves the fallback does not cry wolf on ten valid "
     "snippets; audit_selftest.py checks the real generated app parses",
     "the next generate run reported \"attempt 1 ok\" and the app scans with "
     "0 dead and 0 errors", ""),

    ("the scanner refused working apps, so nothing could ever publish",
     "CRITICAL", "quality gate", ["app_scanner.py"], "VERIFIED_FIXED",
     "The probe demanded that clicking any control change the DOM, storage or "
     "an input value. Three classes of control cannot do that and are not "
     "broken: a select the app reads, a submit button in a form with required "
     "fields, and a button that opens a file picker.",
     "dev-converter: dead=[4 controls] on an app that converts correctly.",
     "python app_scanner.py against the generated app",
     "An id the app's script reads is an input, not a button. Submit buttons get "
     "empty required fields filled first. The file inputs' click is "
     "intercepted, and a click that reached one is reported skipped.",
     "scanner_selftest.py builds a page with four genuinely broken controls, "
     "all of which must still be reported dead",
     "scanner_selftest.py: FAILURES: none. dev-converter: dead=[], skipped="
     "['BUTTON:Import My Data']", ""),

    ("the javascript check crashed on a Windows pipe",
     "MEDIUM", "generation", ["make_app.py"], "VERIFIED_FIXED",
     "The node branch passed the script as text, so the pipe encoded it with the "
     "runner's default codepage. An arrow character in the generated app raised "
     "UnicodeEncodeError in subprocess._stdin_write and the whole generate job "
     "died before the check could report anything.",
     "Run 38400432942: UnicodeEncodeError, charmap codec cannot encode "
     "U+2192, in subprocess._stdin_write.",
     "the run log above",
     "The check encodes to UTF-8 itself and decodes the diagnostics the same "
     "way, so the codepage of whatever machine is running cannot change the "
     "verdict.",
     "nodecheck_selftest.py runs the node branch against a stub and fails if "
     "the arrow raises",
     "nodecheck_selftest.py: PASS", ""),

    ("the paid publish outcome was recorded and then thrown away",
     "HIGH", "ci", [".github/workflows/friday-verify.yml"], "CONFIRMED",
     "The step that records the itch.io outcome has no id, so the PUBLISHED "
     "value it writes to GITHUB_OUTPUT belongs to that step and is read by "
     "nothing. The job reports success whether or not the paid edition was "
     "actually published, which is the reporting defect the audit is required "
     "to eliminate.",
     "Workflow inspection: the only step referencing steps.publish is the one "
     "that writes the unused output.",
     "python parse of friday-verify.yml",
     "", "", "NOT YET FIXED", ""),

    ("a debug backup file is committed to the published site",
     "MEDIUM", "website", ["site/apps/password-manager-basic/app/index.r3.bak"],
     "CONFIRMED",
     "qa_loop writes index.rN.bak beside the app it is repairing and nothing "
     "removes it. git add -A committed one into site/, which GitHub Pages "
     "serves. Development-only material shipped in a release.",
     "git ls-files site/apps shows index.r3.bak",
     "git ls-files site/apps",
     "", "", "NOT YET FIXED", ""),

    ("committed per-minute token counter was read as another runner's usage",
     "MEDIUM", "orchestrator", [".gitignore", "tokenmeter.py"], "VERIFIED_FIXED",
     "The Friday job's blanket git add committed data/token_usage.json. It is "
     "live rate-limit state for whichever machine is running, so each later run "
     "on another runner began its allowance from a total it did not earn.",
     "Commit 0274226 contained data/token_usage.json with total 4370.",
     "git show --stat 0274226",
     "The file and its temporary siblings are ignored.",
     "cleanroom_selftest.py copies what git tracks and asserts it survives",
     "token_usage.json is ignored and untracked", ""),

    ("an unreadable counter read as zero, so the pipeline kept spending",
     "HIGH", "orchestrator", ["tokenmeter.py", "stage_app.py"], "VERIFIED_FIXED",
     "_load() swallowed a parse error and returned {}, which spent() read as "
     "zero tokens used. affordable() then answered yes on every call. In a "
     "counter, zero is the answer that allows spending.",
     "Executed the pre-fix module from 0274226 against a corrupt state file: "
     "spent=0, affordable(8000,100)=True.",
     "exec of git show 0274226:tokenmeter.py",
     "An unreadable or non-dict state is reported on stderr and read as "
     "unknown; spent() returns a figure above any limit. The write is atomic.",
     "audit_selftest.py writes truncated, list and numeric states and checks "
     "each is unknown, not zero, and leaves nothing affordable",
     "audit_selftest.py: FAILURES: none", ""),

    ("an unreadable budget read as zero hours, so jobs were approved",
     "HIGH", "orchestrator", ["budget.py"], "VERIFIED_FIXED",
     "The same fail-open shape. A corrupt budget.json returned an empty budget, "
     "which read as a month with nothing spent, so check() approved work on a "
     "month that may already have spent all thirty hours. The module docstring "
     "claimed the hours were committed and could not quietly reset, which was "
     "false: 380e29e had deliberately untracked the file.",
     "Executed the pre-fix module from 0274226: check() returned 0 (approved) "
     "with a corrupt state.",
     "exec of git show 0274226:budget.py",
     "check() refuses outright when the hours cannot be read; the write is "
     "atomic; the docstring describes what is actually true.",
     "audit_selftest.py checks a readable budget approves and corrupt ones "
     "refuse",
     "audit_selftest.py: FAILURES: none", ""),

    ("a release could die on a traceback and still have claimed to save",
     "MEDIUM", "orchestrator", ["update_state.py"], "VERIFIED_FIXED",
     "save() logged its success line before writing, and neither it nor "
     "publish_public() caught the write error, so an unattended job exited on a "
     "traceback and main() returned 0 either way.",
     "Executed the pre-fix module against a read-only state file and against a "
     "read-only public file: PermissionError traceback, exit 1.",
     "exec of git show 0274226:update_state.py in a copied tree",
     "Both report whether they wrote, neither claims a save it cannot prove, "
     "and main() exits non-zero when either failed.",
     "audit_selftest.py makes the state file read-only and checks no traceback, "
     "a non-zero exit and no claimed save",
     "audit_selftest.py: FAILURES: none", ""),

    ("the site advertised a paid product that was not for sale",
     "CRITICAL", "itch.io publishing",
     ["set_itch_url.py", "publish_paid.py", "site/apps.json"], "VERIFIED_FIXED",
     "set_itch_url.valid() required at least one path segment, computed as "
     "len(path.strip('/').split('/')) >= 1. An account front page has the "
     "path '/', so strip gives the empty string, and ''.split('/') is [''], "
     "which has length one and passed. The catalog therefore held the account "
     "page as the product URL, publish_paid.py saw a URL present and a price in "
     "range, and set published=True.",
     "The live store was fetched during the audit and lists zero products. "
     "site/apps.json carried published=true with itch_url pointing at the "
     "account page, and e2e_product.py reported the catalog as published while "
     "the itch.io check failed.",
     "python publish_paid.py password-manager, which exited 0 and left the "
     "tier marked published",
     "valid() now requires a non-empty first path segment and an account "
     "subdomain. publish_paid.py refuses on the same ground and then fetches "
     "the page, refusing to mark anything on sale unless the response contains "
     "a purchase or download section. The catalog was corrected: the paid tier "
     "is published=false with an empty itch_url until a real product page "
     "exists.",
     "itchurl_selftest.py",
     "itchurl_selftest.py: FAILURES: none. publish_paid.py password-manager "
     "now exits 1 with a plain message. check_exposure ok.",
     "The upload to itch.io has still never been executed, because the "
     "credentials exist only as repository secrets. That the store is empty is "
     "confirmed by fetching the live page."),

    ("the installer job built the wrong product because a slug went stale",
     "HIGH", "ci", ["build_paid_only.py", "data/published.json",
                    ".gitignore"], "VERIFIED_FIXED",
     "build_paid_only took the slug from data/published.json, which the verify "
     "job writes and which was committed. Two dispatches in quick succession "
     "left published.json naming dev-converter while the artifact uploaded in "
     "that run held unit-converter, so the installer job looked for a "
     "directory that had never been uploaded.",
     "Run 38416539839 failed with \"no paid build at paid/dev-converter\". "
     "Downloading the paid-build artifact from that same run shows "
     "unit-converter/app/index.html and nothing named dev-converter, so the "
     "correct build was present and was simply not the one it looked for.",
     "gh run download 38416539839 -n paid-build, then compare what arrived "
     "with what data/published.json named",
     "When the recorded slug has no build, exactly one uploaded build is used "
     "and the mismatch is logged and recorded as RETRIED. Two or more is "
     "ambiguous and is refused rather than guessed. data/published.json is "
     "untracked, because the artifact is the authority on what was actually "
     "built and carrying the slug through git only risks it being one release "
     "stale.",
     "paidbuild_selftest.py",
     "paidbuild_selftest.py: FAILURES: none, covering the named build, the "
     "stale-slug fallback, the ambiguous refusal, and no builds at all.",
     "The itch.io upload is still unexecuted; the credentials exist only as "
     "repository secrets."),

    ("itch.io publishing reported success for having done nothing",
     "CRITICAL", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "itch_publish.main() returned 0 when there was no data/published.json, "
     "printing 'nothing was built this week'. The release gate reads the step "
     "outcome, so 0 became PUBLISHED=yes, and the run summary printed 'the "
     "paid edition is on itch.io and advertised'. No request was ever made to "
     "itch.io.",
     "Run 38424937223 is the proof. Its log contains '[itch] nothing was built "
     "this week', then 'PUBLISHED: yes', then 'paid edition is on itch.io and "
     "advertised'. Fetching https://slingshot-tools.itch.io/ after that run "
     "showed the store still listing no products at all. The gate was working "
     "correctly and was fed a lie.",
     "python itch_publish.py with no paid build and no stage file, which "
     "exited 0",
     "Doing nothing now exits 1 and says so. When the stage file is absent but "
     "exactly one paid build exists, that build is published using the title "
     "from its own concept.json, so an untracked stage file no longer stops "
     "the release. More than one build is ambiguous and is refused.",
     "itchpublish_selftest.py",
     "itchpublish_selftest.py: FAILURES: none, covering no build at all, more "
     "than one build, the real module's own output, and that the gate still "
     "keys off the real exit code.",
     "The upload itself still needs the repository secrets; what is fixed is "
     "that the system can no longer claim it happened when it did not."),

    ("a quiet week stopped the website being deployed",
     "HIGH", "ci", ["sync_links.py", "shorts_script.py"], "VERIFIED_FIXED",
     "sync_links calls shorts_script.product() to build a sample YouTube "
     "description for a person to read. That helper raises SystemExit when "
     "there is no product to advertise, and the SystemExit propagated out of "
     "sync_links and failed the Pages job. Between releases there is always "
     "no product to advertise, so the site was only deployable in the window "
     "right after a release.",
     "Run 38428458061 failed at 'Refresh the platform links' with '[shorts] "
     "no product record; nothing to advertise' and exit code 1, and no deploy "
     "step ran.",
     "gh workflow run pages.yml, which failed at the same step",
     "The sample is skipped when there is nothing to say and sync_links exits "
     "zero. A missing product is the normal case between releases.",
     "itchpublish_selftest.py runs sync_links.py and checks the exit code",
     "itchpublish_selftest.py: FAILURES: none. Run 38429073380 deployed the "
     "site successfully.",
     ""),

    # ---- external blockers: confirmed, not fixable from here
    ("no itch.io project exists to upload to",
     "HIGH", "itch.io publishing", ["itch_publish.py", "itch_doctor.py"],
     "BLOCKED",
     "Uploading needs a project, and itch.io has no endpoint for creating one: "
     "every listing path answers 'invalid api endpoint', and the web login "
     "that would create it is behind a Cloudflare Turnstile bot challenge. "
     "Getting past a bot check is evading an anti-abuse control, which this "
     "will not do. The API key is confirmed working, so this is the last "
     "thing standing between the pipeline and a live store.",
     "Run 38630319521: 'The API key works', and butler reached "
     "'/wharf/builds: invalid game' for a project name that does not exist. "
     "Runs 38592104107 and later: the login page is a 'Just a moment...' "
     "interstitial with one cf-turnstile-response input, not a form.",
     "gh run view 38630319521 --log",
     "The person who owns the account creates one empty project by hand at "
     "https://itch.io/settings/mine/new/game, then runs "
     "python set_itch_url.py <slug> https://slingshot-tools.itch.io/<project>. "
     "Everything after that is hands-off forever, because the key uploads "
     "with no session.",
     "itchpublish_selftest.py",
     "The doctor states this outcome explicitly rather than leaving it "
     "implied: the key is accepted, and only the missing project stands in "
     "the way.",
     "If itch.io ever exposes a create endpoint this closes on its own; until "
     "then it needs a human once, and deliberately not on every run."),

    ("the itch.io session cookie is expired",
     "MEDIUM", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "This was believed to block all uploading. It does not. butler "
     "authenticates with the API key, which is confirmed working, so no "
     "session is needed for a release at all and the expired cookie is "
     "irrelevant to the paid path. It is kept only as the fallback for the "
     "one-time project creation that the key cannot do.",
     "Run 38630319521: butler reached the itch.io builds endpoint with the "
     "key and was refused only because the project does not exist, while the "
     "cookie check still reported REFUSED.",
     "gh run view 38630319521 --log",
     "The upload path no longer depends on the cookie, so its expiry blocks "
     "nothing that runs on a schedule.",
     "itchpublish_selftest.py",
     "The doctor distinguishes the two: the key is accepted, the session is "
     "not needed.",
     "The cookie's expiry is expected and is no longer treated as a defect "
     "in the release path."),

    ("no product has ever been uploaded to itch.io",
     "CRITICAL", "itch.io publishing", ["site/apps.json"], "BLOCKED",
     "Every path to a first upload needs a project, and the project cannot be "
     "created from here. Until one product is uploaded there is nothing to "
     "sell, and the customer purchase journey cannot complete. The cause is "
     "the missing project above, not a credential problem: the key is "
     "confirmed working.",
     "https://slingshot-tools.itch.io/ was fetched during this audit and "
     "lists no products. site/apps.json marks every paid tier "
     "published=false with an empty itch_url, which is the truth and is what "
     "the fixes made it say.",
     "webfetch https://slingshot-tools.itch.io/",
     "none available: dependent on the project above",
     "itchurl_selftest.py asserts the catalog never claims to be on sale",
     "itchurl_selftest.py: FAILURES: none. The catalog is honest: 6 free "
     "editions published, 6 paid tiers kept private, no itch_url.",
     "A genuine purchase has never been exercised. No money was spent and no "
     "account was altered at any point in this audit."),

    # ---- second, independent pass
    ("a price could be set below the hard floor and could never be sold",
     "CRITICAL", "pricing", ["pricing.py"], "VERIFIED_FIXED",
     "charm() subtracts a cent unconditionally and was applied after clamp(), "
     "so charm(clamp(1.00)) is 0.99. publish_paid.py and itch_publish.record() "
     "both refuse any price outside $1-$10, so a product nudged to $0.99 could "
     "never be listed. Worse, decide() signals a hold by returning the current "
     "price, so every run also applied charm to a price that had been decided "
     "not to move, sliding it down a cent per run for ever, and writing "
     "audit-log entries that read 'held' beside a price that had moved.",
     "Executed over the full legal range: charm(clamp(1.00)) == 0.99, below "
     "FLOOR, and 323 of 901 legal price points had a float delta of at least "
     "0.01 against the held price.",
     "python -c 'import pricing; pricing.charm(pricing.clamp(1.00))'",
     "A hold now returns before charm is applied, so the price stays exactly "
     "where it was. Clamp happens after charm, never before, and the "
     "comparison is rounded to cents so a float artefact cannot rewrite a "
     "price.",
     "property_selftest.py",
     "property_selftest.py: no failure across 4505 decide/clamp/charm cases; "
     "ten idle runs leave the price at $3.00 and a real cut and raise still "
     "move it.",
     ""),

    ("loading the release state destroyed the per-app version map",
     "HIGH", "release state", ["update_state.py"], "VERIFIED_FIXED",
     "load() coerced both 'apps' and 'next_major_notes' to lists. 'apps' is a "
     "dict of slug to version, so every load replaced it with an empty list.",
     "Reproduced: a state file with apps={'password-manager': '1.4.0'} loaded "
     "to apps=[], app_version() then answered 2.0.0, the company-wide version, "
     "and set_app_version() raised TypeError: list indices must be integers.",
     "python -c 'import update_state; s=update_state.load()' against a state "
     "file with a populated apps map",
     "Each key is coerced to its own type, dict for apps and list for notes.",
     "audit_selftest.py",
     "apps survives load(), app_version() returns the recorded version and "
     "set_app_version() adds without raising.",
     ""),

    ("a failed installer build returned the previous release's binary",
     "HIGH", "packaging", ["build_installer_app.py"], "VERIFIED_FIXED",
     "The NSIS return code was never checked. Only the existence of the output "
     "file was, and dist/ kept the previous release's installer, so a compile "
     "error, a timeout or a full disk still found last week's file and "
     "returned it while printing 'installer built'. build_paid_only.plausible() "
     "only checks size and the MZ header, which a genuine but outdated binary "
     "passes.",
     "The code read 'if not out_exe.exists()' with no test of "
     "r.returncode anywhere before it.",
     "the branch as written",
     "The previous installer is removed before the build, the exit status is "
     "checked, and a failed build also unlinks any partial output. The file's "
     "existence now means this build produced it.",
     "audit_selftest.py checks the return code is examined and the unlink "
     "happens before the build",
     "Both confirmed by reading the compiled source.",
     ""),

    ("shorts captions were placed outside the clip they belong to",
     "HIGH", "shorts", ["shorts_voice.py"], "VERIFIED_FIXED",
     "_words_from_text already returns offsets in seconds, matching the "
     "ElevenLabs alignment path. The estimate path then multiplied them by the "
     "clip duration a second time.",
     "Executed: a 3.0 second line of six words produced offsets "
     "[0.0, 0.5, 1.0, 1.5, 2.0, 2.5] and then [0.0, 1.5, 3.0, 4.5, 6.0, 7.5], "
     "so the last caption fired 4.5 seconds after the clip ended. Nothing "
     "logged it.",
     "python -c 'import shorts_voice as s; print(s._words_from_text(\"a b c\", 3.0))'",
     "The offsets are rounded and used as they come.",
     "audit_selftest.py",
     "Offsets for 1, 3 and 10 second lines all fall inside their clip.",
     ""),

    ("a video shorter than its narration lost the call to action",
     "HIGH", "shorts", ["shorts_mux.py"], "VERIFIED_FIXED",
     "The frame list was trimmed or padded in memory and then discarded. "
     "ffmpeg is given the '%05d.jpg' pattern and reads however many files are "
     "on disk, so the adjustment changed nothing and -shortest then cut the "
     "audio to the shorter video.",
     "The log line 'trim or extend frames: have 880, need 918' was printed "
     "while the directory still held 880 files. The only trace of the problem "
     "was a reassuring message.",
     "read the source: the adjusted list had no reader after the assignment",
     "The trim and the pad happen on disk, the resulting count is verified and "
     "reported, and padding continues the ffmpeg numbering from have + 1 "
     "because starting at have overwrote the last real frame.",
     "checked directly over five trim and pad cases",
     "5->8, 8->3, 880->918, 918->880 and 10->10 all reach the exact count, and "
     "the padded tail is the real final frame.",
     ""),

    # ---- butler could never have uploaded, and said so in a reassuring way
    ("butler was reported missing while sitting in the repository",
     "HIGH", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "butler() looked in ~/.butler and on PATH only. butler.exe is committed "
     "in ./butler, and the workflow extracts the downloaded copy over that "
     "same folder, so the one tool the store depends on was being reported "
     "absent while present in the working directory. upload() logs 'butler is "
     "not installed' and returns False, which reads like a missing "
     "dependency rather than a wrong search path.",
     "Run 38624142147 logged 'butler is not on this machine, so the key cannot "
     "be tested' while actions/checkout had just restored butler/butler.exe.",
     "place a file at butler/butler.exe and call itch_publish.butler()",
     "butler() now checks ~/.butler, ./butler, the repository root and "
     "./bin, each with the platform's executable name, before falling back to "
     "PATH.",
     "itchpublish_selftest.py, plus a direct check that a file at "
     "butler/butler.exe is found",
     "itchpublish_selftest.py: FAILURES: none. The direct check returned "
     "<repo>\\butler\\butler.exe.",
     ""),

    ("the API key was passed to butler as a flag that does not exist",
     "HIGH", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "upload() passed --api_key. butler v15 has no such flag under that "
     "spelling or the hyphenated one, and prints 'unknown long flag' then "
     "exits 1 before making any network request. The key was therefore never "
     "presented to itch.io and no upload could ever have authenticated, "
     "whatever the key's real value was.",
     "'butler.exe : butler: error: unknown long flag' reproduced locally "
     "against the committed butler v15.32.0 for both --api_key and --api-key.",
     "& butler\\butler.exe push src tgt --api_key dummy",
     "The key is handed over in BUTLER_API_KEY, which is what butler's own "
     "CI notice recommends, so it also stays out of the process list that "
     "every other process on the runner can read.",
     "itchpublish_selftest.py",
     "itchpublish_selftest.py: FAILURES: none. The flag was confirmed absent "
     "and the environment route confirmed accepted by butler.",
     ""),

    ("the upload target named a channel itch.io does not have",
     "HIGH", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "ITCH_CHANNEL defaulted to the bare word 'windows'. butler requires the "
     "target as user/slug:channel and rejects the name outright with "
     "'invalid spec ... missing channel', before any request, so every push "
     "died on the local validation of its own arguments.",
     "Locally, butler answered 'invalid spec: slingshot-tools/probe, missing "
     "channel (examples: ...:windows-32-beta, ...:linux-64)'.",
     "& butler\\butler.exe push stub.zip user/project",
     "The default is windows-64, itch.io's own Windows channel, and it stays "
     "overridable through ITCH_CHANNEL.",
     "itchpublish_selftest.py",
     "itchpublish_selftest.py: FAILURES: none.",
     ""),

    ("the doctor's reading of butler inverted the answer it was measuring",
     "HIGH", "itch.io publishing", ["itch_doctor.py"], "VERIFIED_FIXED",
     "The classifier called the result REFUSED whenever the text contained "
     "'invalid'. butler's answer for a perfectly good key and an unknown "
     "project is 'itch.io API error (400): /wharf/builds: invalid game'. That "
     "is the key working: the request reached the builds endpoint and only "
     "the project name was wrong. The rule reported a valid key as refused, "
     "which would have sent this looking for a bad secret that was not bad.",
     "Run 38628290009 logged 'itch.io API error (400): /wharf/builds: invalid "
     "game' followed by '-> the key is REFUSED by itch.io'.",
     "read the classifier's condition and compare it with that error string",
     "Refusal is now 401, 403 or an explicit auth complaint. A 400 "
     "'invalid game', a 404 or 'not found' is read as the key being accepted "
     "and the project being absent, which is the distinction being measured.",
     "itchpublish_selftest.py",
     "Run 38630319521 reported 'The API key works. Upload is therefore fully "
     "automated and needs no session at all.'",
     ""),

    ("the doctor pushed its probe with the arguments the wrong way round",
     "MEDIUM", "itch.io publishing", ["itch_doctor.py"], "VERIFIED_FIXED",
     "butler reads 'push <src> <target>'. The probe passed the project name "
     "as the source and the stub file as the target, so butler tried to walk "
     "a project name as a directory and failed with 'open "
     "slingshot-tools/...: The system cannot find the path specified' before "
     "contacting itch.io. The probe could not have answered the question it "
     "exists to answer.",
     "The identical failure reproduced locally against the committed butler "
     "before the order was corrected.",
     "& butler\\butler.exe push user/project stub.zip",
     "The stub is the source and user/project:windows-64 is the target.",
     "itchpublish_selftest.py",
     "Run 38630319521 reached the builds endpoint and returned the 400, which "
     "is only possible once the argument order is right.",
     ""),
]


def main() -> int:
    existing = {b.get("symptom") for b in bugtrack.load()}
    added = 0
    for (symptom, severity, component, files, status, cause, evidence, repro,
         fix, test, verification, uncertainty) in FOUND:
        if symptom in existing:
            continue
        bugtrack.record(symptom, severity=severity, component=component,
                        files=files, status=status, root_cause=cause,
                        evidence=evidence, repro=repro, fix=fix,
                        regression_test=test, verification=verification,
                        uncertainty=uncertainty)
        added += 1
        print(f"recorded {symptom[:66]}")
    s = bugtrack.stats()
    print()
    print(f"{added} added this run")
    print(f"total {s['total']}, still open {s['open_confirmed']}")
    for k, v in s["by_status"].items():
        if v:
            print(f"  {k:28s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())