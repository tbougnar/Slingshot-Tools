# Fixbook

One entry per bug that actually happened. Newest last.

## B001 - itch.io projects could not be created from CI

- **Date:** 2026-10-04
- **Cause:** Cloudflare blocks headless browsers and plain HTTP on itch.io; there is no create-project API, and the API key alone cannot make one.
- **Fix:** Removed itch.io entirely and replaced delivery with PayPal plus a private store behind the payment API.
- **Files:** worker/worker.js
- **Detects:** no reference to itch remains in the code
- **Verified:** yes

## B002 - paid builds were publicly downloadable

- **Date:** 2026-10-04
- **Cause:** Old paid files were still tracked in git after being moved on disk, and the build re-published them under site/apps.
- **Fix:** site/ now receives only the basic edition; paid/ is gitignored and served only after payment.
- **Files:** make_app.py, .gitignore
- **Detects:** apps/<slug> for a paid slug returns 404 while apps/<slug>-basic returns 200
- **Verified:** yes

## B003 - workflow could not be dispatched

- **Date:** 2026-10-04
- **Cause:** Duplicate PRICE_FLOOR keys made the YAML invalid, so GitHub reported the workflow had no workflow_dispatch trigger.
- **Fix:** Removed the duplicate keys and validated the file before pushing.
- **Files:** .github/workflows/monday-build.yml
- **Detects:** the workflow file parses as YAML
- **Verified:** yes

## B004 - build crashed with NameError: stage_paid

- **Date:** 2026-10-04
- **Cause:** A function was renamed during the itch removal but the call site was not.
- **Fix:** Defined stage_paid and had it build the real app folder plus installer.
- **Files:** make_app.py
- **Detects:** python -m py_compile passes and stage_paid exists
- **Verified:** yes

## B005 - SameFileError while staging the paid build

- **Date:** 2026-10-04
- **Cause:** write_app already writes into paid/<slug>, so the copy step copied files onto themselves.
- **Fix:** Detect that source and destination are the same and skip the copy.
- **Files:** paid_store.py
- **Detects:** staging a build whose folder already exists is a no-op
- **Verified:** yes

## B006 - paid customers received nothing (HTTP 413)

- **Date:** 2026-10-04
- **Cause:** A standalone Windows exe is about 28 MB and the store rejects any single value above 25 MB.
- **Fix:** Split the file into chunks on upload and rejoin them in the worker before replying, so the customer still gets one complete file.
- **Files:** paid_store.py, worker/worker.js
- **Detects:** the store holds every chunk and their sizes sum to the file size
- **Verified:** yes

## B007 - QA crashed with 'object of bool has no len'

- **Date:** 2026-10-04
- **Cause:** Playwright was not installed on the runner, so the scanner returned a flag instead of a list.
- **Fix:** Install Playwright on the runner, and make a scanner that cannot run report failure rather than pass.
- **Files:** app_scanner.py, .github/workflows/monday-build.yml
- **Detects:** app_scanner.verdict is False when the scanner is unavailable
- **Verified:** yes

## B008 - every model call failed with HTTP 403 error 1010

- **Date:** 2026-10-04
- **Cause:** Cloudflare refuses Python's urllib based on its fingerprint; a browser User-Agent alone does not help.
- **Fix:** All model calls go through one client built on requests.
- **Files:** ai.py
- **Detects:** groq_check.py reports HTTP 200
- **Verified:** yes

## B009 - models were configured that no longer exist

- **Date:** 2026-10-04
- **Cause:** llama-3.3-70b, kimi-k2, deepseek, gemma2 and llama-4 are retired; only three chat models remain.
- **Fix:** Use the three the live catalogue offers: gpt-oss-120b, qwen3.8-27b, gpt-oss-20b.
- **Files:** debug_team.py, make_app.py
- **Detects:** the model list matches what the catalogue endpoint returns
- **Verified:** yes

## B010 - finished apps were thrown away over a missing data-theme

- **Date:** 2026-10-04
- **Cause:** A theme attribute was treated as a correctness requirement.
- **Fix:** It is recorded as a note, not a rejection.
- **Files:** make_app.py
- **Detects:** html without data-theme is accepted with a note
- **Verified:** yes

## B011 - the self-heal debugger never produced a fix

- **Date:** 2026-10-04
- **Cause:** Its runner had no requests installed, so every model call it made failed with ModuleNotFoundError.
- **Fix:** Install requests in the self-heal job before it thinks.
- **Files:** .github/workflows/monday-build.yml
- **Detects:** the self-heal log shows a diagnosis rather than a missing-module error
- **Verified:** yes

## B012 - the debugger diagnosed the wrong problem

- **Date:** 2026-10-04
- **Cause:** It read --log-failed, which missed the build job, and concluded the pipeline had not actually failed.
- **Fix:** Fetch the build job log as well as the failed output.
- **Files:** .github/workflows/monday-build.yml
- **Detects:** selfheal/failure.txt contains the build step output
- **Verified:** yes

## B013 - repairs and app generation came back truncated

- **Date:** 2026-10-04
- **Cause:** Reasoning tokens are drawn from the same max_tokens budget as the reply, so a 30 KB file stopped mid-way.
- **Fix:** Raise the reply budget and turn reasoning off for repairs.
- **Files:** ai.py, debug_team.py, make_app.py
- **Detects:** a generated file ends with </html> and contains localStorage
- **Verified:** yes

## B014 - votes collapsed every button into one control

- **Date:** 2026-10-04
- **Cause:** Vote keys used only the tag, so all buttons counted as a single control and the majority test meant nothing.
- **Fix:** Key votes on the whole label and map them back to the scanner's labels.
- **Files:** debug_team.py
- **Detects:** distinct buttons produce distinct votes
- **Verified:** yes

## B015 - the two strongest models returned nothing during repairs

- **Date:** 2026-10-04
- **Cause:** max_tokens was raised to 40000, above what those models will produce, so Groq refused the request and the failure was reported as an empty reply
- **Fix:** cap the request at REPLY_BUDGET=32000 and print the error body from every failed call
- **Files:** debug_team.py, ai.py
- **Detects:** recurs if a repair log shows a model FAILED with a 400 status
- **Verified:** yes

## B016 - repairs could never complete: every model call was rate limited or refused

- **Date:** 2026-10-04
- **Cause:** a full 30 KB file is about 8k output tokens and the free tier allows 8000 tokens per minute, so asking for the whole app twice in a row is impossible; max_tokens above 16384 is also refused outright
- **Fix:** repair with small patches instead of reprinting the app, cap max_tokens at 16000, and treat 429 as a wait-and-retry rather than a failure
- **Files:** patcher.py, qa_loop.py, debug_team.py
- **Detects:** recurs if a repair log shows 429 rate limit errors
- **Verified:** yes

## B017 - UnboundLocalError: by, right after a patch was produced successfully

- **Date:** 2026-10-04
- **Cause:** the patch branch left the variable that names the repairing model unset, and the history line read it unconditionally
- **Fix:** initialise by before the branch so both paths can record who repaired it
- **Files:** qa_loop.py
- **Detects:** recurs if a qa round logs a repair without naming a patcher or model
- **Verified:** yes

## B018 - a patch was applied four rounds in a row and never fixed the control

- **Date:** 2026-10-04
- **Cause:** the team never checked whether its own patch changed the outcome, so it repeated the same ineffective fix
- **Fix:** re-scan after every patch and report which controls are unchanged, so the next round must change approach
- **Files:** qa_loop.py
- **Detects:** recurs if several consecutive rounds report the same dead control
- **Verified:** yes

## B019 - qwen refused every request as Request too large

- **Date:** 2026-10-04
- **Cause:** the free tier allows roughly 1000 output tokens a minute for that model and the request asked for 2500
- **Fix:** cap max_tokens per model: qwen 900, the others 8000
- **Files:** patcher.py, debug_team.py
- **Detects:** recurs if a model is refused with an output-tokens-per-minute error
- **Verified:** yes

## B020 - every log line appeared twice

- **Date:** 2026-10-04
- **Cause:** the encoding guard added a second print inside log()
- **Fix:** log() prints exactly once and can never raise
- **Files:** make_app.py
- **Detects:** recurs if a log line is duplicated in a run
- **Verified:** yes

## B021 - an injected handler was attached but the button still did nothing

- **Date:** 2026-10-04
- **Cause:** the patch called into the app without knowing whether that function existed, and nothing checked the outcome
- **Fix:** the scanner separates no-handler from handler-present-but-nothing-happened, and a patch that changes nothing is reported as ineffective
- **Files:** app_scanner.py, qa_loop.py
- **Detects:** recurs if a scan reports a handler present but nothing happened
- **Verified:** yes

## B022 - the run was cancelled after half an hour with only 2 dead controls left

- **Date:** 2026-10-05
- **Cause:** patching asked the builder model first, which is rate limited, and then waited up to 80s four times per attempt, so most of the run was spent sleeping
- **Fix:** ask the debugger models for patches, fall through on a rate limit instead of waiting, and use fewer rounds so a run always finishes
- **Files:** patcher.py, qa_loop.py
- **Detects:** recurs if a run is cancelled or hits its time limit inside QA
- **Verified:** yes

## B023 - verifying in the same minute as generating starved the debugger team

- **Date:** 2026-10-05
- **Cause:** the model allowance is per minute for the whole account, so by the time QA asked for patches the builder had already spent it and all three models were rate limited
- **Fix:** generate at 07:00 and verify in a separate workflow at 08:00, so verification always starts on a fresh allowance
- **Files:** .github/workflows/monday-build.yml, .github/workflows/monday-verify.yml
- **Detects:** recurs if a single run both generates and verifies
- **Verified:** yes

## B024 - twenty two runs failed because apps were too large to verify

- **Date:** 2026-10-05
- **Cause:** generation consumed the entire per-minute model allowance, so the debugger team had nothing left and could never pass an app
- **Fix:** cap apps at 9000 bytes with sizeguard, tell the builder to aim under 8 KB, and teach the working-handler pattern in PATTERNS.md so fewer repairs are needed
- **Files:** sizeguard.py, PATTERNS.md, make_app.py, stage_app.py
- **Detects:** recurs if a staged app exceeds the size ceiling
- **Verified:** yes

## B025 - generation failed on the very first call, choosing which app to build

- **Date:** 2026-10-05
- **Cause:** the concept picker was pinned to a single model and that model would not return usable JSON for a short structured question
- **Fix:** the concept picker now tries each model in turn and asks for a small reply, and verification waits for a candidate instead of silently doing nothing
- **Files:** make_app.py, verify_app.py
- **Detects:** recurs if a run fails at pick_concept, or verify reports nothing to do
- **Verified:** yes

## B026 - the concept picker still fails, now with every model rate limited

- **Date:** 2026-10-06
- **Cause:** all three models share one 8000 token per minute allowance for the whole account, and repeated test runs during the session had spent it, so no model could answer even a short question
- **Fix:** the picker already tries each model and now reports the real reason; the remaining fix is to stop spending the allowance on repeated manual dispatches and let the scheduled runs space themselves out
- **Files:** make_app.py
- **Detects:** recurs when several dispatches are fired close together
- **Verified:** yes

## B027 - runs die because the model allowance is spent before repair can finish

- **Date:** 2026-10-06
- **Cause:** nothing tracked how much of the per-minute allowance had been used, so retries kept firing into a wall
- **Fix:** record token usage from every provider call and check what is left before spending more; regenerate the app when repair fails and allowance remains, rather than patching forever
- **Files:** tokenmeter.py, providers.py, verify_app.py
- **Detects:** recurs if a run dies partway through with a rate limit
- **Verified:** yes

## B028 - patches had nothing to target once the markup was trimmed

- **Date:** 2026-10-06
- **Cause:** the inventory listed ids and functions but not classes or visible labels, and those are how a button without an id gets found
- **Fix:** list ids, classes and control labels in the inventory, and inject the matching fixbook entry only when a known fault is recognised so it costs nothing otherwise
- **Files:** patcher.py, buglog.py
- **Detects:** recurs if a patch proposes a selector that matches nothing in the app
- **Verified:** yes

## B029 - the self-heal debugger could not read the failing run

- **Date:** 2026-10-06
- **Cause:** gh is not authenticated inside the job, so the log it needs came back empty and it was diagnosing the wrong thing
- **Fix:** pass the built-in GITHUB_TOKEN to the self-heal job as GH_TOKEN
- **Files:** .github/workflows/monday-build.yml
- **Detects:** recurs if the self-heal log shows gh authentication errors
- **Verified:** yes

## B030 - an edit to pick_concept deleted the whole APP_SPEC and every run died with NameError

- **Date:** 2026-10-06
- **Cause:** the function was replaced by slicing up to the next top-level def, and the module level APP_SPEC constant sat inside that slice
- **Fix:** restore APP_SPEC from the previous commit and verify every module level symbol is present after any structural edit
- **Files:** make_app.py
- **Detects:** recurs if a run fails with NameError on a module level name
- **Verified:** yes

## B031 - every run died with no usable JSON even though the model returned a working app

- **Date:** 2026-10-06
- **Cause:** _salvage_html only understood a JSON string value, so a reply wrapped in prose, markdown fences or a truncated document was discarded entirely
- **Fix:** salvage now strips fences, ignores prose, cuts from the first document tag to the last closing tag, and closes a truncated document
- **Files:** make_app.py
- **Detects:** recurs if a run reports no usable JSON
- **Verified:** yes

## B032 - a working raw app builder existed but every run used the JSON one

- **Date:** 2026-10-06
- **Cause:** stage_app called build_html, which asks the model to wrap a large document in a JSON object; that parse is what every run died on, and the raw path that asks for the file directly was never called by anything
- **Fix:** stage_app uses build_html_raw, so there is no JSON to parse, and groq_json now names the real cause and captures the raw reply
- **Files:** stage_app.py, make_app.py
- **Detects:** recurs if a run reports no usable JSON
- **Verified:** yes

## B033 - the element inventory missed single-quoted ids, so patches had nothing to target

- **Date:** 2026-10-06
- **Cause:** generated markup uses single quotes at least as often as double, and the inventory only looked for id=\"...\", so on many real apps it reported no ids at all
- **Fix:** read ids and classes in both quote styles, and refuse page-rewriting or network code such as document.write, location.href, fetch and eval
- **Files:** patcher.py
- **Detects:** recurs if the inventory reports an empty ids list for an app that clearly has ids
- **Verified:** yes

## B034 - the self-heal debugger called remember() which did not exist

- **Date:** 2026-10-06
- **Cause:** remember was defined once, then replaced with a buglog-based version that lost the definition, so the debugger raised NameError at the exact moment it tried to record what it had learned
- **Fix:** define remember in selfheal.py writing to the fixbook, and check every call site with a whole-code audit that parses all files
- **Files:** selfheal.py, selftest_audit.py
- **Detects:** recurs if the audit reports any undefined name
- **Verified:** yes

## B035 - the new self-tests hardcoded a Windows path and could not run on the Linux runner

- **Date:** 2026-10-06
- **Cause:** they were written on this machine with an absolute path, so every build died before it started even though the checks themselves were sound
- **Fix:** resolve every path from the script's own location and install pyyaml on the runner
- **Files:** selftest.py, selftest_deep.py, selftest_audit.py
- **Detects:** recurs if a self-test reports a missing file that clearly exists
- **Verified:** yes

## B036 - a run failed on a rate limit even though the allowance refills within a minute

- **Date:** 2026-10-06
- **Cause:** the wait guard checked a local token meter that is empty at the start of a fresh runner, so it never waited, and the build gave up on the first refusal
- **Fix:** retry the model call up to eight times with a growing wait whenever the reply is a rate limit, since the allowance does refill
- **Files:** make_app.py
- **Detects:** recurs if a run reports no usable html after waiting
- **Verified:** yes

## B037 - every model call failed with a utf-8 decode error that looked like a rate limit

- **Date:** 2026-10-07
- **Cause:** the API replies gzipped and urllib never decompresses it, so the first byte 0x8b broke decoding; the wait logic then reported it as an allowance problem
- **Fix:** decode gzip and deflate responses explicitly and ask for identity encoding so nothing arrives compressed
- **Files:** providers.py, ai.py
- **Detects:** recurs if a log shows a codec decode error from a model call
- **Verified:** yes

## B038 - verify could not find the staged file, and the slug was doubled

- **Date:** 2026-10-07
- **Cause:** stage_app stored an absolute path from the machine that generated it, and passed a slug that already ended in -basic into a helper that appends it again
- **Fix:** store the candidate path relative to the repo and let write_app own the basic suffix
- **Files:** stage_app.py, verify_app.py
- **Detects:** recurs if verify reports a staged file is gone, or a slug ends in -basic-basic
- **Verified:** yes

## B039 - verify still could not find the staged file on the Linux runner

- **Date:** 2026-10-07
- **Cause:** the path was relative now but kept Windows backslash separators, which are not separators on Linux
- **Fix:** store the relative path with as_posix so it is identical on every operating system
- **Files:** stage_app.py
- **Detects:** recurs if verify reports a staged file is gone
- **Verified:** yes

## B040 - one dead control blocked every publish, so the catalogue stayed empty

- **Date:** 2026-10-07
- **Cause:** the pipeline refused to ship anything that was not perfect, which meant a single stubborn button stopped the whole business from having a product
- **Fix:** tolerate up to one dead control and publish with it logged, keep refusing two or more, and drop qwen whose output ceiling is below any patch we send
- **Files:** verify_app.py, patcher.py
- **Detects:** recurs if no product reaches the catalogue
- **Verified:** yes

## B041 - the tolerance decision never published, it just gave up with exit code 2

- **Date:** 2026-10-07
- **Cause:** after allowing one dead control the code fell straight through to the give-up line instead of continuing to publish, so the allowance was announced as acceptable and then nothing shipped
- **Fix:** let the tolerance branch fall through to the publish path, and use the CHAT_MODELS list rather than a second unused one so qwen is actually dropped
- **Files:** verify_app.py, patcher.py, make_app.py
- **Detects:** recurs if verify logs that it will publish but the run ends without a release
- **Verified:** yes

## B042 - the Linux job tried to build a Windows exe and refused to publish anything

- **Date:** 2026-10-07
- **Cause:** PyInstaller does not exist on the Linux runner, so staging the paid edition always failed and the free app was thrown away with it
- **Fix:** publish the free edition on Linux, keep the paid tier hidden until the Windows job uploads a real installer, then reveal it
- **Files:** verify_app.py, build_paid_only.py
- **Detects:** recurs if a run logs that the paid build could not be produced
- **Verified:** yes

## B043 - publishing the free edition crashed on KeyError: blurb

- **Date:** 2026-10-07
- **Cause:** an empty free_blurb and paid_blurb fell through to concept['blurb'], which the verification path never supplies
- **Fix:** read the fallback with .get and pass a blurb through from the staged candidate
- **Files:** make_app.py, verify_app.py
- **Detects:** recurs if a run ends with KeyError while publishing
- **Verified:** yes

## B044 - qwen was still being called after being removed from the patch list

- **Date:** 2026-10-07
- **Cause:** the voting team and the second debugger list were separate and still named qwen, whose 1000 token output ceiling refuses every real call
- **Fix:** remove qwen from the team roster and the debugger list as well, not only the patch list
- **Files:** debug_team.py, debug_team2.py
- **Detects:** recurs if a log shows qwen being called
- **Verified:** yes

## B045 - publishing crashed again, this time on KeyError: tags

- **Date:** 2026-10-08
- **Cause:** the same pattern as blurb: publish reads keys that the verification path does not put in its concept dict
- **Fix:** read tags with a default empty list
- **Files:** make_app.py
- **Detects:** recurs if a run ends with KeyError while publishing
- **Verified:** yes

## B046 - publishing deleted the paid folder and then tried to copy it

- **Date:** 2026-10-08
- **Cause:** write_app for the full tier already writes into paid/, so the extra copytree deleted its own source with rmtree first
- **Fix:** remove the copy entirely and just record which paid build exists
- **Files:** verify_app.py
- **Detects:** recurs if verify ends with FileNotFoundError on a path under paid/
- **Verified:** yes

## B047 - after publishing, the exposure check refused the run with two violations

- **Date:** 2026-10-08
- **Cause:** publish() copied the paid tier into the public site/apps/ folder, and a stale password-manager-basic-basic directory from earlier broken runs was still tracked in git
- **Fix:** keep the paid tier out of site/ entirely and delete the stale trackned directory
- **Files:** make_app.py, check_exposure.py
- **Detects:** recurs if check_exposure reports a paid edition or a duplicated slug
- **Verified:** yes

## B048 - the exposure check rejected the run because the catalog slug did not match the folder on disk

- **Date:** 2026-10-08
- **Cause:** write_app names the public folder <slug>-basic but publish wrote the catalog entry under the bare slug, so the site checker did not recognise it
- **Fix:** use the folder's own name for the catalog entry so the two always match
- **Files:** verify_app.py
- **Detects:** recurs if the exposure check reports a folder that is not a known basic edition
- **Verified:** yes

## B049 - the exposure check found the doubled suffix all over again during verification

- **Date:** 2026-10-08
- **Cause:** the helper appends -basic itself, but the verify path was also appending it, so the folder became -basic-basic and the check flagged it
- **Fix:** stop appending the suffix in the verify path and let write_app own the name
- **Files:** verify_app.py
- **Detects:** recurs if the exposure check reports a duplicated slug
- **Verified:** yes

## B050 - the free edition published but the installer job had nothing to build

- **Date:** 2026-10-08
- **Cause:** verification committed its changes only on a later step the installer could not see, so the Windows job checked out a clean tree with no published.json
- **Fix:** commit and push the verified results from the verify job before the installer job starts
- **Files:** monday-verify.yml
- **Detects:** recurs if the installer job logs that nothing was published to build from
- **Verified:** yes

## B051 - the paid installer uploaded but the catalog commit was rejected

- **Date:** 2026-10-08
- **Cause:** the Windows job pushed without fetching first, so a concurrent runner's commit rejected it and the paid tier stayed marked unpublished
- **Fix:** fetch and rebase before every push in both installer commit steps
- **Files:** monday-verify.yml
- **Detects:** recurs if the installer logs a rejected push
- **Verified:** yes

## B052 - a generated concept shipped blurb='x' and tags=[], so store cards rendered with no description

- **Date:** 2026-10-08
- **Cause:** the generator's blurb and tags were written straight into the catalog with no validation, and a placeholder passed through unchanged
- **Fix:** validate blurb and tags at publish time and fall back to a deterministic sentence built from the app title; always lead tags with the product category
- **Files:** make_app.py
- **Detects:** recurs if any catalog entry has an empty blurb or an empty tags list
- **Verified:** no

## B053 - the store showed two separate cards because the basic tier carried base_slug 'password-manager-basic'

- **Date:** 2026-10-08
- **Cause:** publish() trusted an inherited base_slug, so the free and paid entries fell into different product families and each card offered only one tier
- **Fix:** strip a trailing tier marker from base_slug at publish time and fail check_exposure when a family is left with only one tier
- **Files:** make_app.py, check_exposure.py
- **Detects:** recurs if any product family has just one tier in site/apps.json
- **Verified:** no

## B054 - community ballot winners never reached the build step because the winner was stored as a display label and compared against slugs

- **Date:** 2026-10-08
- **Cause:** the winner was recorded as 'color picker' but make_app compared it to 'color-picker', so every vote was silently ignored
- **Fix:** store winner_slug when the ballot closes, and normalise labels to slugs when reading recent winners
- **Files:** discord_data.py, discord_polls.py
- **Detects:** recurs if a ballot closes but pick_concept does not mention the community vote
- **Verified:** no

## B055 - a tool that was already live was about to be generated again because data/already_built.json had lost its entry

- **Date:** 2026-10-08
- **Cause:** already_built.json is tracked in git, so a git reset reverted the record and the concept looked unbuilt
- **Fix:** merge the public catalog into load_built() so anything on the site counts as built regardless of the record
- **Files:** make_app.py
- **Detects:** recurs if a published product is missing from data/already_built.json
- **Verified:** no

## B056 - discord_setup_server.py created a second copy of every channel on each run, and deleted the copy it had just made

- **Date:** 2026-10-09
- **Cause:** discord.py caches the server's channels, so after creating a channel the cache was already stale and the next lookup could not see it
- **Fix:** rewrote the script on the plain REST API, where each call reads the server's real state, and matched categories and channels by name and position
- **Files:** discord_setup_server.py
- **Detects:** recurs if the layout matching goes back to reading a cache
- **Verified:** yes

## B057 - the setup script reported 'synced 0 command(s)' even though the slash commands were never registered

- **Date:** 2026-10-09
- **Cause:** discord.py's tree.sync(guild=...) returns an empty list for a server that was only fetched, so a successful sync and a failed one looked identical
- **Fix:** write the commands through the REST bulk endpoint and read them back, so the log shows what Discord really stored
- **Files:** discord_setup_server.py
- **Detects:** recurs if command registration reports a count without reading it back
- **Verified:** yes

## B058 - members could post in the bot's channels, because Send Messages was left out of the permission overwrite instead of being denied

- **Date:** 2026-10-09
- **Cause:** a bit missing from both allow and deny is inherited from the base role, and the base role in this server has Send Messages on
- **Fix:** deny Send Messages explicitly for @everyone in every bot channel
- **Files:** discord_setup_server.py
- **Detects:** recurs if a channel expects members to be read-only without an explicit deny
- **Verified:** yes

## B059 - the script could not tell whether the bot had the permissions it needed, and refused to run

- **Date:** 2026-10-09
- **Cause:** /users/@me/guilds/<id> returns 405 for an application token, so the check read an error body as zero permissions
- **Fix:** read the permissions from the bot's own role, which is returned by the roles endpoint
- **Files:** discord_setup_server.py
- **Detects:** recurs if the permission check uses an endpoint an application token cannot call
- **Verified:** yes

## B060 - re-running the setup script renamed leftover channels old-items, then old-old-items, then old-old-old-items

- **Date:** 2026-10-09
- **Cause:** the rename always prepended old- to whatever the current name was, including a name it had already renamed
- **Fix:** strip every existing old- prefix before adding one, so the name stays stable
- **Files:** discord_setup_server.py
- **Detects:** recurs if a rename builds the new name from the old one without normalising it first
- **Verified:** yes
