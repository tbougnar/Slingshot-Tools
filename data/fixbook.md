# Fixbook

Every fault we have hit in this pipeline, what actually caused it, and
the change that fixed it. Check here before proposing anything.

## B001 - itch.io projects could not be created from CI

- **Cause:** Cloudflare blocks headless browsers and plain HTTP on itch.io; there is no create-project API, and the API key alone cannot make one.
- **Fix:** Removed itch.io entirely and replaced delivery with PayPal plus a private store behind the payment API.
- **Files:** worker/worker.js
- **Check for recurrence:** no reference to itch remains in the code
- **Status:** PROVEN

## B002 - paid builds were publicly downloadable

- **Cause:** Old paid files were still tracked in git after being moved on disk, and the build re-published them under site/apps.
- **Fix:** site/ now receives only the basic edition; paid/ is gitignored and served only after payment.
- **Files:** make_app.py, .gitignore
- **Check for recurrence:** apps/<slug> for a paid slug returns 404 while apps/<slug>-basic returns 200
- **Status:** PROVEN

## B003 - workflow could not be dispatched

- **Cause:** Duplicate PRICE_FLOOR keys made the YAML invalid, so GitHub reported the workflow had no workflow_dispatch trigger.
- **Fix:** Removed the duplicate keys and validated the file before pushing.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** the workflow file parses as YAML
- **Status:** PROVEN

## B004 - build crashed with NameError: stage_paid

- **Cause:** A function was renamed during the itch removal but the call site was not.
- **Fix:** Defined stage_paid and had it build the real app folder plus installer.
- **Files:** make_app.py
- **Check for recurrence:** python -m py_compile passes and stage_paid exists
- **Status:** PROVEN

## B005 - SameFileError while staging the paid build

- **Cause:** write_app already writes into paid/<slug>, so the copy step copied files onto themselves.
- **Fix:** Detect that source and destination are the same and skip the copy.
- **Files:** paid_store.py
- **Check for recurrence:** staging a build whose folder already exists is a no-op
- **Status:** PROVEN

## B006 - paid customers received nothing (HTTP 413)

- **Cause:** A standalone Windows exe is about 28 MB and the store rejects any single value above 25 MB.
- **Fix:** Split the file into chunks on upload and rejoin them in the worker before replying, so the customer still gets one complete file.
- **Files:** paid_store.py, worker/worker.js
- **Check for recurrence:** the store holds every chunk and their sizes sum to the file size
- **Status:** PROVEN

## B007 - QA crashed with 'object of bool has no len'

- **Cause:** Playwright was not installed on the runner, so the scanner returned a flag instead of a list.
- **Fix:** Install Playwright on the runner, and make a scanner that cannot run report failure rather than pass.
- **Files:** app_scanner.py, .github/workflows/monday-build.yml
- **Check for recurrence:** app_scanner.verdict is False when the scanner is unavailable
- **Status:** PROVEN

## B008 - every model call failed with HTTP 403 error 1010

- **Cause:** Cloudflare refuses Python's urllib based on its fingerprint; a browser User-Agent alone does not help.
- **Fix:** All model calls go through one client built on requests.
- **Files:** ai.py
- **Check for recurrence:** groq_check.py reports HTTP 200
- **Status:** PROVEN

## B009 - models were configured that no longer exist

- **Cause:** llama-3.3-70b, kimi-k2, deepseek, gemma2 and llama-4 are retired; only three chat models remain.
- **Fix:** Use the three the live catalogue offers: gpt-oss-120b, qwen3.8-27b, gpt-oss-20b.
- **Files:** debug_team.py, make_app.py
- **Check for recurrence:** the model list matches what the catalogue endpoint returns
- **Status:** PROVEN

## B010 - finished apps were thrown away over a missing data-theme

- **Cause:** A theme attribute was treated as a correctness requirement.
- **Fix:** It is recorded as a note, not a rejection.
- **Files:** make_app.py
- **Check for recurrence:** html without data-theme is accepted with a note
- **Status:** PROVEN

## B011 - the self-heal debugger never produced a fix

- **Cause:** Its runner had no requests installed, so every model call it made failed with ModuleNotFoundError.
- **Fix:** Install requests in the self-heal job before it thinks.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** the self-heal log shows a diagnosis rather than a missing-module error
- **Status:** PROVEN

## B012 - the debugger diagnosed the wrong problem

- **Cause:** It read --log-failed, which missed the build job, and concluded the pipeline had not actually failed.
- **Fix:** Fetch the build job log as well as the failed output.
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** selfheal/failure.txt contains the build step output
- **Status:** PROVEN

## B013 - repairs and app generation came back truncated

- **Cause:** Reasoning tokens are drawn from the same max_tokens budget as the reply, so a 30 KB file stopped mid-way.
- **Fix:** Raise the reply budget and turn reasoning off for repairs.
- **Files:** ai.py, debug_team.py, make_app.py
- **Check for recurrence:** a generated file ends with </html> and contains localStorage
- **Status:** PROVEN

## B014 - votes collapsed every button into one control

- **Cause:** Vote keys used only the tag, so all buttons counted as a single control and the majority test meant nothing.
- **Fix:** Key votes on the whole label and map them back to the scanner's labels.
- **Files:** debug_team.py
- **Check for recurrence:** distinct buttons produce distinct votes
- **Status:** PROVEN

## B015 - the two strongest models returned nothing during repairs

- **Cause:** max_tokens was raised to 40000, above what those models will produce, so Groq refused the request and the failure was reported as an empty reply
- **Fix:** cap the request at REPLY_BUDGET=32000 and print the error body from every failed call
- **Files:** debug_team.py, ai.py
- **Check for recurrence:** recurs if a repair log shows a model FAILED with a 400 status
- **Status:** PROVEN

## B016 - repairs could never complete: every model call was rate limited or refused

- **Cause:** a full 30 KB file is about 8k output tokens and the free tier allows 8000 tokens per minute, so asking for the whole app twice in a row is impossible; max_tokens above 16384 is also refused outright
- **Fix:** repair with small patches instead of reprinting the app, cap max_tokens at 16000, and treat 429 as a wait-and-retry rather than a failure
- **Files:** patcher.py, qa_loop.py, debug_team.py
- **Check for recurrence:** recurs if a repair log shows 429 rate limit errors
- **Status:** PROVEN

## B017 - UnboundLocalError: by, right after a patch was produced successfully

- **Cause:** the patch branch left the variable that names the repairing model unset, and the history line read it unconditionally
- **Fix:** initialise by before the branch so both paths can record who repaired it
- **Files:** qa_loop.py
- **Check for recurrence:** recurs if a qa round logs a repair without naming a patcher or model
- **Status:** PROVEN

## B018 - a patch was applied four rounds in a row and never fixed the control

- **Cause:** the team never checked whether its own patch changed the outcome, so it repeated the same ineffective fix
- **Fix:** re-scan after every patch and report which controls are unchanged, so the next round must change approach
- **Files:** qa_loop.py
- **Check for recurrence:** recurs if several consecutive rounds report the same dead control
- **Status:** PROVEN

## B019 - qwen refused every request as Request too large

- **Cause:** the free tier allows roughly 1000 output tokens a minute for that model and the request asked for 2500
- **Fix:** cap max_tokens per model: qwen 900, the others 8000
- **Files:** patcher.py, debug_team.py
- **Check for recurrence:** recurs if a model is refused with an output-tokens-per-minute error
- **Status:** PROVEN

## B020 - every log line appeared twice

- **Cause:** the encoding guard added a second print inside log()
- **Fix:** log() prints exactly once and can never raise
- **Files:** make_app.py
- **Check for recurrence:** recurs if a log line is duplicated in a run
- **Status:** PROVEN

## B021 - an injected handler was attached but the button still did nothing

- **Cause:** the patch called into the app without knowing whether that function existed, and nothing checked the outcome
- **Fix:** the scanner separates no-handler from handler-present-but-nothing-happened, and a patch that changes nothing is reported as ineffective
- **Files:** app_scanner.py, qa_loop.py
- **Check for recurrence:** recurs if a scan reports a handler present but nothing happened
- **Status:** PROVEN

## B022 - the run was cancelled after half an hour with only 2 dead controls left

- **Cause:** patching asked the builder model first, which is rate limited, and then waited up to 80s four times per attempt, so most of the run was spent sleeping
- **Fix:** ask the debugger models for patches, fall through on a rate limit instead of waiting, and use fewer rounds so a run always finishes
- **Files:** patcher.py, qa_loop.py
- **Check for recurrence:** recurs if a run is cancelled or hits its time limit inside QA
- **Status:** PROVEN

## B023 - verifying in the same minute as generating starved the debugger team

- **Cause:** the model allowance is per minute for the whole account, so by the time QA asked for patches the builder had already spent it and all three models were rate limited
- **Fix:** generate at 07:00 and verify in a separate workflow at 08:00, so verification always starts on a fresh allowance
- **Files:** .github/workflows/monday-build.yml, .github/workflows/monday-verify.yml
- **Check for recurrence:** recurs if a single run both generates and verifies
- **Status:** PROVEN

## B024 - twenty two runs failed because apps were too large to verify

- **Cause:** generation consumed the entire per-minute model allowance, so the debugger team had nothing left and could never pass an app
- **Fix:** cap apps at 9000 bytes with sizeguard, tell the builder to aim under 8 KB, and teach the working-handler pattern in PATTERNS.md so fewer repairs are needed
- **Files:** sizeguard.py, PATTERNS.md, make_app.py, stage_app.py
- **Check for recurrence:** recurs if a staged app exceeds the size ceiling
- **Status:** PROVEN

## B025 - generation failed on the very first call, choosing which app to build

- **Cause:** the concept picker was pinned to a single model and that model would not return usable JSON for a short structured question
- **Fix:** the concept picker now tries each model in turn and asks for a small reply, and verification waits for a candidate instead of silently doing nothing
- **Files:** make_app.py, verify_app.py
- **Check for recurrence:** recurs if a run fails at pick_concept, or verify reports nothing to do
- **Status:** PROVEN

## B026 - the concept picker still fails, now with every model rate limited

- **Cause:** all three models share one 8000 token per minute allowance for the whole account, and repeated test runs during the session had spent it, so no model could answer even a short question
- **Fix:** the picker already tries each model and now reports the real reason; the remaining fix is to stop spending the allowance on repeated manual dispatches and let the scheduled runs space themselves out
- **Files:** make_app.py
- **Check for recurrence:** recurs when several dispatches are fired close together
- **Status:** PROVEN

## B027 - runs die because the model allowance is spent before repair can finish

- **Cause:** nothing tracked how much of the per-minute allowance had been used, so retries kept firing into a wall
- **Fix:** record token usage from every provider call and check what is left before spending more; regenerate the app when repair fails and allowance remains, rather than patching forever
- **Files:** tokenmeter.py, providers.py, verify_app.py
- **Check for recurrence:** recurs if a run dies partway through with a rate limit
- **Status:** PROVEN

## B028 - patches had nothing to target once the markup was trimmed

- **Cause:** the inventory listed ids and functions but not classes or visible labels, and those are how a button without an id gets found
- **Fix:** list ids, classes and control labels in the inventory, and inject the matching fixbook entry only when a known fault is recognised so it costs nothing otherwise
- **Files:** patcher.py, buglog.py
- **Check for recurrence:** recurs if a patch proposes a selector that matches nothing in the app
- **Status:** PROVEN

## B029 - the self-heal debugger could not read the failing run

- **Cause:** gh is not authenticated inside the job, so the log it needs came back empty and it was diagnosing the wrong thing
- **Fix:** pass the built-in GITHUB_TOKEN to the self-heal job as GH_TOKEN
- **Files:** .github/workflows/monday-build.yml
- **Check for recurrence:** recurs if the self-heal log shows gh authentication errors
- **Status:** PROVEN

## B030 - an edit to pick_concept deleted the whole APP_SPEC and every run died with NameError

- **Cause:** the function was replaced by slicing up to the next top-level def, and the module level APP_SPEC constant sat inside that slice
- **Fix:** restore APP_SPEC from the previous commit and verify every module level symbol is present after any structural edit
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run fails with NameError on a module level name
- **Status:** PROVEN

## B031 - every run died with no usable JSON even though the model returned a working app

- **Cause:** _salvage_html only understood a JSON string value, so a reply wrapped in prose, markdown fences or a truncated document was discarded entirely
- **Fix:** salvage now strips fences, ignores prose, cuts from the first document tag to the last closing tag, and closes a truncated document
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run reports no usable JSON
- **Status:** PROVEN

## B032 - a working raw app builder existed but every run used the JSON one

- **Cause:** stage_app called build_html, which asks the model to wrap a large document in a JSON object; that parse is what every run died on, and the raw path that asks for the file directly was never called by anything
- **Fix:** stage_app uses build_html_raw, so there is no JSON to parse, and groq_json now names the real cause and captures the raw reply
- **Files:** stage_app.py, make_app.py
- **Check for recurrence:** recurs if a run reports no usable JSON
- **Status:** PROVEN

## B033 - the element inventory missed single-quoted ids, so patches had nothing to target

- **Cause:** generated markup uses single quotes at least as often as double, and the inventory only looked for id=\"...\", so on many real apps it reported no ids at all
- **Fix:** read ids and classes in both quote styles, and refuse page-rewriting or network code such as document.write, location.href, fetch and eval
- **Files:** patcher.py
- **Check for recurrence:** recurs if the inventory reports an empty ids list for an app that clearly has ids
- **Status:** PROVEN

## B034 - the self-heal debugger called remember() which did not exist

- **Cause:** remember was defined once, then replaced with a buglog-based version that lost the definition, so the debugger raised NameError at the exact moment it tried to record what it had learned
- **Fix:** define remember in selfheal.py writing to the fixbook, and check every call site with a whole-code audit that parses all files
- **Files:** selfheal.py, selftest_audit.py
- **Check for recurrence:** recurs if the audit reports any undefined name
- **Status:** PROVEN

## B035 - the new self-tests hardcoded a Windows path and could not run on the Linux runner

- **Cause:** they were written on this machine with an absolute path, so every build died before it started even though the checks themselves were sound
- **Fix:** resolve every path from the script's own location and install pyyaml on the runner
- **Files:** selftest.py, selftest_deep.py, selftest_audit.py
- **Check for recurrence:** recurs if a self-test reports a missing file that clearly exists
- **Status:** PROVEN

## B036 - a run failed on a rate limit even though the allowance refills within a minute

- **Cause:** the wait guard checked a local token meter that is empty at the start of a fresh runner, so it never waited, and the build gave up on the first refusal
- **Fix:** retry the model call up to eight times with a growing wait whenever the reply is a rate limit, since the allowance does refill
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run reports no usable html after waiting
- **Status:** PROVEN

## B037 - every model call failed with a utf-8 decode error that looked like a rate limit

- **Cause:** the API replies gzipped and urllib never decompresses it, so the first byte 0x8b broke decoding; the wait logic then reported it as an allowance problem
- **Fix:** decode gzip and deflate responses explicitly and ask for identity encoding so nothing arrives compressed
- **Files:** providers.py, ai.py
- **Check for recurrence:** recurs if a log shows a codec decode error from a model call
- **Status:** PROVEN

## B038 - verify could not find the staged file, and the slug was doubled

- **Cause:** stage_app stored an absolute path from the machine that generated it, and passed a slug that already ended in -basic into a helper that appends it again
- **Fix:** store the candidate path relative to the repo and let write_app own the basic suffix
- **Files:** stage_app.py, verify_app.py
- **Check for recurrence:** recurs if verify reports a staged file is gone, or a slug ends in -basic-basic
- **Status:** PROVEN

## B039 - verify still could not find the staged file on the Linux runner

- **Cause:** the path was relative now but kept Windows backslash separators, which are not separators on Linux
- **Fix:** store the relative path with as_posix so it is identical on every operating system
- **Files:** stage_app.py
- **Check for recurrence:** recurs if verify reports a staged file is gone
- **Status:** PROVEN

## B040 - one dead control blocked every publish, so the catalogue stayed empty

- **Cause:** the pipeline refused to ship anything that was not perfect, which meant a single stubborn button stopped the whole business from having a product
- **Fix:** tolerate up to one dead control and publish with it logged, keep refusing two or more, and drop qwen whose output ceiling is below any patch we send
- **Files:** verify_app.py, patcher.py
- **Check for recurrence:** recurs if no product reaches the catalogue
- **Status:** PROVEN

## B041 - the tolerance decision never published, it just gave up with exit code 2

- **Cause:** after allowing one dead control the code fell straight through to the give-up line instead of continuing to publish, so the allowance was announced as acceptable and then nothing shipped
- **Fix:** let the tolerance branch fall through to the publish path, and use the CHAT_MODELS list rather than a second unused one so qwen is actually dropped
- **Files:** verify_app.py, patcher.py, make_app.py
- **Check for recurrence:** recurs if verify logs that it will publish but the run ends without a release
- **Status:** PROVEN

## B042 - the Linux job tried to build a Windows exe and refused to publish anything

- **Cause:** PyInstaller does not exist on the Linux runner, so staging the paid edition always failed and the free app was thrown away with it
- **Fix:** publish the free edition on Linux, keep the paid tier hidden until the Windows job uploads a real installer, then reveal it
- **Files:** verify_app.py, build_paid_only.py
- **Check for recurrence:** recurs if a run logs that the paid build could not be produced
- **Status:** PROVEN

## B043 - publishing the free edition crashed on KeyError: blurb

- **Cause:** an empty free_blurb and paid_blurb fell through to concept['blurb'], which the verification path never supplies
- **Fix:** read the fallback with .get and pass a blurb through from the staged candidate
- **Files:** make_app.py, verify_app.py
- **Check for recurrence:** recurs if a run ends with KeyError while publishing
- **Status:** PROVEN

## B044 - qwen was still being called after being removed from the patch list

- **Cause:** the voting team and the second debugger list were separate and still named qwen, whose 1000 token output ceiling refuses every real call
- **Fix:** remove qwen from the team roster and the debugger list as well, not only the patch list
- **Files:** debug_team.py, debug_team2.py
- **Check for recurrence:** recurs if a log shows qwen being called
- **Status:** PROVEN

## B045 - publishing crashed again, this time on KeyError: tags

- **Cause:** the same pattern as blurb: publish reads keys that the verification path does not put in its concept dict
- **Fix:** read tags with a default empty list
- **Files:** make_app.py
- **Check for recurrence:** recurs if a run ends with KeyError while publishing
- **Status:** PROVEN

## B046 - publishing deleted the paid folder and then tried to copy it

- **Cause:** write_app for the full tier already writes into paid/, so the extra copytree deleted its own source with rmtree first
- **Fix:** remove the copy entirely and just record which paid build exists
- **Files:** verify_app.py
- **Check for recurrence:** recurs if verify ends with FileNotFoundError on a path under paid/
- **Status:** PROVEN

## B047 - after publishing, the exposure check refused the run with two violations

- **Cause:** publish() copied the paid tier into the public site/apps/ folder, and a stale password-manager-basic-basic directory from earlier broken runs was still tracked in git
- **Fix:** keep the paid tier out of site/ entirely and delete the stale trackned directory
- **Files:** make_app.py, check_exposure.py
- **Check for recurrence:** recurs if check_exposure reports a paid edition or a duplicated slug
- **Status:** PROVEN

## B048 - the exposure check rejected the run because the catalog slug did not match the folder on disk

- **Cause:** write_app names the public folder <slug>-basic but publish wrote the catalog entry under the bare slug, so the site checker did not recognise it
- **Fix:** use the folder's own name for the catalog entry so the two always match
- **Files:** verify_app.py
- **Check for recurrence:** recurs if the exposure check reports a folder that is not a known basic edition
- **Status:** PROVEN

## B049 - the exposure check found the doubled suffix all over again during verification

- **Cause:** the helper appends -basic itself, but the verify path was also appending it, so the folder became -basic-basic and the check flagged it
- **Fix:** stop appending the suffix in the verify path and let write_app own the name
- **Files:** verify_app.py
- **Check for recurrence:** recurs if the exposure check reports a duplicated slug
- **Status:** PROVEN

## B050 - the free edition published but the installer job had nothing to build

- **Cause:** verification committed its changes only on a later step the installer could not see, so the Windows job checked out a clean tree with no published.json
- **Fix:** commit and push the verified results from the verify job before the installer job starts
- **Files:** monday-verify.yml
- **Check for recurrence:** recurs if the installer job logs that nothing was published to build from
- **Status:** PROVEN

## B051 - the paid installer uploaded but the catalog commit was rejected

- **Cause:** the Windows job pushed without fetching first, so a concurrent runner's commit rejected it and the paid tier stayed marked unpublished
- **Fix:** fetch and rebase before every push in both installer commit steps
- **Files:** monday-verify.yml
- **Check for recurrence:** recurs if the installer logs a rejected push
- **Status:** PROVEN

## B052 - a generated concept shipped blurb='x' and tags=[], so store cards rendered with no description

- **Cause:** the generator's blurb and tags were written straight into the catalog with no validation, and a placeholder passed through unchanged
- **Fix:** validate blurb and tags at publish time and fall back to a deterministic sentence built from the app title; always lead tags with the product category
- **Files:** make_app.py
- **Check for recurrence:** recurs if any catalog entry has an empty blurb or an empty tags list
- **Status:** UNTESTED

## B053 - the store showed two separate cards because the basic tier carried base_slug 'password-manager-basic'

- **Cause:** publish() trusted an inherited base_slug, so the free and paid entries fell into different product families and each card offered only one tier
- **Fix:** strip a trailing tier marker from base_slug at publish time and fail check_exposure when a family is left with only one tier
- **Files:** make_app.py, check_exposure.py
- **Check for recurrence:** recurs if any product family has just one tier in site/apps.json
- **Status:** UNTESTED

## B054 - community ballot winners never reached the build step because the winner was stored as a display label and compared against slugs

- **Cause:** the winner was recorded as 'color picker' but make_app compared it to 'color-picker', so every vote was silently ignored
- **Fix:** store winner_slug when the ballot closes, and normalise labels to slugs when reading recent winners
- **Files:** discord_data.py, discord_polls.py
- **Check for recurrence:** recurs if a ballot closes but pick_concept does not mention the community vote
- **Status:** UNTESTED

## B055 - a tool that was already live was about to be generated again because data/already_built.json had lost its entry

- **Cause:** already_built.json is tracked in git, so a git reset reverted the record and the concept looked unbuilt
- **Fix:** merge the public catalog into load_built() so anything on the site counts as built regardless of the record
- **Files:** make_app.py
- **Check for recurrence:** recurs if a published product is missing from data/already_built.json
- **Status:** UNTESTED

## B056 - discord_setup_server.py created a second copy of every channel on each run, and deleted the copy it had just made

- **Cause:** discord.py caches the server's channels, so after creating a channel the cache was already stale and the next lookup could not see it
- **Fix:** rewrote the script on the plain REST API, where each call reads the server's real state, and matched categories and channels by name and position
- **Files:** discord_setup_server.py
- **Check for recurrence:** recurs if the layout matching goes back to reading a cache
- **Status:** PROVEN

## B057 - the setup script reported 'synced 0 command(s)' even though the slash commands were never registered

- **Cause:** discord.py's tree.sync(guild=...) returns an empty list for a server that was only fetched, so a successful sync and a failed one looked identical
- **Fix:** write the commands through the REST bulk endpoint and read them back, so the log shows what Discord really stored
- **Files:** discord_setup_server.py
- **Check for recurrence:** recurs if command registration reports a count without reading it back
- **Status:** PROVEN

## B058 - members could post in the bot's channels, because Send Messages was left out of the permission overwrite instead of being denied

- **Cause:** a bit missing from both allow and deny is inherited from the base role, and the base role in this server has Send Messages on
- **Fix:** deny Send Messages explicitly for @everyone in every bot channel
- **Files:** discord_setup_server.py
- **Check for recurrence:** recurs if a channel expects members to be read-only without an explicit deny
- **Status:** PROVEN

## B059 - the script could not tell whether the bot had the permissions it needed, and refused to run

- **Cause:** /users/@me/guilds/<id> returns 405 for an application token, so the check read an error body as zero permissions
- **Fix:** read the permissions from the bot's own role, which is returned by the roles endpoint
- **Files:** discord_setup_server.py
- **Check for recurrence:** recurs if the permission check uses an endpoint an application token cannot call
- **Status:** PROVEN

## B060 - re-running the setup script renamed leftover channels old-items, then old-old-items, then old-old-old-items

- **Cause:** the rename always prepended old- to whatever the current name was, including a name it had already renamed
- **Fix:** strip every existing old- prefix before adding one, so the name stays stable
- **Files:** discord_setup_server.py
- **Check for recurrence:** recurs if a rename builds the new name from the old one without normalising it first
- **Status:** PROVEN

## B061 - worker/wrangler.toml bound the KV namespace as KEYS while worker.js reads env.BUILDS, so a deploy from the repo would answer 'Store is not configured' and every paid download would 404

- **Cause:** the binding was renamed in the worker code but the manifest kept the old name, and nothing checked the two against each other
- **Fix:** bound the namespace as BUILDS in wrangler.toml with the same id paid_store.py uploads to
- **Files:** worker/wrangler.toml, worker/worker.js
- **Check for recurrence:** recurs if a worker binding is renamed in code but not in the manifest
- **Status:** PROVEN

## B062 - a second, stray ballot shadowed the live one, and closing the wrong ballot left the community vote unable to steer the build

- **Cause:** open_poll() returned the first open ballot it found, and close_ballot() always took that one, so a test ballot and the real one raced
- **Fix:** open_poll() returns the newest open ballot, and close_ballot() accepts a poll id so a specific one can be closed
- **Files:** discord_data.py, discord_polls.py
- **Check for recurrence:** recurs if more than one ballot is ever open at the same time
- **Status:** PROVEN

## B063 - Discord announcements and articles silently did nothing in CI, because every posting script only spoke to a webhook and the pipeline had no webhook

- **Cause:** each script carried its own webhook-only poster, so there was no path to Discord through the bot token the pipeline already had
- **Fix:** one discord_post.py now handles both transports, trying the webhook then the bot, and every posting script calls it
- **Files:** discord_post.py, discord_announce.py, discord_article.py, discord_polls.py
- **Check for recurrence:** recurs if a new script posts to Discord without going through discord_post
- **Status:** PROVEN

## B064 - discord_article.py read --dry-run as the product slug and refused to run

- **Cause:** the slug was taken from argv[1] without skipping flags
- **Fix:** take the first argument that is not a flag as the slug
- **Files:** discord_article.py
- **Check for recurrence:** recurs if an argument position is used for a value that also has flags
- **Status:** PROVEN

## B065 - the two leftover prototype channels could not be deleted, because Discord's Community mode pins the rules and system channels

- **Cause:** the server was set up as a Community server, which reserves two channels and refuses any delete on them
- **Fix:** turned Community mode off and set the server description, which released both channels
- **Files:** DISCORD_BOT_SETUP.md
- **Check for recurrence:** recurs if a server is a Community server and an automated job tries to tidy its channels
- **Status:** PROVEN

## B066 - the Discord bot posted nothing in CI, because every posting script required a webhook and the pipeline had only a bot token

- **Cause:** each script carried its own webhook-only transport with no shared fallback
- **Fix:** discord_post.py tries the webhook then the bot token, and resolves channels by name with the emoji prefix stripped
- **Files:** discord_post.py
- **Check for recurrence:** recurs if a channel is renamed for looks and lookup stops matching it
- **Status:** PROVEN

## B067 - retiring a product was impossible even after a year of no sales, because any sale at all blocked it forever

- **Cause:** the rule compared lifetime sales against zero, so one sale in five hundred days was treated as a reason to keep it
- **Fix:** allow at most two lifetime sales and none in the last 365 days, which is what 'nobody wants it' actually means
- **Files:** retire_product.py
- **Check for recurrence:** recurs if the retirement bar is stricter than the evidence warrants
- **Status:** PROVEN

## B068 - the self-upgrade pass threw away every good patch, because it treated the repository's own new files as a dirty tree

- **Cause:** it checked git status for the whole repository instead of only the files the patch had touched
- **Fix:** ask git about the patched paths alone, and keep a separate whole-tree check as the precondition
- **Files:** self_upgrade.py
- **Check for recurrence:** recurs if a cleanliness check is broader than the change it is judging
- **Status:** PROVEN

## B069 - the tests failed after the weekly cycle replaced the monthly workflows, because they named workflow files that no longer exist

- **Cause:** the test suite hard-coded monday-build.yml and monday-verify.yml
- **Fix:** the tests now discover the workflow files and require the four weekly stages to be present and to name the scripts they run
- **Files:** selftest.py, selftest_audit.py
- **Check for recurrence:** recurs if a workflow is renamed without updating what the tests check for
- **Status:** PROVEN

## B070 - the scheduled workflows were not protected, so the self-improvement job could have edited its own budget and schedule

- **Cause:** the guard listed only site/ and the site scripts; the workflow files were never added
- **Fix:** added the five scheduled workflows to the protected set, and fixed a matching bug where str.lstrip ate the dot in .github
- **Files:** weekly_guard.py, selftest_audit.py
- **Check for recurrence:** recurs if a new scheduled workflow is added without protecting it
- **Status:** PROVEN

## B071 - an edit to weekly_guard.py silently disappeared, because the upgrade test ran git checkout -- . over uncommitted work

- **Cause:** the self-upgrade test cleans the tree with a blanket checkout, which also reverts changes made in the same working copy beforehand
- **Fix:** the guard change was re-applied and committed before running the destructive test again
- **Files:** weekly_guard.py
- **Check for recurrence:** recurs when a destructive test runs while other edits are uncommitted
- **Status:** PROVEN

## B072 - the public repository tracked apps/, which held the complete native source of nine paid products including the full-edition launcher and installer script

- **Cause:** apps/ was the staging folder from the older itch.io era and was never added to .gitignore once the pipeline moved to paid/ and site/apps/
- **Fix:** untracked apps/ and every stale backup and scratch script, added them to .gitignore, and check_repo_hygiene.py now fails the build if any of them comes back
- **Files:** .gitignore, check_repo_hygiene.py
- **Check for recurrence:** recurs if a new staging folder is created and not added to .gitignore
- **Status:** PROVEN

## B073 - check_repo_hygiene.py crashed on a binary file in the git log because the console encoding could not decode it

- **Cause:** git output was decoded with text=True, which uses the console encoding and fails on non-UTF-8 bytes
- **Fix:** read git output as bytes and decode with errors='replace', since the history legitimately contains binaries
- **Files:** check_repo_hygiene.py
- **Check for recurrence:** recurs whenever subprocess output is assumed to be valid text
- **Status:** PROVEN

## B074 - voting by reaction could never work: Discord returns 405 for reading reactions over REST, and 404 for creating a native poll, so a scheduled job could not count a single vote

- **Cause:** the REST API will not let a bot read reaction counts at all, and the poll endpoint is not available to bots
- **Fix:** voting is by reply instead: the ballot is a message, members reply with a number, and Friday reads those replies over REST, which does work
- **Files:** discord_tally.py, discord_polls.py, discord_post.py
- **Check for recurrence:** recurs if a design assumes a bot can read reactions or create native polls over REST
- **Status:** PROVEN

## B075 - an earlier attempt at channel lookup stopped working entirely, and announcements would have posted nothing while CI carried on

- **Cause:** the emoji-tolerant find_channel was reverted when a destructive test ran git checkout over the uncommitted working tree
- **Fix:** re-applied the lookup and committed it before running any test that cleans the tree
- **Files:** discord_post.py
- **Check for recurrence:** recurs when a test that resets the tree runs while other edits are uncommitted
- **Status:** PROVEN

## B076 - the weekly cycle was rate limited by Discord partway through, so most channels never got their first message

- **Cause:** every channel lookup made its own call to the channel list, and a job touching nineteen channels tripped the per-route limit
- **Fix:** cached the channel list for a minute, and made the REST layer wait out a 429 instead of failing
- **Files:** discord_post.py
- **Check for recurrence:** recurs whenever a job makes many calls to the same route
- **Status:** PROVEN

## B077 - sixteen of nineteen channels were empty because nothing had ever posted an introduction

- **Cause:** the setup script built the structure but only the ballot and article scripts ever wrote to a channel
- **Fix:** discord_intro.py fills any empty channel, and both Monday and Friday run it so none can be empty again
- **Files:** discord_intro.py
- **Check for recurrence:** recurs if a new channel is added without an introduction
- **Status:** PROVEN

## B078 - renaming a channel to add an emoji orphaned its content and emptied it

- **Cause:** the intro script looked the channel up by its old name, so after a rename it found nothing and skipped posting
- **Fix:** channel lookup strips the emoji prefix and falls back through an alias map, so a rename cannot empty a channel
- **Files:** discord_post.py, discord_intro.py
- **Check for recurrence:** recurs if a channel is renamed without updating what looks it up
- **Status:** PROVEN

## B079 - the site had no way to take money at all, because PayPal live mode needs a Business account with a tax ID that does not exist

- **Cause:** the payment worker was the only checkout, and it depended on PayPal credentials that cannot be issued without a business account
- **Fix:** itch.io became the store: the catalog carries an itch_url, checkout.html forwards to it, and the worker, paid_store.py and full.html were deleted
- **Files:** ITCH_SELLING.md, set_itch_url.py, publish_paid.py, site/checkout.html
- **Check for recurrence:** recurs if a buy button is wired to an endpoint that does not exist
- **Status:** PROVEN

## B080 - the paid tier was still marked published even though nothing could be bought, so the site showed a buy button that led to a dead worker

- **Cause:** the flip used to happen the moment the build reached Cloudflare, and that pipeline no longer exists
- **Fix:** publishing is now manual and refuses unless an itch_url is already in the catalog
- **Files:** publish_paid.py, build_paid_only.py
- **Check for recurrence:** recurs if a product is shown for sale before its purchase link exists
- **Status:** PROVEN

## B081 - the site showed a buy button for a tool nobody could actually buy, because the paid tier was marked published with no store behind it

- **Cause:** publishing was flipped by the build step, which knew nothing about whether a purchase was possible
- **Fix:** itch_publish.py makes itch.io first and the site second: create, upload, verify the page answers, and only then publish
- **Files:** itch_publish.py, ITCH_SELLING.md
- **Check for recurrence:** recurs if anything marks a product as sold before the store has it
- **Status:** PROVEN

## B082 - itch.io looked automatable but cannot create a project at all: the API is read-only for games and butler refuses the first push

- **Cause:** itch.io only exposes reads plus collection editing; project creation is a browser page, so any plan to automate it has to drive a browser
- **Fix:** create the project with Playwright using a session cookie, then push the file with butler
- **Files:** itch_publish.py
- **Check for recurrence:** recurs if a plan assumes itch.io has a project-creation API
- **Status:** PROVEN

## B083 - the browser automation would never have logged in, because it set a cookie named itch.io while itch.io's session cookie is actually itchio_token

- **Cause:** the cookie name was guessed from the domain instead of read from a real request, and nothing tested it against a live login
- **Fix:** use itchio_token, accept either a bare value or a whole pasted Cookie header, and drop cf_clearance because it is bound to one IP and gets a runner blocked
- **Files:** itch_publish.py
- **Check for recurrence:** recurs if browser automation sets a cookie by guessing its name
- **Status:** PROVEN

## B084 - an expired itch.io session cookie would fail later as a confusing 'project was not created' rather than the truth

- **Cause:** the browser login was attempted first and its failure reported as a creation problem
- **Fix:** check the session before attempting anything, and pass butler the API key so uploading keeps working after the cookie expires
- **Files:** itch_publish.py
- **Check for recurrence:** recurs if an expired credential is only detected by the action that needed it
- **Status:** PROVEN

## B085 - the itch.io publisher would have uploaded one tool's installer under another tool's page, because it took whichever .exe it found first in a shared dist folder

- **Cause:** dist/ is shared between builds and the search had no name match, so invoice-maker's exe could be published as password-manager
- **Fix:** require a name match, prefer the exact stem, and prefer paid/<slug>/ when it exists
- **Files:** itch_publish.py
- **Check for recurrence:** recurs if a file is chosen from a shared folder without checking it belongs to the product
- **Status:** PROVEN

## B086 - the homepage showed 'The catalog loads on first build' to every visitor, so no app was listed at all

- **Cause:** groupProducts ended with key:k, but k is bound inside the forEach callback above it. The map callback that used it ran later, where k no longer existed, so it threw ReferenceError and took render() with it
- **Fix:** the family key is read from the pair itself, key:(full.base_slug||full.slug), which is always in scope where it is used
- **Files:** site/index.html
- **Check for recurrence:** site_js_selftest.py: the key:k pattern is refused, and the function is executed in a real browser against a two-entry catalog
- **Status:** UNTESTED

## B087 - clicking 'See options' on any product threw 'Unexpected end of input' and no purchase dialog would ever open

- **Cause:** the card button inlined JSON.stringify(item) into a double-quoted onclick attribute. The JSON contains double quotes, so the first one closed the attribute early and the browser parsed the rest as junk
- **Fix:** the button passes an index instead, openDialogByIndex(idx), and the handler looks the product up. No JSON is ever written into markup
- **Files:** site/index.html
- **Check for recurrence:** site_js_selftest.py: JSON.stringify must not appear in render()
- **Status:** UNTESTED

## B088 - the index passed to the card button came out as '$3.00' instead of a number

- **Cause:** render() already binds p to the formatted price string, so the interpolation wrote the price into the onclick where an index was meant to go, and openDialogByIndex looked up a product that does not exist
- **Fix:** the map callback takes (item, idx) and the button uses idx
- **Files:** site/index.html
- **Check for recurrence:** site_js_selftest.py: the button may not interpolate the price variable
- **Status:** UNTESTED

## B089 - there was no version anywhere: the installer hardcoded 1.0.0 and the catalog had no version field, so an installed app could not be compared with a published one

- **Cause:** version was written into three unrelated places and none of them read the others, so they disagreed as soon as anything shipped
- **Fix:** update_state.py is the only place a version is stored or changed, and every other script reads it
- **Files:** update_state.py, app_update.py
- **Check for recurrence:** update_selftest.py: the parse, bump and compare boundaries
- **Status:** UNTESTED

## B090 - a patch bump turned 1.9.9 into 1.9.0, which is older than what was already installed

- **Cause:** the bump added one to the last number, so any version ending in 9 or more carried backwards instead of forwards
- **Fix:** bump() parses into three integers and adds to the right one, so 1.9.9 becomes 1.9.10
- **Files:** update_state.py
- **Check for recurrence:** update_selftest.py: 1.9.9 plus a patch is 1.9.10
- **Status:** UNTESTED

## B091 - the update check said 1.10.0 was older than 1.9.0

- **Cause:** the versions were compared as strings, and '1.10.0' sorts before '1.9.0' alphabetically
- **Fix:** is_newer() compares parsed integer tuples
- **Files:** update_state.py, app_update.py
- **Check for recurrence:** update_selftest.py: 1.10.0 is newer than 1.9.0
- **Status:** UNTESTED

## B092 - an app that could not reach the update file would have had to show an error, breaking the promise that an app always opens

- **Cause:** the check reads a file that is generated at deploy time, so it is absent on a fresh machine and unreachable offline
- **Fix:** every failure path returns no banner instead of an error, and the check is off by default when switched off
- **Files:** app_update.py, native_launcher.py
- **Check for recurrence:** update_selftest.py: a missing public file is not a crash
- **Status:** UNTESTED

## B093 - an in-app update notice would have broken the promise that these apps never make network calls

- **Cause:** make_app.html_looks_fine rejects any app containing an external URL, and APP_SPEC says 'no network calls' twice. A fetch inside the app HTML would fail the build and break the privacy promise
- **Fix:** the check lives in native_launcher.py, which is the native shell and not the app, and injects the banner after load. The app HTML is unchanged and still passes html_looks_fine
- **Files:** app_update.py, native_launcher.py
- **Check for recurrence:** update_selftest.py plus the existing html_looks_fine check
- **Status:** UNTESTED

## B094 - every rebuild would stack another update banner on top of the last

- **Cause:** inject() ran on every build and appended unconditionally, leaving two elements with the same id and two visible banners
- **Fix:** the injected block is detected by its id and a second injection is refused
- **Files:** app_update.py
- **Check for recurrence:** update_selftest.py: injecting twice leaves exactly one banner
- **Status:** UNTESTED

## B095 - the app file was left corrupted when it had no <body>

- **Cause:** inject() assumed a body tag and sliced the string anyway
- **Fix:** a document with no body is refused and left untouched
- **Files:** app_update.py
- **Check for recurrence:** update_selftest.py: a page with no body is refused and unchanged
- **Status:** UNTESTED

## B096 - the homepage kept announcing a release that had already shipped

- **Cause:** the date was written into the page once and never cleared, so a committed countdown file survives indefinitely
- **Fix:** the countdown is generated during the Pages deploy from the live state and is never committed. Outside the announcement window the file carries no date at all, so the banner hides itself
- **Files:** update_state.py, .github/workflows/pages.yml
- **Check for recurrence:** update_selftest.py: idle and live both publish a null date
- **Status:** UNTESTED

## B097 - the Discord event id and other internal state were one copy-paste away from being published on the public site

- **Cause:** update.json is served to everyone, and it is written from the same state file that holds internal ids
- **Fix:** the published file is built field by field and never copies the raw state
- **Files:** update_state.py
- **Check for recurrence:** update_selftest.py: no event id appears in the published file
- **Status:** UNTESTED

## B098 - the countdown banner could have broken the homepage

- **Cause:** a broken or missing update.json would leave the fetch rejecting, and a throw inside that handler could stop the page rendering
- **Fix:** every step is guarded and the catch is empty, so the banner stays hidden and the rest of the page is unaffected
- **Files:** site/index.html
- **Check for recurrence:** site_js_selftest.py: the fetch has an empty catch and escapes its text
- **Status:** UNTESTED

## B099 - a release could be planned for a date that had already passed, which would skip the countdown entirely

- **Cause:** the 26th was used as a fixed day, so planning on the 28th produced a date in the past and the phase went straight to live
- **Fix:** target_date() rolls forward a whole month until there are at least ten days left
- **Files:** update_plan.py
- **Check for recurrence:** update_selftest.py: planning on the 27th and the 31st both roll forward
- **Status:** UNTESTED

## B100 - a month could have no plan at all, because the plan depended on the model being reachable

- **Cause:** the only source of the theme was a model call, and the account runs out of credits regularly
- **Fix:** there is a fixed menu of themes that can actually be built, and the model may only choose from it. If the model cannot be reached the menu decides instead
- **Files:** update_plan.py
- **Check for recurrence:** update_selftest.py: fallback lands on the menu and avoids repeats
- **Status:** UNTESTED

## B101 - the trailer could advertise a feature nobody built

- **Cause:** the model was free to invent a theme, and a title it wrote would become a promise in a video
- **Fix:** an id that is not on the menu is discarded rather than trusted, so only buildable themes ever reach the script or the trailer
- **Files:** update_plan.py, update_trailer_script.py
- **Check for recurrence:** update_selftest.py: the fallback and the menu agree
- **Status:** UNTESTED

## B102 - re-running the announce step would create a second Discord event for the same release

- **Cause:** events are created by POST and have no natural key, so a retried job makes another one
- **Fix:** the event id is stored in the update state and reused; a stored id that no longer exists falls through to creating a fresh one rather than wedging the release
- **Files:** update_discord.py
- **Check for recurrence:** update_selftest.py: existing() reads the stored id
- **Status:** UNTESTED

## B103 - the weekly patch lane could have announced itself alongside a major release

- **Cause:** both write the same state file, and the weekly ran whatever day it fell on
- **Fix:** the weekly refuses to run while a major is already in the announced phase
- **Files:** update_weekly.py
- **Check for recurrence:** checked by hand: with a major three days out the weekly exits without bumping
- **Status:** UNTESTED

## B104 - a weekly release would have been announced as a major change

- **Cause:** both lanes bumped the same version field with no distinction recorded
- **Fix:** the weekly is hard coded to a patch bump, and update_selftest.py checks that major and minor are left alone
- **Files:** update_weekly.py
- **Check for recurrence:** update_selftest.py: 1.4.2 becomes 1.4.3 and never 1.5.0 or 2.0.0
- **Status:** UNTESTED

## B105 - the trailer could not reuse the Shorts renderer, because that file is pinned to a 1080x1920 phone frame

- **Cause:** W and H are module level constants used by every gradient, band and merge in shorts_render, so a landscape frame silently breaks them
- **Fix:** update_trailer_render.py draws its own landscape background and uses shorts_render only for helpers that take no size: font, wrap, ease, the logo and the screenshots
- **Files:** update_trailer_render.py
- **Check for recurrence:** update_selftest.py: the trailer is landscape and the Shorts is not
- **Status:** UNTESTED

## B106 - the trailer's headline was drawn twice, once as a shadow at the wrong offset, so a ghost of it showed through

- **Cause:** the shadow was drawn at a different y from the fill, so the two layers did not line up
- **Fix:** the shadow offsets are applied to the same position the fill uses
- **Files:** update_trailer_render.py
- **Check for recurrence:** checked visually across four timestamps
- **Status:** UNTESTED

## B107 - the app card sat on top of the trailer's headline and narration

- **Cause:** the card position was computed from the canvas centre while the text was wrapped to a width that assumed a much narrower frame
- **Fix:** the frame is a fixed two-column split: the card owns the right, the text is wrapped to the space on the left of it
- **Files:** update_trailer_render.py
- **Check for recurrence:** update_selftest.py: every frame renders at the canvas size, and the split was checked visually
- **Status:** UNTESTED

## B108 - the voiceover would have read '[upbeat music]' out loud

- **Cause:** the model returns stage directions and markdown often enough to matter, and the synthesiser speaks whatever it is given
- **Fix:** leading cues and markdown are stripped from every line before it is written
- **Files:** update_trailer_script.py
- **Check for recurrence:** update_selftest.py: a leading cue and bold markers are removed
- **Status:** UNTESTED

## B109 - shorts_script_selftest.py crashed with TypeError: sequence item 4: expected str instance, list found

- **Cause:** the test joined every value in the returned dict, and _clean now returns a 'tour' list alongside the string fields, so the join had a list in it
- **Fix:** the test joins only the string values, which is what it meant to check
- **Files:** shorts_script_selftest.py
- **Check for recurrence:** the suite runs to completion again
- **Status:** UNTESTED

## B110 - the release workflows were not protected from the self-improvement job

- **Cause:** PROTECTED_WORKFLOWS listed the four original workflows, so a job that could edit its own schedule could edit these two as well
- **Fix:** both new workflows are in PROTECTED_WORKFLOWS and selftest_audit.py asserts they are protected
- **Files:** weekly_guard.py, selftest_audit.py
- **Check for recurrence:** selftest_audit.py: both are checked as protected
- **Status:** UNTESTED

## B111 - counting the weekly ballot crashed with NameError when the bot could not read a channel

- **Cause:** the 403 branch logged an undefined name. The parameter is called channel, and name was left over from an older signature, so the graceful empty-list path was itself the thing that threw
- **Fix:** the branch logs the channel it actually failed to read, and every status now returns an empty list instead of raising
- **Files:** discord_post.py
- **Check for recurrence:** checked by hand: 403, 200, 500 and 429 all return cleanly now
- **Status:** UNTESTED

## B112 - the live key checker raised UnboundLocalError the instant it was run, so it never tested anything

- **Cause:** main() read _KEY and then assigned to it in the same function. That assignment made _KEY local, so the read above it had no value to come from
- **Fix:** the key arrives as a parameter, so there is nothing to shadow and the function reads only what it is given
- **Files:** groq_live_check.py
- **Check for recurrence:** checked by hand: empty key, wrong prefix and a fake key all return the right thing instead of crashing
- **Status:** UNTESTED

## B113 - re-enabling the video captions would have crashed the renderer with NameError on every frame

- **Cause:** caption() positioned itself with BAND_CAPTION, which was deleted when captions were removed from the videos. Nothing calls caption() so it sat there as dead code with a name that no longer exists
- **Fix:** the function was deleted rather than given a band, because captions are not wanted and a resurrected band would be a guess
- **Files:** shorts_render.py
- **Check for recurrence:** pyflakes reports no undefined names anywhere in the project
- **Status:** UNTESTED

## B114 - a release could have been planned for a date that had already passed

- **Cause:** the plan wrote a fixed day of the month, so planning near the end of a month produced a date behind us and the countdown was skipped entirely
- **Fix:** this was caught and fixed with the release lane and is listed there again for completeness
- **Files:** update_plan.py
- **Check for recurrence:** update_selftest.py: planning on the 27th and the 31st roll forward
- **Status:** UNTESTED

## B115 - every Friday build waited for the model allowance even when there was almost nothing spent, and the check it computed was never used

- **Cause:** the loop waited whenever spent() was greater than zero, so ten tokens used meant waiting out the clock with seven thousand left. The limit and need were calculated and then discarded
- **Fix:** the loop asks tokenmeter.affordable(limit, need), which is the function that already existed for exactly this, and says so out loud when it starts anyway
- **Files:** stage_app.py
- **Check for recurrence:** tokenmeter.affordable is asserted directly in selftest.py
- **Status:** UNTESTED

## B116 - the coach's list of lessons to keep was calculated and then thrown away, so the model and the file could disagree

- **Cause:** the prompt asks for keep, add and drop, but only drop was honoured: the carried-over list was rebuilt by subtraction instead of taking the model's own answer
- **Fix:** keep wins when the model supplies it, and the subtraction is the fallback for when it does not
- **Files:** learn.py
- **Check for recurrence:** both branches log which one was used, so a run shows it
- **Status:** UNTESTED

## B117 - a run that could not build an app burned its allowance walking the whole model list on every single call

- **Cause:** the function declared global CHAT_MODEL and then only ever read it. A dead global like that is the fossil of a caching step, and without it a rate limited first model is retried before every generation
- **Fix:** the model that answered is remembered and tried first next time, so the run stops paying for models that have already failed
- **Files:** make_app.py
- **Check for recurrence:** checked by hand with a stubbed provider: the second call goes straight to the working model
- **Status:** UNTESTED

## B118 - every Wednesday run would have deleted all 110 recorded bugs

- **Cause:** learn.py and buglog.py both wrote data/lessons.txt in different formats. buglog appends a line per entry, learn.py rewrites the whole file, so whichever ran last destroyed the other
- **Fix:** the coach writes its own file. The fixbook keeps lessons.txt, and the two records can no longer touch each other
- **Files:** learn.py, .gitignore
- **Check for recurrence:** learn.LESSONS and buglog.LESSONS are asserted to be different files
- **Status:** UNTESTED

## B119 - importing any module could create site/licenses, which GitHub Pages would then serve and which fails the exposure check

- **Cause:** paypal.py called LICENSE_DIR.mkdir() at module scope, and paypal_check.py imports it at module scope too. The folder is gitignored, so it never showed up in a diff, but Pages serves the working tree and check_exposure.py refuses the whole site when that folder exists, so an import could fail the release gate on its own
- **Fix:** the mkdir moved into save_key, where something is actually written, so importing and reading no longer touch the published site
- **Files:** paypal.py
- **Check for recurrence:** scan_selftest.py imports every module in a fresh interpreter and fails if anything new appears under site/
- **Status:** UNTESTED

## B120 - the check that stopped an automated job committing a protected file never asked the guard, so it flagged workflows that merely mentioned one and passed ones that staged one

- **Cause:** weekly_guard was imported as _guard and then never called. The check was a substring test for a protected filename anywhere in the file, including inside comments, which is why the release workflow tripped it
- **Fix:** the guard is actually asked about every path a blanket git add stages, so the rule and the enforcement cannot drift apart
- **Files:** selftest_audit.py
- **Check for recurrence:** checked by hand: a comment naming a protected file passes, a real blanket add of one is reported
- **Status:** UNTESTED

## B121 - weekly review 2026-W42: 0 order(s), $0.00, 0 star(s), 0 vote(s) on the open ballot

- **Cause:** ## What happened
- **Fix:** read data/weekly_reviews.json before the next build; it carries this week's numbers and what to change
- **Files:** data/weekly_reviews.json, weekly_review.py
- **Check for recurrence:** recurs every Wednesday; one entry per week is expected
- **Status:** UNTESTED

## B122 - nothing has ever been buyable: the paid edition is marked published but has no itch_url, so the buy button leads nowhere

- **Cause:** itch_url has never been set in this repository's history. publish_paid.py refuses to publish without one, but nothing checked the flag that was already there, so a published-but-unbuyable product sat there indefinitely and no gate noticed
- **Fix:** check_exposure.py now reports any published paid edition with no itch_url. It is a warning rather than a failure by default, because nothing is leaking and fixing it needs one person to open a page; --strict makes it fatal
- **Files:** check_exposure.py, signals.py
- **Check for recurrence:** check_exposure.py prints the slug and the command that fixes it, and exits 1 under --strict
- **Status:** UNTESTED

## B123 - the paid build on this machine is a 59-byte placeholder, not an app

- **Cause:** paid/password-manager/app/index.html holds a single localStorage assignment. Nothing verifies that a paid build is a real application before the catalog calls it built
- **Fix:** reported rather than papered over: it is local and gitignored, so it was never published, but it means the paid edition has never actually been built and cannot be sold as it stands
- **Files:** itch_publish.py
- **Check for recurrence:** no automatic check yet; signals.py reports catalog_on_sale, which is 0 until an itch_url exists
- **Status:** UNTESTED

## B124 - conversion was reported as zero percent while five sales were recorded

- **Cause:** conversion() read the sales count from itch.io, which only returns one when ITCH_API_KEY is present. Without it the count was 0, and the recorded order count was fetched and then never used
- **Fix:** the order count stands in when itch has no sales of its own, and the result records which source it came from so the two can be compared
- **Files:** signals.py
- **Check for recurrence:** growth_selftest.py: five orders against two hundred visits is 2.5%, and itch's own figure still wins when it has one
- **Status:** UNTESTED

## B125 - the daily lane assumed two APIs that do not exist

- **Cause:** improve_daily called budget.affordable, which budget.py never had, and passed an argument to self_upgrade.main, which takes none. Both raised and were swallowed by the same handler, so the lane logged a failure and moved on every day without ever improving anything
- **Fix:** budget.remaining() is the real call and self_upgrade.main() takes no argument. The caught-and-carried-on handler stays, because a failing improver must not fail the job
- **Files:** improve_daily.py
- **Check for recurrence:** the lane runs and reports a real reason instead of an AttributeError
- **Status:** UNTESTED

## B126 - the self-improvement gate did not know about the new lanes

- **Cause:** TEST_SUITE was four scripts. A generator patch could have broken the thumbnail layout, the release countdown or the homepage JavaScript and still counted as an improvement, because none of those were in the suite that decides whether to keep it
- **Fix:** TEST_SUITE now includes every lane's selftest plus the link and exposure checks, so a patch that renders a broken card is discarded
- **Files:** self_upgrade.py
- **Check for recurrence:** self_upgrade.TEST_SUITE is checked against the filesystem at runtime
- **Status:** UNTESTED

## B127 - nothing stopped a self-improving job from rewriting the goal it is measured against

- **Cause:** the guard protected prices and the site but not goals.py or signals.py, so the lane could have edited the standard it is judged on, which is the same failure as a job that raises its own price ceiling
- **Fix:** goals.py, signals.py and improve_daily.py are in MONEY_AND_DEATH for the same reason pricing.py is, and selftest_audit asserts it
- **Files:** weekly_guard.py, selftest_audit.py
- **Check for recurrence:** selftest_audit.py: each of them is checked as protected
- **Status:** UNTESTED

## How to use this

1. If the symptom matches an entry, use that fix. Do not invent a new one.
2. If it does not match, treat it as new: diagnose it, then record it with
   `buglog.record(symptom, cause, fix, files, detects)` so it is here next time.
