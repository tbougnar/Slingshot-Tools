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

    ("publish asked the browser for a session that the API key does not need",
     "CRITICAL", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "Step 1 of publish() asked find_game() whether the project already "
     "existed. find_game() reads the itch.io listing API, and every path on "
     "that API answers 'invalid api endpoint', so it always returned nothing. "
     "That sent every release down the browser-creation path, which needs a "
     "session, which the bot challenge refuses. The run therefore died "
     "asking for a cookie while holding a working API key, and never once "
     "attempted the upload the key was obtained for.",
     "Run 38636758615: '[itch] no usable itch.io session could be established' "
     "and 'set ITCH_LOGIN and ITCH_PASSWORD once', while the doctor in the "
     "same run reported 'The API key works'.",
     "call publish() for a slug whose project exists, with no KEY and no "
     "session available",
     "Existence is decided from what can be trusted: the catalogue entry's "
     "itch_url when its public page answers, and only then the API. A live "
     "catalogue entry goes straight to the upload, so no session is looked "
     "for. Only a genuinely absent project now needs the browser, and that "
     "message names the one-time manual step instead of asking for a "
     "credential that would not have helped.",
     "itchpublish_selftest.py asserts working_session() is never called when "
     "the catalogue points at a live page",
     "itchpublish_selftest.py: FAILURES: none. The test fails if the "
     "catalogue lookup is removed.",
     "The API listing endpoint remains unreadable, so find_game() is kept as "
     "a fallback but is no longer the only way existence is decided."),

    ("each release deleted the previous product's build from the store",
     "CRITICAL", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "Every product was pushed to the same channel, windows-64, inside the one "
     "shared project. An itch.io channel holds a single build, so each weekly "
     "release replaced the one before it. After three successful runs the store "
     "listed only the newest build while the catalogue still advertised all "
     "three as purchasable, so a customer could pay for a download that was no "
     "longer there. That is worse than the empty store this audit spent its "
     "effort on: an empty shop is honest, a shop selling what it no longer has "
     "is not.",
     "After run 38900671183 the project page listed only 'Base64 and URL "
     "encoding tool-Setup.exe', while the catalogue marked chess-clock, "
     "markdown-preview and base64-tool as published, so two of the three had "
     "nothing to download.",
     "publish two different products into the shared project and fetch the "
     "page afterwards",
     "Each product gets its own channel, derived from its slug, so the builds "
     "accumulate instead of overwriting. ITCH_CHANNEL still overrides it for "
     "anyone who wants a single channel, and the workflow no longer pins a "
     "channel that would defeat the per-product default.",
     "itchpublish_selftest.py asserts two products resolve to two different "
     "channels, and that no workflow pins one",
     "itchpublish_selftest.py: FAILURES: none. butler accepted a per-product "
     "channel name and refused only on the deliberately dummy key with 403, "
     "which is the refused-key shape rather than a bad-channel one.",
     "The builds already overwritten are gone from the store and have to be "
     "put back by publishing those products again."),

    ("record() put a store URL on the free edition of a published product",
     "HIGH", "itch.io publishing", ["itch_publish.py", "set_itch_url.py"],
     "VERIFIED_FIXED",
     "record() wrote itch_url onto every entry of the family, the free basic "
     "edition included, each time a product was published. The free edition is "
     "served from this site and is never uploaded to itch.io, so the catalogue "
     "claimed it was on a store it had never reached. set_itch_url.py --all had "
     "already been corrected for this, but record() is the path that runs on "
     "every release, so the correction never held.",
     "site/apps.json carried itch_url on base64-tool-basic and "
     "markdown-preview-basic, both free editions whose paid siblings were "
     "published.",
     "publish a product and read the free edition's itch_url",
     "record() writes the URL to the paid edition only and clears any stale "
     "one from the free edition, so the catalogue cannot claim a free app is on "
     "itch.io.",
     "itchpublish_selftest.py asserts no free edition of a published product "
     "carries a store URL",
     "itchpublish_selftest.py: FAILURES: none, and the catalogue was cleaned "
     "and re-checked.",
     ""),

    ("one unlucky request deleted a project that existed",
     "HIGH", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "page_is_live made a single request and treated anything other than 200 "
     "as proof the project did not exist, including a 429 and a timeout. "
     "itch.io rate-limits, and four consecutive probes of the same live page "
     "returned True, False, True, False. The publish path turned one of those "
     "into 'the store project did not answer', fell through to browser project "
     "creation, and told the account holder to go and create a project they "
     "had already created and that had been uploaded to twice.",
     "Run 38912830336: '1. the store project did not answer' followed by 'no "
     "project exists and one cannot be created from here'. Concurrently on the "
     "same URL, page_probe returned True, False, True, False.",
     "call page_is_live on the live store project several times in a row",
     "The probe now distinguishes a verdict from a refusal. 403 and 404 are "
     "verdicts, so the page genuinely is not there; 429, 5xx and transport "
     "errors are refusals and are retried with backoff. If the store never "
     "answers, the run stops and says the store declined to answer, which is "
     "not the same as saying it does not exist.",
     "itchpublish_selftest.py drives a probe that declines twice then answers, "
     "and one that never answers",
     "itchpublish_selftest.py: FAILURES: none. It is probed three times and "
     "concluded live, and four times before giving up when it never answers.",
     ""),

    ("two products were on sale with no download behind them",
     "CRITICAL", "itch.io publishing", ["itch_publish.py"], "VERIFIED_FIXED",
     "Step 4 asked only whether the project page answered. The store is one "
     "project holding every product, so it answers perfectly well while "
     "missing the particular build being sold. chess-clock and markdown-preview "
     "had been published before builds got their own channel; their builds were "
     "replaced by later releases and the catalogue kept offering them, which is "
     "taking money for a download that cannot be delivered.",
     "The store listed 'Base64 and URL encoding tool-Setup.exe' and 'Offline "
     "password manager-Setup.exe' while the catalogue marked chess-clock and "
     "markdown-preview as published. build_is_listed confirmed chess-clock's "
     "file is absent.",
     "publish a product, then replace its build, and check whether the site "
     "still offers it",
     "Publishing now verifies that this product's own installer file is listed "
     "on the page before it is advertised, retried because itch.io publishes "
     "builds asynchronously after the upload returns. The two orphans were "
     "taken off sale, since nothing can restore them without rebuilding those "
     "products and advertising them is worse than not offering them.",
     "itchpublish_selftest.py asserts the step-4 check exists and that no "
     "advertised paid product lacks a build",
     "itchpublish_selftest.py: FAILURES: none. The store now lists a build for "
     "every product on sale.",
     "chess-clock and markdown-preview will return to the shop if and when the "
     "pipeline builds them again."),

    ("the builder could upload one product's installer as another's",
     "CRITICAL", "packaging", ["build_paid_only.py", "itch_publish.py"],
     "VERIFIED_FIXED",
     "find_existing returned the first plausible *-Setup.exe anywhere in "
     "dist/, which is a folder shared by every build, with no regard for which "
     "product the file belonged to. Building chess-clock reused "
     "invoice-maker-Setup.exe. The publisher's find_installer had the same "
     "shape, falling back to `needle in stem or stem in needle`, a substring "
     "test in both directions. Either one sells a customer the wrong tool "
     "under the name they paid for.",
     "python rebuild_paid.py chess-clock reported 'ready for itch.io: "
     "dist\\invoice-maker-Setup.exe' for a product it had just reconstructed as "
     "chess-clock. dist/ held eleven installers, none of them chess-clock's.",
     "put another product's installer in dist/ and build this product",
     "find_existing only accepts a dist installer whose normalised name is "
     "this product's, and find_installer no longer falls back to a substring "
     "match at all. A missing installer stops the release, which is "
     "recoverable; shipping the wrong tool is not.",
     "itchpublish_selftest.py puts a foreign installer in dist/ and checks "
     "neither the builder nor the publisher will take it",
     "itchpublish_selftest.py: FAILURES: none.",
     ""),

    ("importing a module created directories in the repository",
     "LOW", "repository", ["itch_login.py"], "VERIFIED_FIXED",
     "itch_login.py called mkdir on .sessions and .cookies at module level, so "
     "merely importing it, including from a check that never runs the login, "
     "put two folders in the working tree. This is the general shape of the "
     "defect that started this audit's catalogue incident: a file nobody "
     "intended to write appearing in the tree. The module is gitignored on "
     "purpose because it handles a session cookie, so this affects the "
     "working copy only and no workflow runs it.",
     "prove_everything.py reported 'itch_login.py (mkdir)' as the one module "
     "that wrote to disk on import, twice, once for each directory.",
     "import itch_login with .sessions and .cookies absent and check whether "
     "they appear",
     "Both directories are created where they are written, inside the "
     "function that needs them, not on import.",
     "prove_everything.py, which checks every module for writes at import",
     "prove_everything.py: 0 BROKEN. Importing itch_login now creates neither "
     "directory.",
     ""),

    ("generating the audit report took twenty-three minutes",
     "MEDIUM", "tooling", ["audit_report.py"], "VERIFIED_FIXED",
     "The report runs the whole suite, including cleanroom, and then "
     "write_report() called main() a second time to capture its output. Every "
     "check therefore ran twice, so a document that reads as a summary cost "
     "more than twenty minutes and would time out in CI.",
     "Timed at 1410s before and 654s after, with run_selftests.py at 330s and "
     "cleanroom_selftest.py at 284s being paid for twice.",
     "time python audit_report.py",
     "The output of the single run is captured once and written from that, so "
     "the checks run one time. --quick leaves out the live customer journeys "
     "as well, for anyone who wants the document without the network.",
     "prove_everything.py runs it as an entry point and reports how long it "
     "took",
     "prove_everything.py: EXECUTED, rc=0 in 554.6s.",
     "The report is still a heavy thing to generate because it genuinely runs "
     "the suite; --quick is the fast path."),

    ("a product's own installer could not be found under the name it shipped as",
     "HIGH", "packaging", ["itch_publish.py", "build_paid_only.py",
                            "itchpublish_selftest.py"], "VERIFIED_FIXED",
     "Two builders name their output differently: make_app.py writes "
     "'<slug>-Setup.exe' and build_installer_app.py writes '<title>-Setup.exe'. "
     "find_installer matched only the slug and find_existing matched only "
     "paid.name, so neither recognised a title-named installer - which is the "
     "form actually on the store. find_installer('base64-tool') and "
     "find_installer('password-manager') both returned None while the store was "
     "selling 'Base64 and URL encoding tool-Setup.exe' and 'Offline password "
     "manager-Setup.exe'. The knock-on effect is worse than a failed lookup: "
     "rebuild_paid.py asks find_installer for the file it just built, so it "
     "would have reported that a live product 'cannot be reconstructed' and "
     "left it off the shelf indefinitely.",
     "find_installer('password-manager') returned None next to a dist/ folder "
     "holding 'Offline password manager-Setup.exe', its live build.",
     "ask find_installer and find_existing for a product whose installer is "
     "named after its title",
     "Both now match the slug and the title, derived from paid/<slug>/"
     "concept.json and the catalogue, each still as an exact match so a foreign "
     "installer cannot be substituted. find_existing also had to normalise the "
     "whole file name rather than Path.stem, because _norm strips 'setup.exe' "
     "and the stem had already removed the '.exe', leaving a trailing 'setup' "
     "that matched nothing.",
     "itchpublish_selftest.py checks a title-named installer is found for its "
     "own product and that a foreign one beside it is not",
     "itchpublish_selftest.py: FAILURES: none.",
     ""),

    ("the paid edition could be unlocked by adding ?paid to the free app's URL",
     "CRITICAL", "revenue", ["site/apps/*/app/index.html",
                             "tier_gate_selftest.py"], "VERIFIED_FIXED",
     "Twenty-five free editions were generated with "
     "`const PAID = new URLSearchParams(location.search).has('paid')` feeding "
     "the limit table, so the paid edition was the same file with nothing else "
     "standing between a visitor and the full product except a query string. "
     "Adding ?paid to the free app's own URL unlocked it. Every one of those "
     "twenty-five apps is a paid product and two of them, password-manager and "
     "base64-tool, are on the store for $3, so the bypass was live and free to "
     "anyone who guessed the parameter. The current generator bakes the "
     "edition in as TIER at build time instead, and rebuild_paid.py produces "
     "the full edition by flipping that one constant, so there is no runtime "
     "switch to reach.",
     "the live free app at .../apps/password-manager-basic/ contained "
     "`const PAID=new URLSearchParams(location.search).has('paid');const "
     "LIM=PAID?{max:Infinity,export:true}:...`, so ?paid was the whole lock.",
     "append ?paid to a free edition's URL and read its limit table",
     "All twenty-five were rewritten to decide from TIER, not from the URL: "
     "`const LIM=TIER==='full'?{unlimited}:{basic}`. Flipping TIER to full "
     "still yields the paid edition, so rebuild_paid.py is unaffected, and the "
     "free edition is now genuinely limited with no way to reach the full one "
     "from the address bar.",
     "tier_gate_selftest.py reads every free edition and fails if any gates on "
     "the query string, or is labelled basic without a real limit table, or "
     "does not flip to a different full edition",
     "tier_gate_selftest.py: 34 free editions, FAILURES: none. Injecting the "
     "exploit back into one app makes it fail, so the test bites. The "
     "standalone copy at site/apps/<name>/index.html, which is the file served "
     "at the catalogue's URL, carried the same gate and is checked as well; "
     "fixing only app/index.html would have left the live exploit in the file "
     "people actually open.",
     ""),

    ("a successful paid build reported a failure after the installer was made",
     "MEDIUM", "packaging", ["build_paid_only.py"], "VERIFIED_FIXED",
     "build() logged where it had kept the installer with "
     "kept.relative_to(Path.cwd()). When the job runs from a different working "
     "directory than the repository, which is how CI invokes it, the installer "
     "is not under the cwd and relative_to raises ValueError. The exception "
     "came after the installer had been built and copied, so a finished build "
     "was reported as a crash and the release was abandoned with a valid "
     "installer sitting on disk.",
     "python build_paid_only build() from a different cwd raised ValueError: "
     "'paid\\password-manager\\Offline password manager-Setup.exe' is not in "
     "the subpath of the current directory, after printing 'installer built "
     "(19.6 MB)'.",
     "run the paid build with a working directory outside the repository",
     "The path is shown relative to the repository when it is inside it, and "
     "as an absolute path when it is not, with no exception either way.",
     "paidbuild_selftest.py builds a paid edition and checks it is kept",
     "paidbuild_selftest.py: FAILURES: none.",
     ""),

    ("the release countdown was a day out for part of every day",
     "HIGH", "product", ["update_state.py", "property_selftest.py"],
     "VERIFIED_FIXED",
     "days_until, which phase() and therefore the banner, the Discord event and "
     "the trailer all read, computed its answer with now().date(). now() is "
     "UTC, while _empty() stamps date.today() and every other function in "
     "update_state reads the local calendar day. In any positive-offset "
     "timezone there is an hour each night where the two dates differ, and in "
     "that hour the countdown was one day long and the phase was wrong: on the "
     "release day itself phase returned 'announced' instead of 'live', so the "
     "countdown would not read zero on the day and the Discord event and the "
     "trailer would disagree about whether it had shipped. The suite could not "
     "pass on a clean checkout during that hour, which is how it was found.",
     "property_selftest.py failed five date checks on a clean checkout at "
     "2026-10-21 00:19 local, when UTC was still 2026-10-20: 'a date 100 days "
     "out is idle and 100 days away' reported 'idle / 101' and 'the day itself "
     "is live' reported 'announced'.",
     "run the date checks at a moment when the local date and the UTC date "
     "differ",
     "days_until uses date.today(), the same calendar day the rest of the "
     "module uses, so the countdown, the phase, the banner and the state's own "
     "timestamp agree at every hour.",
     "property_selftest.py now pins the two clocks together: a release 30 days "
     "out must report 30, whatever the hour",
     "property_selftest.py: FAILURES: none. Restoring now().date() makes the "
     "new check fail along with the five originals, so it bites.",
     ""),

    ("the scheduled lanes died on a missing dependency before doing any work",
     "HIGH", "pipeline", [".github/workflows/daily-improve.yml",
                          ".github/workflows/weekly-patch.yml",
                          ".github/workflows/wednesday-review.yml",
                          ".github/workflows/check-connections.yml",
                          ".github/workflows/monthly-update.yml",
                          "selftest.py", "tracked_selftest.py"],
     "VERIFIED_FIXED",
     "selftest.py imports every project module to prove they load, and one of "
     "them, update_trailer_render, imports pillow at module level; the same "
     "selftest parses every workflow with yaml. Five scheduled lanes installed "
     "requests alone, so they crashed on 'No module named PIL' and then 'No "
     "module named yaml' before running a single real check. The daily "
     "self-improvement lane, the weekly patch lane, the Wednesday review and "
     "the connections check had all been failing that way in every retained "
     "run, so the production pipeline was dead while the suite it could not "
     "reach stayed green on a developer machine that happened to have the "
     "libraries installed.",
     "gh run list showed daily-improve failing every retained run back to "
     "2026-10-13, each in about 13 seconds; gh run view --log-failed showed "
     "'FAIL modules import ModuleNotFoundError: No module named PIL' and 'FAIL "
     "workflows parse ModuleNotFoundError: No module named yaml'.",
     "install requests alone in a fresh venv and run selftest.py, which is what "
     "the lanes did: 11/13 pass, both failures are the missing modules",
     "the five lanes install pillow and pyyaml alongside requests, the set the "
     "tests actually import.",
     "tracked_selftest.py now reads each workflow's install step and fails if a "
     "workflow that runs selftest.py does not install pillow and pyyaml",
     "a fresh venv with requests alone reproduces 11/13; adding pillow and "
     "pyyaml makes selftest.py and every other script the lanes run exit 0. "
     "Removing a dependency from a workflow makes the new check fail, so it "
     "bites.",
     ""),

    ("the test suite posted a real announcement to the real Discord server",
     "HIGH", "tests", ["update_selftest.py", "discord_post.py"],
     "VERIFIED_FIXED",
     "update_selftest.py called update_discord.upsert() and expected it to "
     "return False because there are no credentials. The credentials are read "
     "from the environment when discord_post is imported, and a scheduled "
     "runner has DISCORD_BOT_TOKEN and DISCORD_GUILD_ID set, so on the runner "
     "the check created a real scheduled guild event and then failed, because "
     "the call returned True. The test was testing the ambient environment "
     "rather than the guard, and it was the only thing standing between the "
     "suite and the live server. Run 39640947607 is the evidence: the log "
     "reads 'created event 1562512689769484331' and then 'FAIL upsert without "
     "credentials is safe'.",
     "gh run view 39640947607 --log showed '[event] created event "
     "1562512689769484331 for 2026-10-26T18:00:00+00:00: Major update' "
     "immediately before the failing check, so the test really did create the "
     "event rather than merely report that it might.",
     "run update_selftest.py with DISCORD_BOT_TOKEN and DISCORD_GUILD_ID set",
     "the test forces dp.TOKEN and dp.GUILD_ID to empty for the duration of "
     "the check and restores them afterwards, so it tests the guard and "
     "cannot reach Discord whatever the machine has.",
     "update_selftest.py now clears both credentials around the check and "
     "restores them in a finally block, and the check still fails if the "
     "guard is removed",
     "with dummy credentials set the test passes and prints no 'created "
     "event' line, so the server is not touched; without the credentials "
     "cleared it creates a real event, which is what the old code did.",
     ""),

    ("the test suite could have pushed a real build to the real store",
     "HIGH", "tests", ["itchpublish_selftest.py", "itch_publish.py",
                       "testenv.py"],
     "VERIFIED_FIXED",
     "itchpublish_selftest.py starts itch_publish.py as a subprocess with the "
     "inherited environment and the real repository as its working directory. "
     "itch_publish reads ITCH_API_KEY and ITCH_USER, so on a runner with "
     "those set the child found the real paid build, resolved the live store "
     "page and called butler. It failed here only because the local key was "
     "not valid, so nothing was uploaded, but the path to a real upload was "
     "open. The in-process part of the same test cleared ip.USER only, and "
     "the upload path uses the API key, so that guard did not hold either.",
     "running the child with the itch.io and butler variables stripped still "
     "reached butler and printed 'creating build on remote server: itch.io "
     "API error (400): /wharf/builds: invalid target (bad user)', which is a "
     "remote call made before the run failed",
     "start itch_publish.py with no itch.io credentials but with a paid build "
     "present and watch whether butler is reached",
     "the test scrubs the credentials from every child it starts, and "
     "itch_publish.upload() now refuses before running butler when there is "
     "no itch.io user, naming the variable that is missing",
     "itchpublish_selftest.py starts every child with the scrubbed "
     "environment and asserts that upload() starts no process at all when "
     "there is no user",
     "with the credentials stripped the child no longer reaches butler; "
     "removing the guard from upload() makes the new check fail, so it "
     "bites.",
     ""),

    ("the test suite could have spent real model money",
     "HIGH", "tests", ["audit_selftest.py", "testenv.py"],
     "VERIFIED_FIXED",
     "audit_selftest.py ran improve_daily.py in a copied directory with the "
     "inherited environment. A copied directory protects the files, not the "
     "API: improve_daily calls the model provider, the provider reads "
     "GROQ_API_KEY from the environment, and the scheduled lane that runs "
     "audit_selftest.py has a real one. The check that a module survives a "
     "missing data file was therefore making a real, billable request.",
     "the sanitised environment was applied to the first improve_daily run "
     "only; the run at line 81, inside the loop over six modules, inherited "
     "everything, and the lane that runs this test sets GROQ_API_KEY",
     "run audit_selftest.py with a GROQ_API_KEY set and watch whether a "
     "request is made",
     "every child a test starts now gets the environment from testenv, which "
     "takes out the provider keys and the service credentials, and the "
     "runners that start the whole suite scrub the environment for their "
     "children as well",
     "selftest_audit.py now reads the source of every selftest and fails "
     "when one starts a child process with the inherited environment, or "
     "with an environment copied from os.environ",
     "a fresh venv with requests alone shows the lane failing on the missing "
     "module; the static check reports zero problems across 140 files, and "
     "removing the env= from one call makes it report that one file",
     ""),

    ("the test suite destroyed the rate limit and the budget that protect it",
     "MEDIUM", "tests", ["selftest.py", "audit_selftest.py",
                         "tokenmeter.py", "budget.py"],
     "VERIFIED_FIXED",
     "selftest.py and audit_selftest.py tested the token meter by resetting it "
     "and adding to it, and they did that against the real data "
     "directory, so the recorded spend was zeroed and the guard that decides "
     "whether the pipeline may spend was disarmed for the rest of the month. "
     "audit_selftest.py did the same to the real budget file, writing "
     "invalid content over it and restoring it afterwards, so a run killed "
     "in between left the allowance unreadable, which refuses every job. Its "
     "backup was written next to the real file as data/budget.json.auditbak, "
     "which nothing ignores, so a git add -A could commit the allowance.",
     "both tests are run by the scheduled lanes, and tokenmeter.STATE and "
     "budget.STATE are module-level paths into the real data directory",
     "run selftest.py and audit_selftest.py and look at whether the real "
     "token_usage.json and budget.json are touched",
     "both tests now work on their own files in a temporary directory, and "
     "the budget backup is written outside the repository",
     "the meter check in selftest.py points tokenmeter.STATE at a temporary "
     "file and restores it; the budget check points budget.STATE at a "
     "temporary file and removes the directory afterwards",
     "the tests pass, and the real data directory is unchanged afterwards",
     ""),

    ("the shop sold thirty-two products as a Full edition for nothing",
     "HIGH", "site", ["site/index.html", "site_js_selftest.py"],
     "VERIFIED_FIXED",
     "groupProducts dropped every catalogue entry marked published:false "
     "before grouping it with its family. For a product whose paid edition is "
     "not on sale yet, the entry that is marked false is the paid one, so the "
     "family was left holding only the free edition and `full` fell back to "
     "it. The card then read 'Full edition' and took the free edition's "
     "price, which is zero. The dialog offered a 'Get the full edition' "
     "button that charged nothing, and the checkout link carried the free "
     "edition's slug because it read item.base_slug, a property groupProducts "
     "never set. On the live site that was thirty-two of the thirty-four "
     "products; only the two that are actually on sale were right.",
     "running the live page's own groupProducts and render against the live "
     "apps.json gave 34 cards, 32 of them labelled 'Full edition' and priced "
     "$0.00, with the title still carrying the '(Basic)' suffix",
     "load the page and read what the cards say",
     "groupProducts keeps both editions and records whether the paid one is "
     "on sale. A product that is not for sale yet is shown as the free "
     "edition it actually is, at its real price, and the dialog offers the "
     "free download and says the paid edition is still being prepared.",
     "site_js_selftest.py checks the grouping in a real browser: a product "
     "with an unsold paid edition is still listed, is not treated as on "
     "sale, and shows the free edition",
     "the old grouping fails all three of the new checks; the new one "
     "renders 34 cards of which 0 claim to be a Full edition at a free "
     "price",
     ""),

    ("a paid app did nothing at all, on the live site",
     "HIGH", "app", ["site/apps/chess-board-basic/index.html",
                     "make_app.py", "tier_gate_selftest.py"],
     "VERIFIED_FIXED",
     "One stray brace in the script block that had been appended to the "
     "chess-board app made the whole file fail to parse, so the app showed "
     "no board, no buttons and no error the visitor could see. It was in the "
     "catalogue that whole time. The validator that refuses a broken app "
     "could not see it, because it could not read a template literal: it "
     "reported eleven perfectly good apps as unparseable instead.",
     "loading the file in a real browser gave 'SyntaxError: missing ) after "
     "argument list' and an empty page, in both the free and the paid "
     "edition",
     "load the app in a browser and look for a board",
     "the stray brace is gone, the validator reads template literals "
     "properly, and tier_gate_selftest.py checks that every app's script "
     "parses",
     "the validator reports the broken file as 'a } closes the wrong "
     "bracket' and none of the thirty-four apps as unparseable; the "
     "selftest fails when the brace is put back",
     "the app now renders its 64 squares in both editions, and the free one "
     "has no export control while the paid one does",
     ""),

    ("the paid features were not gated, or were gated the wrong way round",
     "HIGH", "app", ["site/apps/", "tier_gate_selftest.py"],
     "VERIFIED_FIXED",
     "Ten apps had a paid feature that the free edition could use, a paid "
     "feature the paid edition could not use, or a limit that was never "
     "applied. The chess-board export control was created only in the free "
     "edition, because the gate asked whether the limit was unlimited. The "
     "split-bill import button was hidden in both editions, because LIM "
     "never defined the key it asked for. The dev-converter data section was "
     "never shown. The regex-tester limit check compared !TIER with 'full', "
     "which can never be true. Nine apps offered import with no cap, so the "
     "free edition could import more than the limit it advertises. Two apps "
     "declared a limit they never used, so the limit was not a limit.",
     "checked in a real browser: the free edition of dev-converter has no "
     "data section, the split-bill import button is hidden with the paid "
     "edition, and speed-typing-test never applies its limit of three",
     "look at each app's gate in the free edition and the paid one",
     "each gate now asks whether the capability exists rather than whether "
     "the limit is unlimited, every limit key LIM uses is defined, and every "
     "import is capped at the edition's limit",
     "tier_gate_selftest.py checks that no tier comparison can never be "
     "true, that every LIM key used is defined, and that no feature is "
     "gated on the limit instead of the capability",
     "re-introducing the broken comparison, the undefined key and the wrong "
     "gate each makes the selftest fail",
     ""),

    ("the command that puts a product on the store also put it on the free "
     "edition",
     "MEDIUM", "catalogue", ["set_itch_url.py", "itchurl_selftest.py"],
     "VERIFIED_FIXED",
     "set_itch_url.set_url() wrote the store URL onto both editions of a "
     "product. The free edition is a download from this site and has never "
     "been uploaded to itch.io, so a store URL on it is a claim that is not "
     "true, and the site then offers a buy button for something that is "
     "free. set_all() and itch_publish.record() both strip it from the free "
     "tier, and the release instructions tell the operator to run this "
     "command, so running them as written produced exactly the state the "
     "audit had closed.",
     "the docstring of set_all() says the free editions are deliberately not "
     "given a store URL, and set_url() did the opposite",
     "run set_itch_url.py with a product and look at both of its entries",
     "set_url() clears the store URL from the free edition and sets it on "
     "the paid one, which is what the other two writers do",
     "itchurl_selftest.py checks that no free edition in the catalogue "
     "carries a store URL, and that the command itself does not put one "
     "there",
     "the check fails when the guard is removed from set_url()",
     ""),

    ("one environment variable put a buy button on every free product",
     "MEDIUM", "catalogue", ["pricing.py", "itchurl_selftest.py"],
     "VERIFIED_FIXED",
     "pricing.py filled in every catalogue entry without an itch_url from "
     "the ITCH_PAGE_URL environment variable, including the free editions. "
     "The comment above it says there is no fallback and that an empty value "
     "means 'not for sale yet', but the line was still there. The test that "
     "guards this could not see it, because it looks for a literal URL and "
     "this is a value read at run time, so setting the variable put a store "
     "URL on all thirty-four free editions at once.",
     "the comment and the code disagreed, which is how it survived the audit "
     "that removed the hardcoded version of the same thing",
     "set ITCH_PAGE_URL and run pricing.py",
     "the fallback is only used for a paid edition, and only when the value "
     "is a real product page and not the account's front page",
     "itchurl_selftest.py reads the syntax tree and fails if any module "
     "fills itch_url from the environment",
     "the check fails when the environment read is put back",
     ""),

    ("the tool that brings a dead product back on sale could not",
     "MEDIUM", "tooling", ["rebuild_paid.py", "paidbuild_selftest.py"],
     "VERIFIED_FIXED",
     "rebuild_paid.py existed to reconstruct a product whose paid build is "
     "missing and put it back on sale. It called build_exe.main(), and "
     "build_exe has make_ico() and build_app() and no main(), so it died "
     "with an AttributeError after it had already written the product out. "
     "It also compared the slug against the installer's file name, and the "
     "installer is named after the product's title, so it refused the "
     "correct installer for every product. And it handed butler the store's "
     "URL where butler wants the project's slug, so the target could not "
     "have worked even if the build had.",
     "build_exe.main() does not exist; 'password-manager' would be "
     "'Offline password manager-Setup.exe' and the slug is not a substring "
     "of the file name once the dashes are removed",
     "run rebuild_paid.py for a product and watch it fail",
     "it builds the installer the way the Friday job does, compares the "
     "installer by slug or title the way the publisher does, and gives "
     "butler the project slug",
     "paidbuild_selftest.py checks all three, and the full path was run: the "
     "installer built, was verified as this product's, and the upload was "
     "refused because there was no itch.io user",
     "removing any one of the three makes the selftest fail",
     ""),

    ("the free edition's folder was named twice over",
     "MEDIUM", "tooling", ["make_app.py", "paidbuild_selftest.py"],
     "VERIFIED_FIXED",
     "make_app.main() passed an already-suffixed slug to write_app, which "
     "appends '-basic' itself, so the free edition was written to "
     "'<slug>-basic-basic'. The published copy the catalogue links to "
     "stayed stale, a duplicated slug was published to GitHub Pages, and "
     "the release gate refused the build. The other two callers already "
     "passed the plain slug for exactly this reason.",
     "stage_app.py and verify_app.py both carry a comment saying the suffix "
     "is added by write_app, and main() did the opposite",
     "call write_app with a suffixed slug and look at the folder name",
     "main() passes the plain slug, and write_app accepts either form and "
     "adds the suffix once",
     "paidbuild_selftest.py writes both editions into a temporary directory "
     "and checks that both are called '<slug>-basic'",
     "removing the guard from write_app makes the selftest fail",
     ""),

    ("the command that puts a product on sale proved it with another "
     "product's build",
     "HIGH", "store", ["publish_paid.py", "itch_publish.py"],
     "VERIFIED_FIXED",
     "publish_paid.py decided a product was on sale by looking for the words "
     "download, Buy or purchase in the body of the itch.io page. The store is "
     "ONE project holding every product, and that page says 'download' for "
     "every slug forever, so the check passed for a product whose build had "
     "never been uploaded. The catalogue was then marked published and the "
     "site offered a buy button for a product with nothing behind it. The "
     "publisher had the right check all along, build_is_listed, which looks "
     "for this product's own installer by name.",
     "the live store page contains 'download' and 'purchase' for every "
     "product, and 'Markdown editor-Setup.exe' is not listed on it at all, "
     "so the old check would have published a product with no build",
     "run publish_paid.py for a product that was never uploaded",
     "the product's own installer has to be listed on the page, by name, and "
     "the price rule is checked before the catalogue is written",
     "itchpublish_selftest.py and itchurl_selftest.py cover the catalogue "
     "rules; the check is in the publisher, which is the one place that "
     "decides",
     "a product with no build of its own on the page is refused, and the "
     "refusal says which names it looked for",
     ""),

    ("the release gate let a paid build through",
     "HIGH", "pipeline", ["check_exposure.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "check_exposure.py is the last thing between the paid product and the "
     "public site, and it had three holes. It looked for a flat index.html, "
     "but the paid edition is paid/<slug>/app/index.html, so a copy of the "
     "paid folder into site/apps/ was invisible to it. It read the folder "
     "check's exemption from data/candidate.json and allowed the plain paid "
     "slug with it, so the folder holding the paid build was accepted as a "
     "known basic edition. And its list of development files had no binary "
     "extensions, so the installer, which is the paid product, was not on "
     "it.",
     "five leaks were reproduced against the real gate: a paid build at "
     "apps/<slug>/app/, the same with a candidate naming that slug, a flat "
     "paid build, a paid edition inside the basic folder, and an installer "
     "under site/downloads. The gate printed 'ok' for all five.",
     "put a paid build in the published folder and run the gate",
     "the gate looks for the paid build in the app folder as well, reads the "
     "tier constant in the file, only exempts the free edition's folder "
     "name, and refuses any binary under the published site",
     "audit_selftest.py builds a public site with each leak in it and asks "
     "the gate about it",
     "all five leaks are now caught; the old gate passed all five",
     ""),

    ("a version with two numbers was silently thrown away",
     "MEDIUM", "state", ["update_state.py", "update_selftest.py"],
     "VERIFIED_FIXED",
     "parse() returned (1, 0, 0) for any version with fewer than three "
     "parts, so `update_state.py --set 2.0` stored version 1.0.0, logged "
     "'version 1.0.0' and exited 0. The release state moved backwards and "
     "the run reported success.",
     "parse('2.0') gave (1, 0, 0), and the same fallback meant the "
     "installed version of any app was normalised to 1.0.0",
     "run update_state.py --set 2.0 and read the state file",
     "a version with fewer than three parts is padded with zeros, and only a "
     "version with no digits in it is the unknown 1.0.0",
     "update_selftest.py checks the padding, the empty case and a bump on a "
     "short version",
     "restoring the old parse makes the new checks fail",
     ""),

    ("an installed app could never be told it was out of date",
     "MEDIUM", "app", ["app_update.py", "update_state.py"],
     "VERIFIED_FIXED",
     "installed_version() read app.json from one level too high for the "
     "launcher, which passes the app's root while the file is in the app "
     "folder inside it, so the installed version was always the fallback of "
     "1.0.0. The banner then said '1.0.0 is installed' for a copy that was "
     "already current and could never stop. And latest() read a local "
     "site/update.json, which is gitignored and was never in the bundle, so "
     "for a customer it always returned nothing and the banner could never "
     "appear at all. The per-app version map was kept in the state file and "
     "never published, so a product could not learn its own version even in "
     "principle.",
     "the launcher reads BASE/app/app.json and the check read BASE/app.json, "
     "and no build step put an app.json in the bundle at all",
     "run app_update.py against an installed layout",
     "both places the file can be are tried, the published file is fetched "
     "when there is no local copy, and the per-app versions are published",
     "update_selftest.py checks that the installed version is read from "
     "either layout",
     "the old function returns 1.0.0 for the layout the launcher uses",
     ""),

    ("a product's title and price came from whichever edition was listed "
     "first",
     "MEDIUM", "store", ["itch_publish.py"],
     "VERIFIED_FIXED",
     "_describe() took the first catalogue entry with a matching slug and "
     "stopped there, so a family written basic-first described the product "
     "as the free edition, with its price of zero, and the caller then "
     "quietly substituted the default price of $3.00. The site advertised "
     "the catalogue price and itch.io charged the substituted one. It also "
     "asked for entry['full'], a nested shape the catalogue does not have, "
     "so the branch it took always found nothing.",
     "_describe on a synthetic basic-first family gave ('thing', 0.0), and "
     "on a full-first family gave the right answer",
     "describe a product whose family is listed basic-first",
     "the paid entry is found whichever order the family is in, the same "
     "way the rest of the module does it",
     "the publisher's own tests cover the catalogue rules",
     "a basic-first family now gives the same answer as a full-first one",
     ""),

    ("verifying an app destroyed the paid build that was already there",
     "MEDIUM", "tooling", ["make_app.py", "verify_app.py"],
     "VERIFIED_FIXED",
     "write_app emptied the paid folder before writing to it, and the paid "
     "folder holds the installer, which took forty minutes to build. "
     "Verifying an app on a machine that already had the paid build "
     "destroyed that build, silently, because paid/ is gitignored and "
     "nothing showed it in a diff. It also meant the verify job's artifact "
     "could never carry the installer, so the installer job always rebuilt "
     "it from nothing.",
     "write_app did rmtree(PAID_DIR / slug) for the full tier",
     "run verify_app.py with a paid build present and look at the folder",
     "only the two files write_app owns are replaced, and the rest of the "
     "folder is left alone",
     "the layout checks in paidbuild_selftest.py cover the folder naming",
     "the paid folder and its installer survive a rewrite",
     ""),

    ("a rejected candidate stayed staged for ever",
     "LOW", "tooling", ["verify_app.py"],
     "VERIFIED_FIXED",
     "verify_app.py removed data/candidate.json only when the app passed. A "
     "rejected candidate stayed in a tracked file, so the next run verified "
     "the same rejected app again, and it kept widening the release gate's "
     "exemption for that folder name for as long as it existed.",
     "the unlink was on the success path only",
     "reject an app and look for the candidate file",
     "the candidate is cleared whether the app passed or not",
     "the file is gone either way",
     "putting the unlink back leaves it behind on the failure path",
     ""),

    ("the paid edition never said what the customer was paying for",
     "MEDIUM", "catalogue", ["make_app.py", "stage_app.py",
                              "tier_gate_selftest.py"],
     "VERIFIED_FIXED",
     "The generator's raw path asks the model for the app file and nothing "
     "else, and the three things that describe the product to a customer, "
     "its name, the list of what the paid edition adds and the two "
     "descriptions, were set to empty strings. Every product was published "
     "with the same description as its own free edition and an empty "
     "differences list, so the shop asked for three dollars and never said "
     "what the three dollars were for. The answer was in the app's own "
     "limit table, which nobody read.",
     "the live catalogue has an identical blurb and an empty differences "
     "list for both editions of all thirty-four products, and the buy dialog "
     "shows that blurb",
     "look at what the paid option says in the buy dialog",
     "the paid features are read out of the app's own limit table, which "
     "costs no model call, and a feature is only claimed if the app is seen "
     "to have it, so nothing is promised that is not there",
     "tier_gate_selftest.py checks that every product's paid edition has "
     "something the free one does not",
     "all thirty-four products now list real differences, and a limit key "
     "with no matching control is not claimed",
     ""),

    ("the bot cannot read the server's channels",
     "MEDIUM", "discord", ["check_connections.py"],
     "BLOCKED",
     "The Discord guild routes answer 403 for this bot: the member record, "
     "the channel list and the role list all return 'internal network "
     "error' with code 40333, which is Discord's Unknown Member. The token "
     "itself is good, it is in the guild, and the webhook posts fine, so "
     "this is on Discord's side of the connection rather than in the code. "
     "It needs a person with access to the server.",
     "run 39674190056: 'discord bot - Slingshot Tools#2486' and 'discord "
     "server - Slingshot Tools' both PASS, the webhook PASSES, and only the "
     "guild-scoped routes answer 403 with code 40333",
     "run check-connections.yml and read the discord channels row",
     "not a code change. A person with access to the server should check "
     "the bot's permissions and re-invite it if the membership record is "
     "stale. The posting path is unaffected, because the webhook is tried "
     "first and it works.",
     "check_connections.py already reports what Discord actually returned, "
     "so the failure is actionable as it stands",
     "not verified, because it cannot be fixed from here and the fix needs "
     "access to the Discord server. It may also be a Discord-side outage, "
     "in which case it clears itself. Until then the connections lane "
     "stays red on this one row, and only on this one row.",
     ""),

    ("the YouTube refresh token was revoked",
     "MEDIUM", "youtube", ["check_connections.py", "shorts_auth.py"],
     "BLOCKED",
     "The stored YouTube refresh token no longer exchanges for an access "
     "token, which is what happens when a Google account revokes the "
     "authorisation, when the app is in testing mode and the refresh token "
     "has expired, or when the consent screen is changed. Re-authorising is "
     "an interactive browser step with a Google account, so it cannot be "
     "done from here.",
     "run 39674190056: 'FAIL youtube - the refresh token was revoked or "
     "expired', and the check itself says 'run python shorts_auth.py again'",
     "run check-connections.yml and read the youtube row",
     "not a code change. A person has to run python shorts_auth.py and "
     "complete the Google consent screen, then put the new refresh token in "
     "the YOUTUBE_REFRESH_TOKEN secret.",
     "check_connections.py says exactly what to do, so the failure is "
     "actionable as it stands",
     "not verified, because re-authorising needs a browser and a Google "
     "account. Nothing in the shop depends on it. The lanes that publish to "
     "YouTube would fail on their own, and they are not part of a release.",
     ""),

    ("the guard that protects the site could not see anything",
     "CRITICAL", "pipeline", ["weekly_guard.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "changed_files() asked git for the diff between HEAD and HEAD with the "
     "three-dot form, which is a merge-base comparison, so the merge base was "
     "that commit and the diff was empty with exit code 0. The function "
     "always returned an empty list, the fallback that would have caught it "
     "was unreachable, and every gate built on it reported '0 changed "
     "file(s), none protected' while a protected workflow sat modified in the "
     "tree. Six workflows run that gate, and self_upgrade.py asks the same "
     "question after a patch.",
     "with a protected workflow modified in the tree, git reported the file "
     "as changed, changed_files() returned an empty list, violations() "
     "returned nothing and guard() returned 0",
     "modify a protected file and run python weekly_guard.py check",
     "the working tree against HEAD, and anything staged, is what is asked "
     "about, and a job that commits its own change asks before it commits",
     "audit_selftest.py modifies a protected workflow, asks the guard, and "
     "checks that it sees the file, calls it a violation and refuses",
     "putting the three-dot form back makes all three checks fail",
     ""),

    ("the repair lane could rewrite the scripts the guard protects",
     "CRITICAL", "pipeline", ["selfheal.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "The repair lane's allow-list included build_exe.py and "
     "build_installer_app.py, and both are in the guard's list of the "
     "scripts that make the site work, so the lane could rewrite the very "
     "files the guard exists to protect and the gate would not have said so, "
     "because the gate was not looking. The lane also only compiled the "
     "patched file and stopped, though its own docstring said a patch must "
     "survive a test run, so a whole-file rewrite that broke the build but "
     "still parsed was committed to main and pushed. It also had itself in "
     "the allow-list.",
     "the two files were in both lists, and no test ran anywhere in the file",
     "ask the repair lane to patch a protected script and see what it does",
     "a protected file is never repairable, the whole suite has to pass with "
     "the patch in place, and the guard has the last word before anything is "
     "committed",
     "audit_selftest.py asks the repair lane about a protected script and "
     "checks that it is refused",
     "removing the refusal makes the check fail",
     ""),

    ("a credential held as a dictionary value was written to the public log",
     "HIGH", "audit", ["auditlog.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "The scrubber needed the name and the value side by side in one string, "
     "and in a dictionary they are two separate strings, so a credential "
     "held as a value was written to the log as it was. The log is a tracked "
     "file in a public repository, and the natural place for a credential is "
     "the evidence dictionary every event carries. The test that claimed to "
     "cover it passed only because its nested value happened to match a "
     "shape rule.",
     "scrub({'password': 'hunter2000'}) returned the password unchanged, and "
     "the same for an itch.io session cookie, a Discord bot token and an "
     "authorization header",
     "scrub a dictionary holding a credential",
     "a key that names a credential means the value is one, however ordinary "
     "the value looks, and the value is replaced",
     "audit_selftest.py checks that a password, a session cookie, a Discord "
     "token, an authorization header and a nested key are all replaced, and "
     "that an ordinary word is not",
     "removing the replacement makes the checks fail",
     ""),

    ("rotating the audit log threw the history away",
     "MEDIUM", "audit", ["auditlog.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "The rotation copied the newest file to .1 and then deleted it, which "
     "is the opposite of what its own docstring says it does, and read() only "
     "ever read the newest file, so past the size limit the whole trail "
     "became empty and the report that depends on it reported nothing.",
     "with the size limit lowered, the log file did not exist afterwards and "
     "read() returned no events",
     "write more than the size limit worth of events and read them back",
     "the newest file is emptied rather than deleted, and the rotated files "
     "are read too, oldest first, so the trail is continuous",
     "audit_selftest.py writes past the limit and checks the file is still "
     "there and there is still something to read",
     "deleting the file instead of emptying it makes the check fail",
     ""),

    ("the price engine reset the whole shop to the starting price every week",
     "HIGH", "pricing", ["pricing.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "The engine's state file is untracked, so on a fresh runner it does not "
     "exist and every product was defaulted to the starting price, which "
     "reset the whole shop to three dollars every Friday, reverted any price "
     "that had been set by hand, and left the engine unable to learn from a "
     "run because it started from nothing every time. The hold path also "
     "skipped the clamp, so a stored price outside the rule was published "
     "and then refused by the command that lists a product for sale, and a "
     "product that is held could never move.",
     "the state file is in .gitignore, the Friday lane runs pricing.py on a "
     "fresh checkout, and the catalogue's own price was never read",
     "run pricing.py against a catalogue with a price of five dollars and no "
     "state file",
     "the catalogue is the price of record, a hold is clamped like a move is, "
     "and the catalogue decides the tier rather than the engine's note",
     "audit_selftest.py runs the engine against a catalogue with a price of "
     "five dollars and one outside the rule, and checks both",
     "defaulting to the starting price again makes the checks fail",
     ""),

    ("a corrupt budget crashed the job instead of refusing it",
     "MEDIUM", "budget", ["budget.py", "audit_selftest.py"],
     "VERIFIED_FIXED",
     "The state file's shape was only checked at the top level, so a file "
     "holding a months list instead of a table, or a month that was a number "
     "instead of a record, or an hour count that was a word, made spent() "
     "raise out of check(). The module promises that an unreadable budget "
     "refuses the job. The hours and the broken-ness also came from two "
     "separate reads of the same file, so a failed read and a successful one "
     "could be combined, and the job was approved on zeros from the failed "
     "one.",
     "a state file holding {\"months\": []} made check() raise an "
     "AttributeError, and one holding a non-numeric hour count raised a "
     "ValueError",
     "put each of those shapes in data/budget.json and run budget.py check",
     "the shape is checked before it is used, one read answers both "
     "questions, and the temporary file has a unique name so two writers "
     "cannot swap each other's file into place",
     "audit_selftest.py covers the shape of the state file",
     "putting the old check back makes a corrupt file crash again",
     ""),

    ("the daily lane believed a corrupt budget was a full month",
     "HIGH", "budget", ["improve_daily.py"],
     "VERIFIED_FIXED",
     "The daily lane asked budget.remaining() for the hours left, and "
     "remaining() reads a corrupt state as zero spent, so it answered with a "
     "whole month while the truth was unknown. The command that answers this "
     "question properly, budget.check(), refuses when the hours cannot be "
     "read, and the lane did not use it.",
     "with a corrupt budget file, broken() was true, check() returned 1 and "
     "remaining() returned 30.0",
     "corrupt data/budget.json and run the daily lane",
     "the lane asks budget.check(), which refuses when the hours cannot be "
     "read",
     "the refusal is the answer, not a number",
     "the daily lane asked for a number again",
     ""),

    ("the daily lane recorded changes that never happened",
     "HIGH", "improvement", ["improve_daily.py"],
     "VERIFIED_FIXED",
     "The lane decided whether anything changed by comparing the bytes of "
     "the improver's state file before and after. The improver rewrites that "
     "file on every path, including the model proposing nothing and the "
     "patch being rejected and rolled back, so the bytes always differed "
     "and the lane always said a change had been made. It recorded changes "
     "that never happened and started the cooldown on days when nothing was "
     "done, so the promise that doing nothing is a success never held.",
     "the improver rewrites its state file on every path, with a fresh "
     "timestamp, so the comparison was always true",
     "run the lane and look at whether it says a change was made when the "
     "model declined",
     "the lane reads what the improver recorded, and a change means a patch "
     "was kept",
     "the lane asks for the recorded outcome rather than the file bytes",
     "comparing the bytes again makes every run claim a change",
     ""),

    ("the daily lane threw away the patch it had tested",
     "HIGH", "improvement", [".github/workflows/daily-improve.yml"],
     "VERIFIED_FIXED",
     "The lane committed only the four data files, so the improved "
     "generator was written into the working tree, tested there and then "
     "thrown away with the runner, while the note saying it had been tried "
     "was committed. The memory of the attempt survived and the attempt did "
     "not, so the same patch was proposed every day and never kept.",
     "the commit step staged four data files and nothing else, and the "
     "patched file was never staged",
     "read the commit step of the daily lane",
     "the patch is staged with the notes, so a patch that passed the suite "
     "is kept",
     "the lane's own commit step",
     "removing the staging of the changed files leaves the patch on the "
     "runner",
     ""),

    ("the private-data guard was defeated by a shallow checkout",
     "MEDIUM", "hygiene", ["check_repo_hygiene.py",
                            ".github/workflows/daily-improve.yml"],
     "VERIFIED_FIXED",
     "The check that looks for a credential which was committed and then "
     "deleted reads the whole log, and the runners checked out one commit by "
     "default, so in CI it never saw more than the latest commit while it "
     "did see the history on a full clone. The lanes that run it were given "
     "the whole history. The scan also failed on a full clone over a test "
     "fixture that had been removed from the working tree months earlier, "
     "so the gate was red for everybody and meaningless.",
     "the runners use the default shallow checkout, and a full clone found a "
     "token-shaped test fixture in the history that is not in the working "
     "tree",
     "run check_repo_hygiene.py on a full clone and on a shallow one",
     "the lanes fetch the whole history, and an obvious placeholder is not "
     "treated as a leaked secret",
     "check_repo_hygiene.py is run by five lanes",
     "the placeholder is still treated as a secret",
     ""),

    ("the repair lane could never run, because there was nothing to read",
     "MEDIUM", "pipeline", ["selfheal.py", ".github/workflows/friday-build.yml"],
     "VERIFIED_FIXED",
     "The repair lane was handed the failure log to diagnose, and it looked "
     "for it in a directory that nothing in this repository ever wrote, and "
     "for an artifact that no workflow ever uploaded. So it found nothing on "
     "every run, said so and gave up before it asked anything, and the "
     "repair-after-a-failed-generation capability had never existed.",
     "there is no selfheal/ directory, nothing writes the two files it "
     "looked for, and the only artifacts uploaded are named paid-build and "
     "slingshot-installer",
     "run the repair lane and see that it finds no log",
     "the generate job keeps its output as an artifact, the workflow "
     "downloads it, and the repair lane looks in the places the log can "
     "land",
     "the lane's own log handling",
     "removing the new places makes the lane find nothing again",
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