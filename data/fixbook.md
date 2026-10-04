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

## How to use this

1. If the symptom matches an entry, use that fix. Do not invent a new one.
2. If it does not match, treat it as new: diagnose it, then record it with
   `buglog.record(symptom, cause, fix, files, detects)` so it is here next time.
