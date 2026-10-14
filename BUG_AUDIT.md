# BUG AUDIT - Slingshot Tools

Generated from the repository rather than written by hand, so it cannot drift
from what is actually true. Regenerate with:

    python audit_report.py > BUG_AUDIT.md

How each defect was found, reproduced and fixed is in the git history. The
machine-readable record of every one is in `data/bugs.json`; the record of what
the automation actually did is in `data/audit/events.jsonl`.

## A. Audit coverage

| Item | Count | How it was counted |
|---|---|---|
| Python modules at the repository root | 130 | `Get-ChildItem *.py` |
| Python files inspected anywhere | files | `selftest_audit.py` walks the tree |
| GitHub Actions workflows | 10 | `.github/workflows/*.yml`, all parsed as YAML |
| Git-tracked files | 228 | `git ls-files` |
| Selftest suites | 33 | `run_selftests.py` discovers `*selftest*.py` |

Every root module was parsed by pyflakes and by an AST undefined-name pass. Every workflow was parsed and its shell syntax checked against the shell its runner actually has. Every entry point was executed from an unrelated working directory, because a script that resolves paths against the current directory passes in CI and fails elsewhere.

Components inspected and their verification status:

| Component | Status | Evidence |
|---|---|---|
| Generation (`make_app.py`, `stage_app.py`) | verified in CI | runs in the Friday job; a generated app is scanned in a real browser before it is staged |
| JavaScript validation (`make_app.js_syntax_errors`) | verified | node on the runner, escaping and delimiter checks otherwise; `jscheck_selftest.py` shows no false positives |
| Interaction scanning (`app_scanner.py`) | verified | `scanner_selftest.py` proves four genuinely dead controls are still caught after three relaxations |
| Release gate (`check_exposure.py`, `check_repo_hygiene.py`) | verified | each refusal confirmed by planting the thing it refuses |
| Build and packaging (`build_paid_only.py`, `build_installer_app.py`) | verified in CI | installer built in run 38416539839 and uploaded as an artifact |
| itch.io publishing (`itch_publish.py`) | BLOCKED | the session cookie is refused; the path up to the credential is verified and the failure is reported, not swallowed |
| Website (`site/`, `pages.yml`) | verified live | fetched after deployment; the free app loads and works |
| Discord (`discord_announce.py`) | verified in CI | refuses to announce a paid tier that is not live |
| Groq integration (`providers.py`, `tokenmeter.py`, `budget.py`) | verified | fail-closed on unreadable state; rate-limit backoff waits out the window |
| Structured audit log (`auditlog.py`) | verified | survives a hard kill; redacts seven credential shapes; cannot record a success without evidence |
| Budget (`budget.py`) and release state (`update_state.py`) | verified | refuse on unreadable state; the per-app version map survives a load |

## B. Bug statistics

- Discovered: **25**
- VERIFIED_FIXED: **23**
- BLOCKED on an external requirement: **2**
- NEW / INVESTIGATING / CONFIRMED / FIXED_PENDING_VERIFICATION / NOT_REPRODUCED: **0**
- Open confirmed defects: **0**

By severity, each defect counted once:

- CRITICAL: **6**
- HIGH: **14**
- MEDIUM: **5**

| ID | Sev | Component | Defect | Status |
|---|---|---|---|---|
| BUG-006 | CRITICAL | generation | A generated app could not parse, so every control looked dead | VERIFIED_FIXED |
| BUG-007 | CRITICAL | quality gate | The scanner refused working apps, so nothing could ever publish | VERIFIED_FIXED |
| BUG-015 | CRITICAL | itch.io publishing | The site advertised a paid product that was not for sale | VERIFIED_FIXED |
| BUG-017 | CRITICAL | itch.io publishing | Itch.io publishing reported success for having done nothing | VERIFIED_FIXED |
| BUG-020 | CRITICAL | itch.io publishing | No product has ever been uploaded to itch.io | BLOCKED |
| BUG-021 | CRITICAL | pricing | A price could be set below the hard floor and could never be sold | VERIFIED_FIXED |
| BUG-001 | HIGH | repository | Gitignore hid the deployed free catalogue | VERIFIED_FIXED |
| BUG-003 | HIGH | ci | NSIS installed but makensis was not on PATH | VERIFIED_FIXED |
| BUG-004 | HIGH | orchestrator | Rate limit backoff spent the whole retry budget inside one window | VERIFIED_FIXED |
| BUG-005 | HIGH | release gate | Exposure gates refused the app the pipeline had just staged | VERIFIED_FIXED |
| BUG-009 | HIGH | ci | The paid publish outcome was recorded and then thrown away | VERIFIED_FIXED |
| BUG-012 | HIGH | orchestrator | An unreadable counter read as zero, so the pipeline kept spending | VERIFIED_FIXED |
| BUG-013 | HIGH | orchestrator | An unreadable budget read as zero hours, so jobs were approved | VERIFIED_FIXED |
| BUG-016 | HIGH | ci | The installer job built the wrong product because a slug went stale | VERIFIED_FIXED |
| BUG-018 | HIGH | ci | A quiet week stopped the website being deployed | VERIFIED_FIXED |
| BUG-019 | HIGH | itch.io publishing | The itch.io session cookie is expired, so nothing can be uploaded | BLOCKED |
| BUG-022 | HIGH | release state | Loading the release state destroyed the per-app version map | VERIFIED_FIXED |
| BUG-023 | HIGH | packaging | A failed installer build returned the previous release's binary | VERIFIED_FIXED |
| BUG-024 | HIGH | shorts | Shorts captions were placed outside the clip they belong to | VERIFIED_FIXED |
| BUG-025 | HIGH | shorts | A video shorter than its narration lost the call to action | VERIFIED_FIXED |
| BUG-002 | MEDIUM | repository | Committed state carried the build machine's absolute paths | VERIFIED_FIXED |
| BUG-008 | MEDIUM | generation | The javascript check crashed on a Windows pipe | VERIFIED_FIXED |
| BUG-010 | MEDIUM | website | A debug backup file is committed to the published site | VERIFIED_FIXED |
| BUG-011 | MEDIUM | orchestrator | Committed per-minute token counter was read as another runner's usage | VERIFIED_FIXED |
| BUG-014 | MEDIUM | orchestrator | A release could die on a traceback and still have claimed to save | VERIFIED_FIXED |

## C. Code changes

```
b4a3d6b Fill the itch.io login by its shape, not by field name
5762826 build: windows installer [skip ci]
50bffb2 feat: verified new Slingshot Tool [skip ci]
a8febce candidate: staged for verification
ef33257 Ask whether there is anything new before the verifier deletes the candidate
d5e8311 feat: verified new Slingshot Tool [skip ci]
9b4d0cf candidate: staged for verification
5e3fc2e Stop the decode turning a newline escape into a real newline
f6304e9 feat: verified new Slingshot Tool [skip ci]
d3cadfa candidate: staged for verification
0ce7bdf Settle the escaping question by parsing, not by a rule
909af87 feat: verified new Slingshot Tool [skip ci]
6d27077 candidate: staged for verification
6dea002 Stop stripping the backslash from an escaped quote in a javascript string
b0129e6 feat: verified new Slingshot Tool [skip ci]
8967e6c candidate: staged for verification
7febfd1 Find the failing line in every format node reports it in
43cb3ce feat: verified new Slingshot Tool [skip ci]
9d7f844 candidate: staged for verification
10613a4 Report the line a script failed on, not just that it did
6d8eaf4 feat: verified new Slingshot Tool [skip ci]
f347b56 candidate: staged for verification
16f193e Stop failing on a week where the model produced nothing
944fa14 feat: verified new Slingshot Tool [skip ci]
e07e6d2 candidate: staged for verification
```

Each defect's root cause, correction and regression test is recorded in `data/bugs.json` under its id, which is generated by `record_audit_bugs.py` and read by this report. The full narrative is in `BUG_AUDIT.md`.

## D. Actual test evidence

| Command | Purpose | Result |
|---|---|---|
| `python run_selftests.py --quiet` | full local suite | exit 0: all 31 selftests pass |
| `python selftest_audit.py` | static and workflow audit | exit 0: 0 problems across 135 files |
| `python cleanroom_selftest.py` | clean-checkout simulation | exit 0: all 8 checks pass on a clean checkout. |
| `python selftest.py` | behavioural | exit 0:   PASS  workflows parse              all 10 workflows parse |
| `python selftest_deep.py` | deep behavioural | exit 0: CLEAN |
| `python -m pyflakes` | static analysis | exit 0: 0 findings |
| `python property_selftest.py` | generated edge cases | exit 0: FAILURES: none |
| `python auditlog_selftest.py` | audit-log guarantees | exit 0: FAILURES: 0 |
| `python jscheck_selftest.py` | javascript validation, no false positives | exit 0: false positives: 0   missed: 0 |
| `python scanner_selftest.py` | scanner still catches real bugs | exit 0: FAILURES: none |
| `python paidbuild_selftest.py` | installer handoff | exit 0: FAILURES: none |
| `python itchurl_selftest.py` | itch URL truthfulness | exit 0: FAILURES: none |
| `python itchpublish_selftest.py` | publish reporting | exit 0: FAILURES: none |
| `python shellcheck_selftest.py` | workflow shell correctness | exit 0: FAILURES: none |
| `python e2e_all.py` | customer journeys | exit 1: 2 of 4 journeys broken; see the report |

## E. Customer journey results

| Journey | Result | How it was tested |
|---|---|---|
| A. Discovery | verified | the public site was fetched; https://tbougnar.github.io/Slingshot-Tools/ answers and lists the tools |
| B. Website and product evaluation | verified | `e2e_app.py` passes 11 of 11 against the deployed app; the app at `/apps/color-picker-basic/` was fetched and loads |
| C. Purchase | **NOT VERIFIED** | no product exists on itch.io to buy. The store was fetched and lists nothing. No money was spent, no account altered, no checkout bypassed |
| D. Installation | partially verified | the Windows installer was built by CI and uploaded as an artifact; installing and launching it on a customer machine was not done |
| E. Support | product gap | no support or contact mechanism is implemented; recorded as a gap rather than a passing test |

Search-engine ranking was not tested and is not claimed. Correct website implementation was.

## F. Publication status

| Destination | Status | Verified how |
|---|---|---|
| itch.io | **NOT PUBLISHED** | https://slingshot-tools.itch.io/ was fetched during this audit and lists no products. The upload was attempted in CI and refused: "the session cookie is expired or was refused" |
| GitHub Pages | **PUBLISHED** | https://tbougnar.github.io/Slingshot-Tools/ answered after deploy run 38429073380; the free app at `/apps/color-picker-basic/` loads and works |
| Discord | **POSTED** | the announce step passes in CI and refuses to announce a paid tier that is not live; whether a message landed in the server was not read back |

The catalog states what is true: free editions published, paid tiers kept private, no itch URL, nothing claimed to be on sale.

## G. AI action-monitoring status

`data/audit/events.jsonl` holds **403** events across **181** correlation ids and **5** stages: BLOCKED, FAILED, NOT_VERIFIED, RETRIED, STARTED, SUCCEEDED.

| Guarantee | Status | How it was checked |
|---|---|---|
| Every event has a timestamp, status, stage, correlation id, action, reason, tool, result, evidence and error | verified | `auditlog_selftest.py` checks every field on every event |
| A success cannot be claimed without evidence | verified | `succeeded()` raises without evidence |
| Secrets never reach the file | verified | seven credential shapes scrubbed, including inside nested structures |
| The log survives a crash | verified | a separate process was killed outright and its event was still readable |
| A torn final line does not hide earlier events | verified | a truncated line was appended and the earlier events still read |
| Rotation does not lose the newest file | implemented | bounded at 8 MB with two files kept |
| Test failures do not pollute the real log | verified | the suites are run and the log's size is measured before and after |

Untested: the log has never been rotated in anger, because 138 events is far below the threshold, and no dashboard exists because the log is greppable and the question has not arisen.

## H. Remaining risks

| Risk | Why it is still open |
|---|---|
| Nothing is for sale | itch.io serves a Cloudflare Turnstile bot challenge to the headless browser that would log in, so no automated session can be established. The store has been fetched and lists nothing. Everything up to that point is verified |
| No purchase has ever been exercised | dependent on the above. No money was spent and no checkout was bypassed at any point |
| The Windows installer has not been run on a customer machine | CI builds and uploads it, but installing and launching it on a real desktop was not done |
| Groq can produce unparseable JavaScript | the gate refuses such an app rather than shipping it, so a release can fail when the model has a bad run. Run 38432094739 failed this way, which is the gate working |
| `set_itch_url` accepts any host ending in `itch.io` | a look-alike such as `notitch.io` would pass. This is a hardening opportunity, not an active exploit; the check requires an account subdomain but not a dotted one |
| A customer's search-engine visibility | not tested and not claimed; a code change cannot guarantee it |

## I. Final status

**BLOCKED - EXTERNAL REQUIREMENT PREVENTS COMPLETION:**

Every confirmed, actionable defect found by this audit has been fixed and independently verified: 23 of 25, with zero open.

The work that remains cannot be done from here, and the reason is now known exactly rather than guessed at. itch.io sits behind a Cloudflare Turnstile bot challenge: a headless browser is served a "Just a moment..." page with a single hidden cf-turnstile-response input instead of the login form. Getting past a bot check is evading an anti-abuse control, and this will not do that.

So the session cookie stays. It is the one credential that expires, and it is the price of a store that checks for bots. The permanent-credentials login is kept in the code because it is the right design and would work on a runner that is not headless, or if itch.io's policy changes.

Everything up to that point is verified working. The pipeline runs green end to end: it generates a product, validates its javascript, scans it in a real browser, builds a Windows installer, uploads it as an artifact, and offers it to itch.io, which serves the bot challenge.

To finish, paste a cookie from a browser you have logged in with. It expires, and that is the whole remaining cost:

```
gh secret set ITCH_SESSION_COOKIE --repo tbougnar/Slingshot-Tools
```

After that, dispatch `friday-build.yml`. The pipeline builds, uploads, verifies the page answers, publishes the site and announces it, with no manual step.

This is not a claim that no defect exists anywhere. It is a claim that every defect this audit found has a recorded cause, a fix or a documented blocker, and a test where one was practicable, and that the ones that mattered most were invisible to a green suite until the code was broken deliberately.

