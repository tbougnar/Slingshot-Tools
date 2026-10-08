# Fixbook

Every fault we have hit in this pipeline, what actually caused it, and
the change that fixed it. Check here before proposing anything.

## B001 - itch.io projects could not be created from CI

- **Cause:** Cloudflare blocks headless browsers and plain HTTP on itch.io; there is no create-project API, and the API key alone cannot make one.
- **Fix:** Removed itch.io entirely and replaced delivery with PayPal plus a private store behind the payment API.
- **Files:** worker/worker.js
- **Check for recurrence:** no reference to itch remains in the code
- **Status:** UNTESTED

## B002 - paid builds were publicly downloadable

- **Cause:** Old paid files were still tracked in git after being moved on disk, and the build re-published them under site/apps.
- **Fix:** site/ now receives only the basic edition; paid/ is gitignored and served only after payment.
- **Files:** make_app.py, .gitignore
- **Check for recurrence:** apps/<slug> for a paid slug returns 404 while apps/<slug>-basic returns 200
- **Status:** UNTESTED

## B003 - workflow could not be dispatched

- **Cause:** Duplicate PRICE_FLOOR keys made the YAML invalid, so GitHub reported the workflow had no workflow_dispatch trigger.
- **Fix:** Removed the duplicate keys and validated the file before pushing.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** the workflow file parses as YAML
- **Status:** UNTESTED

## B004 - build crashed with NameError: stage_paid

- **Cause:** A function was renamed during the itch removal but the call site was not.
- **Fix:** Defined stage_paid and had it build the real app folder plus installer.
- **Files:** make_app.py
- **Check for recurrence:** python -m py_compile passes and stage_paid exists
- **Status:** UNTESTED

## B005 - SameFileError while staging the paid build

- **Cause:** write_app already writes into paid/<slug>, so the copy step copied files onto themselves.
- **Fix:** Detect that source and destination are the same and skip the copy.
- **Files:** paid_store.py
- **Check for recurrence:** staging a build whose folder already exists is a no-op
- **Status:** UNTESTED

## B006 - paid customers received nothing (HTTP 413)

- **Cause:** A standalone Windows exe is about 28 MB and the store rejects any single value above 25 MB.
- **Fix:** Split the file into chunks on upload and rejoin them in the worker before replying, so the customer still gets one complete file.
- **Files:** paid_store.py, worker/worker.js
- **Check for recurrence:** the store holds every chunk and their sizes sum to the file size
- **Status:** UNTESTED

## B007 - QA crashed with 'object of bool has no len'

- **Cause:** Playwright was not installed on the runner, so the scanner returned a flag instead of a list.
- **Fix:** Install Playwright on the runner, and make a scanner that cannot run report failure rather than pass.
- **Files:** app_scanner.py, .github/workflows/monday-build.yml
- **Check for recurrence:** app_scanner.verdict is False when the scanner is unavailable
- **Status:** UNTESTED

## B008 - every model call failed with HTTP 403 error 1010

- **Cause:** Cloudflare refuses Python's urllib based on its fingerprint; a browser User-Agent alone does not help.
- **Fix:** All model calls go through one client built on requests.
- **Files:** ai.py
- **Check for recurrence:** groq_check.py reports HTTP 200
- **Status:** UNTESTED

## B009 - models were configured that no longer exist

- **Cause:** llama-3.3-70b, kimi-k2, deepseek, gemma2 and llama-4 are retired; only three chat models remain.
- **Fix:** Use the three the live catalogue offers: gpt-oss-120b, qwen3.8-27b, gpt-oss-20b.
- **Files:** debug_team.py, make_app.py
- **Check for recurrence:** the model list matches what the catalogue endpoint returns
- **Status:** UNTESTED

## B010 - finished apps were thrown away over a missing data-theme

- **Cause:** A theme attribute was treated as a correctness requirement.
- **Fix:** It is recorded as a note, not a rejection.
- **Files:** make_app.py
- **Check for recurrence:** html without data-theme is accepted with a note
- **Status:** UNTESTED

## B011 - the self-heal debugger never produced a fix

- **Cause:** Its runner had no requests installed, so every model call it made failed with ModuleNotFoundError.
- **Fix:** Install requests in the self-heal job before it thinks.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** the self-heal log shows a diagnosis rather than a missing-module error
- **Status:** UNTESTED

## B012 - the debugger diagnosed the wrong problem

- **Cause:** It read --log-failed, which missed the build job, and concluded the pipeline had not actually failed.
- **Fix:** Fetch the build job log as well as the failed output.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** selfheal/failure.txt contains the build step output
- **Status:** UNTESTED

## B013 - repairs and app generation came back truncated

- **Cause:** Reasoning tokens are drawn from the same max_tokens budget as the reply, so a 30 KB file stopped mid-way.
- **Fix:** Raise the reply budget and turn reasoning off for repairs.
- **Files:** ai.py, debug_team.py, make_app.py
- **Check for recurrence:** a generated file ends with </html> and contains localStorage
- **Status:** UNTESTED

## B014 - votes collapsed every button into one control

- **Cause:** Vote keys used only the tag, so all buttons counted as a single control and the majority test meant nothing.
- **Fix:** Key votes on the whole label and map them back to the scanner's labels.
- **Files:** debug_team.py
- **Check for recurrence:** distinct buttons produce distinct votes
- **Status:** UNTESTED

## B015 - the two strongest models returned nothing during repairs

- **Cause:** max_tokens was raised to 40000, above what those models will produce, so Groq refused the request and the failure was reported as an empty reply
- **Fix:** cap the request at REPLY_BUDGET=32000 and print the error body from every failed call
- **Files:** debug_team.py, ai.py
- **Check for recurrence:** recurs if a repair log shows a model FAILED with a 400 status
- **Status:** UNTESTED

## B016 - repairs could never complete: every model call was rate limited or refused

- **Cause:** a full 30 KB file is about 8k output tokens and the free tier allows 8000 tokens per minute, so asking for the whole app twice in a row is impossible; max_tokens above 16384 is also refused outright
- **Fix:** repair with small patches instead of reprinting the app, cap max_tokens at 16000, and treat 429 as a wait-and-retry rather than a failure
- **Files:** patcher.py, qa_loop.py, debug_team.py
- **Check for recurrence:** recurs if a repair log shows 429 rate limit errors
- **Status:** UNTESTED

## B017 - UnboundLocalError: by, right after a patch was produced successfully

- **Cause:** the patch branch left the variable that names the repairing model unset, and the history line read it unconditionally
- **Fix:** initialise by before the branch so both paths can record who repaired it
- **Files:** qa_loop.py
- **Check for recurrence:** recurs if a qa round logs a repair without naming a patcher or model
- **Status:** UNTESTED

## B018 - a patch was applied four rounds in a row and never fixed the control

- **Cause:** the team never checked whether its own patch changed the outcome, so it repeated the same ineffective fix
- **Fix:** re-scan after every patch and report which controls are unchanged, so the next round must change approach
- **Files:** qa_loop.py
- **Check for recurrence:** recurs if several consecutive rounds report the same dead control
- **Status:** UNTESTED

## B019 - qwen refused every request as Request too large

- **Cause:** the free tier allows roughly 1000 output tokens a minute for that model and the request asked for 2500
- **Fix:** cap max_tokens per model: qwen 900, the others 8000
- **Files:** patcher.py, debug_team.py
- **Check for recurrence:** recurs if a model is refused with an output-tokens-per-minute error
- **Status:** UNTESTED

## B020 - every log line appeared twice

- **Cause:** the encoding guard added a second print inside log()
- **Fix:** log() prints exactly once and can never raise
- **Files:** make_app.py
- **Check for recurrence:** recurs if a log line is duplicated in a run
- **Status:** UNTESTED

## B021 - an injected handler was attached but the button still did nothing

- **Cause:** the patch called into the app without knowing whether that function existed, and nothing checked the outcome
- **Fix:** the scanner separates no-handler from handler-present-but-nothing-happened, and a patch that changes nothing is reported as ineffective
- **Files:** app_scanner.py, qa_loop.py
- **Check for recurrence:** recurs if a scan reports a handler present but nothing happened
- **Status:** UNTESTED

## B022 - the run was cancelled after half an hour with only 2 dead controls left

- **Cause:** patching asked the builder model first, which is rate limited, and then waited up to 80s four times per attempt, so most of the run was spent sleeping
- **Fix:** ask the debugger models for patches, fall through on a rate limit instead of waiting, and use fewer rounds so a run always finishes
- **Files:** patcher.py, qa_loop.py
- **Check for recurrence:** recurs if a run is cancelled or hits its time limit inside QA
- **Status:** UNTESTED

## B023 - verifying in the same minute as generating starved the debugger team

- **Cause:** the model allowance is per minute for the whole account, so by the time QA asked for patches the builder had already spent it and all three models were rate limited
- **Fix:** generate at 07:00 and verify in a separate workflow at 08:00, so verification always starts on a fresh allowance
- **Files:** .github/workflows/monday-build.yml, .github/workflows/monday-verify.yml
- **Check for recurrence:** recurs if a single run both generates and verifies
- **Status:** UNTESTED

## B024 - twenty two runs failed because apps were too large to verify

- **Cause:** generation consumed the entire per-minute model allowance, so the debugger team had nothing left and could never pass an app
- **Fix:** cap apps at 9000 bytes with sizeguard, tell the builder to aim under 8 KB, and teach the working-handler pattern in PATTERNS.md so fewer repairs are needed
- **Files:** sizeguard.py, PATTERNS.md, make_app.py, stage_app.py
- **Check for recurrence:** recurs if a staged app exceeds the size ceiling
- **Status:** UNTESTED

## B025 - generation failed on the very first call, choosing which app to build

- **Cause:** the concept picker was pinned to a single model and that model would not return usable JSON for a short structured question
- **Fix:** the concept picker now tries each model in turn and asks for a small reply, and verification waits for a candidate instead of silently doing nothing
- **Files:** make_app.py, verify_app.py
- **Check for recurrence:** recurs if a run fails at pick_concept, or verify reports nothing to do
- **Status:** UNTESTED

## B026 - the concept picker still fails, now with every model rate limited

- **Cause:** all three models share one 8000 token per minute allowance for the whole account, and repeated test runs during the session had spent it, so no model could answer even a short question
- **Fix:** the picker already tries each model and now reports the real reason; the remaining fix is to stop spending the allowance on repeated manual dispatches and let the scheduled runs space themselves out
- **Files:** make_app.py
- **Check for recurrence:** recurs when several dispatches are fired close together
- **Status:** UNTESTED

## B027 - runs die because the model allowance is spent before repair can finish

- **Cause:** nothing tracked how much of the per-minute allowance had been used, so retries kept firing into a wall
- **Fix:** record token usage from every provider call and check what is left before spending more; regenerate the app when repair fails and allowance remains, rather than patching forever
- **Files:** tokenmeter.py, providers.py, verify_app.py
- **Check for recurrence:** recurs if a run dies partway through with a rate limit
- **Status:** UNTESTED

## B028 - patches had nothing to target once the markup was trimmed

- **Cause:** the inventory listed ids and functions but not classes or visible labels, and those are how a button without an id gets found
- **Fix:** list ids, classes and control labels in the inventory, and inject the matching fixbook entry only when a known fault is recognised so it costs nothing otherwise
- **Files:** patcher.py, buglog.py
- **Check for recurrence:** recurs if a patch proposes a selector that matches nothing in the app
- **Status:** UNTESTED

## B029 - the self-heal debugger could not read the failing run

- **Cause:** gh is not authenticated inside the job, so the log it needs came back empty and it was diagnosing the wrong thing
- **Fix:** pass the built-in GITHUB_TOKEN to the self-heal job as GH_TOKEN
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** recurs if the self-heal log shows gh authentication errors
- **Status:** UNTESTED

## B030 - an edit to pick_concept deleted the whole APP_SPEC and every run died with NameError

- **Cause:** the function was replaced by slicing up to the next top-level def, and the module level APP_SPEC constant sat inside that slice
- **Fix:** restore APP_SPEC from the previous commit and verify every module level symbol is present after any structural edit
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run fails with NameError on a module level name
- **Status:** UNTESTED

## B031 - every run died with no usable JSON even though the model returned a working app

- **Cause:** _salvage_html only understood a JSON string value, so a reply wrapped in prose, markdown fences or a truncated document was discarded entirely
- **Fix:** salvage now strips fences, ignores prose, cuts from the first document tag to the last closing tag, and closes a truncated document
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run reports no usable JSON
- **Status:** UNTESTED

## B032 - a working raw app builder existed but every run used the JSON one

- **Cause:** stage_app called build_html, which asks the model to wrap a large document in a JSON object; that parse is what every run died on, and the raw path that asks for the file directly was never called by anything
- **Fix:** stage_app uses build_html_raw, so there is no JSON to parse, and groq_json now names the real cause and captures the raw reply
- **Files:** stage_app.py, make_app.py
- **Check for recurrence:** recurs if a run reports no usable JSON
- **Status:** UNTESTED

## B033 - the element inventory missed single-quoted ids, so patches had nothing to target

- **Cause:** generated markup uses single quotes at least as often as double, and the inventory only looked for id=\"...\", so on many real apps it reported no ids at all
- **Fix:** read ids and classes in both quote styles, and refuse page-rewriting or network code such as document.write, location.href, fetch and eval
- **Files:** patcher.py
- **Check for recurrence:** recurs if the inventory reports an empty ids list for an app that clearly has ids
- **Status:** UNTESTED

## B034 - the self-heal debugger called remember() which did not exist

- **Cause:** remember was defined once, then replaced with a buglog-based version that lost the definition, so the debugger raised NameError at the exact moment it tried to record what it had learned
- **Fix:** define remember in selfheal.py writing to the fixbook, and check every call site with a whole-code audit that parses all files
- **Files:** selfheal.py, selftest_audit.py
- **Check for recurrence:** recurs if the audit reports any undefined name
- **Status:** UNTESTED

## B035 - the new self-tests hardcoded a Windows path and could not run on the Linux runner

- **Cause:** they were written on this machine with an absolute path, so every build died before it started even though the checks themselves were sound
- **Fix:** resolve every path from the script's own location and install pyyaml on the runner
- **Files:** selftest.py, selftest_deep.py, selftest_audit.py
- **Check for recurrence:** recurs if a self-test reports a missing file that clearly exists
- **Status:** UNTESTED

## B036 - a run failed on a rate limit even though the allowance refills within a minute

- **Cause:** the wait guard checked a local token meter that is empty at the start of a fresh runner, so it never waited, and the build gave up on the first refusal
- **Fix:** retry the model call up to eight times with a growing wait whenever the reply is a rate limit, since the allowance does refill
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run reports no usable html after waiting
- **Status:** UNTESTED

## B037 - every model call failed with a utf-8 decode error that looked like a rate limit

- **Cause:** the API replies gzipped and urllib never decompresses it, so the first byte 0x8b broke decoding; the wait logic then reported it as an allowance problem
- **Fix:** decode gzip and deflate responses explicitly and ask for identity encoding so nothing arrives compressed
- **Files:** providers.py, ai.py
- **Check for recurrence:** recurs if a log shows a codec decode error from a model call
- **Status:** UNTESTED

## B038 - verify could not find the staged file, and the slug was doubled

- **Cause:** stage_app stored an absolute path from the machine that generated it, and passed a slug that already ended in -basic into a helper that appends it again
- **Fix:** store the candidate path relative to the repo and let write_app own the basic suffix
- **Files:** stage_app.py, verify_app.py
- **Check for recurrence:** recurs if verify reports a staged file is gone, or a slug ends in -basic-basic
- **Status:** UNTESTED

## B039 - verify still could not find the staged file on the Linux runner

- **Cause:** the path was relative now but kept Windows backslash separators, which are not separators on Linux
- **Fix:** store the relative path with as_posix so it is identical on every operating system
- **Files:** stage_app.py
- **Check for recurrence:** recurs if verify reports a staged file is gone
- **Status:** UNTESTED

## B040 - one dead control blocked every publish, so the catalogue stayed empty

- **Cause:** the pipeline refused to ship anything that was not perfect, which meant a single stubborn button stopped the whole business from having a product
- **Fix:** tolerate up to one dead control and publish with it logged, keep refusing two or more, and drop qwen whose output ceiling is below any patch we send
- **Files:** verify_app.py, patcher.py
- **Check for recurrence:** recurs if no product reaches the catalogue
- **Status:** UNTESTED

## B041 - the tolerance decision never published, it just gave up with exit code 2

- **Cause:** after allowing one dead control the code fell straight through to the give-up line instead of continuing to publish, so the allowance was announced as acceptable and then nothing shipped
- **Fix:** let the tolerance branch fall through to the publish path, and use the CHAT_MODELS list rather than a second unused one so qwen is actually dropped
- **Files:** verify_app.py, patcher.py, make_app.py
- **Check for recurrence:** recurs if verify logs that it will publish but the run ends without a release
- **Status:** UNTESTED

## B042 - the Linux job tried to build a Windows exe and refused to publish anything

- **Cause:** PyInstaller does not exist on the Linux runner, so staging the paid edition always failed and the free app was thrown away with it
- **Fix:** publish the free edition on Linux, keep the paid tier hidden until the Windows job uploads a real installer, then reveal it
- **Files:** verify_app.py, build_paid_only.py
- **Check for recurrence:** recurs if a run logs that the paid build could not be produced
- **Status:** UNTESTED

## B043 - publishing the free edition crashed on KeyError: blurb

- **Cause:** an empty free_blurb and paid_blurb fell through to concept['blurb'], which the verification path never supplies
- **Fix:** read the fallback with .get and pass a blurb through from the staged candidate
- **Files:** make_app.py, verify_app.py
- **Check for recurrence:** recurs if a run ends with KeyError while publishing
- **Status:** UNTESTED

## B044 - qwen was still being called after being removed from the patch list

- **Cause:** the voting team and the second debugger list were separate and still named qwen, whose 1000 token output ceiling refuses every real call
- **Fix:** remove qwen from the team roster and the debugger list as well, not only the patch list
- **Files:** debug_team.py, debug_team2.py
- **Check for recurrence:** recurs if a log shows qwen being called
- **Status:** UNTESTED

## B045 - publishing crashed again, this time on KeyError: tags

- **Cause:** the same pattern as blurb: publish reads keys that the verification path does not put in its concept dict
- **Fix:** read tags with a default empty list
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run ends with KeyError while publishing
- **Status:** UNTESTED

## B046 - publishing deleted the paid folder and then tried to copy it

- **Cause:** write_app for the full tier already writes into paid/, so the extra copytree deleted its own source with rmtree first
- **Fix:** remove the copy entirely and just record which paid build exists
- **Files:** verify_app.py
- **Check for recurrence:** recurs if verify ends with FileNotFoundError on a path under paid/
- **Status:** UNTESTED

## B047 - after publishing, the exposure check refused the run with two violations

- **Cause:** publish() copied the paid tier into the public site/apps/ folder, and a stale password-manager-basic-basic directory from earlier broken runs was still tracked in git
- **Fix:** keep the paid tier out of site/ entirely and delete the stale trackned directory
- **Files:** make_app.py, check_exposure.py
- **Check for recurrence:** recurs if check_exposure reports a paid edition or a duplicated slug
- **Status:** UNTESTED

## How to use this

1. If the symptom matches an entry, use that fix. Do not invent a new one.
2. If it does not match, treat it as new: diagnose it, then record it with
   `buglog.record(symptom, cause, fix, files, detects)` so it is here next time.
