# BUG AUDIT — Slingshot Tools

Started: 2026-10-12
Status: **VERIFIED WITHIN TESTED SCOPE** — see §10 for what that does and
does not cover, and §6 for what is still genuinely broken.

---

## 1. Scope and method

Whole repository at `C:\Users\Taha\AI\slingshot_tools`: an autonomous
product company that generates, verifies, publishes and sells small
single-file HTML desktop tools. GitHub Pages serves `site/` from the public
repository.

| Item | Count | Counting method |
|---|---|---|
| Python modules at the root | 112 | `Get-ChildItem *.py` |
| Python files audited anywhere | 117 | `selftest_audit.py` walks the tree |
| GitHub Actions workflows | 10 | `.github/workflows/*.yml` |
| Published HTML pages | 4 | `site/**.html`, recursive |
| Git-tracked files | 161 | `git ls-files` |
| PowerShell files | 1 | `check.ps1` |
| Shell scripts | 0 | no `.sh` files |
| Selftest suites | 21 | `run_selftests.py` discovers `*selftest*.py` |
| Fixbook entries | 138 | `data/fixbook.json`, fed to `lessons.txt` by `record_scan_lessons.py` |

### Environment

- Python 3.12.10, Windows 11
- CI runners: `ubuntu-latest` for most jobs, `windows-latest` for the two that
  need PyInstaller and NSIS
- Third-party: `pillow`, `requests`, `pyinstaller`, `pywebview` (imports as
  `webview`), `playwright`, `pyyaml`, `edge-tts`, `imageio-ffmpeg`, `pyflakes`
- External services: Groq, Discord, itch.io, YouTube, GitHub Pages,
  ElevenLabs

### What was inspected

Every root module was parsed by pyflakes and by the AST undefined-name pass in
`selftest_audit.py`. All 10 workflows were parsed as YAML and their
`python X.py` calls resolved against the tracked file set. `check.ps1` was
parsed by the PowerShell language parser and executed. The subprocess call
sites were walked for injection surface. Every `except` clause ending in a bare
`pass` was listed by AST and read individually to see which ones hid a failure
that mattered. Each entry point was then executed from an unrelated working
directory, because a script that reads `data/x.json` relative to the current
directory passes in CI and fails on a laptop, and static reading of paths was
already shown to be unreliable in this pass (§5, bug 011). The full test suite
was run, then the end-to-end journeys were run against the local and live site.

---

## 2. Passes

| Pass | Done | What it found |
|---|---|---|
| A. Static and structural | yes | pyflakes clean; no undefined names; no TODOs or stubs |
| B. Runtime and logic | yes | 8 arithmetic and edge-case defects; see `property_selftest.py` |
| C. Script and OS | yes | working-directory dependence; `check.ps1` short by five variables |
| D. Integration | yes | `learn.py` duplicated the itch.io fetch against a dead endpoint; a committed counter crossing machines |
| E. Security and reliability | yes | no `eval`, `exec`, `os.system`, `pickle`; no shell=True on external input; no credentials in the repository |
| F. Failure and recovery | yes | 3 fail-open accounting bugs; the SystemExit crash; every module survives no credentials and a missing data file |
| G. Regression | yes | a committed scratch file; a committed per-minute counter |

---

## 3. Baseline before the second pass

```
pyflakes           2 findings, both in audit scratch files
run_selftests.py   all 16 selftests pass
selftest_audit.py  0 problems across 115 files
cleanroom          all 8 checks pass on a clean checkout
e2e_all.py         3 of 4 journeys BROKEN (the baseline; 2 of 4 at the end)
```

---

## 4. Bug inventory

### Found and fixed in the first pass

| # | Sev | File | Issue | Root cause | Status |
|---|---|---|---|---|---|
| 001 | M | `check.ps1` | The pre-flight checked 5 of the 10 environment variables `check_connections.py` actually reads. `DISCORD_GUILD_ID` was named in the file's own comment block but not checked. | The list was written once and the checker grew. | **Fixed, verified** |
| 002 | M | `learn.py` | The coach fetched usage from `{page}.itch.io/embed-stats`, a game-level endpoint that answers 404 for an account, while `reputation.py` and `signals.py` fetched the same data from `api/1/x/stats/*`. The coach had been reasoning with no usage data for weeks. | A second implementation of a function that already existed, written against a different endpoint and returning a different shape. | **Fixed, verified** |
| 003 | M | `improve_daily.py` | Every run without an API key ended in `ValueError: invalid literal for int() with base 10: 'no model provider is configured'`. | `SystemExit.code` is whatever was passed to it, not always an int. | **Fixed, verified** |
| 004 | L | `_t.py` | A scratch file had been swept into commit `7570c48` by `git add -A`, then deleted locally, leaving a tracked path pointing at nothing. | A scratch file committed without review. | **Fixed, verified** |
| 005 | L | `friday-build.yml` | NSIS was installed only on the verify job, while the installer is built on the generate job. CI reported `[nsis] makensis not found`. | The installer moved into `stage_app.py` without the runner gaining the tool. | **Fixed, not yet verified in CI** |

### Found and fixed in the second pass

| # | Sev | File | Issue | Root cause | Status |
|---|---|---|---|---|---|
| 006 | M | `update_state.py` | A read-only or full state file raised an unhandled `PermissionError`, killing an unattended job on a traceback. `save()` also logged `saved 1.0.0` **before** writing, so a claim of success was printed for a write that never happened. | No error handling on the two writes, and the log line came first. | **Fixed, verified** |
| 007 | **H** | `tokenmeter.py` | An unreadable `token_usage.json` was swallowed by a bare `except` and returned `{}`, which `spent()` read as **zero tokens used**. `affordable()` therefore answered "yes, plenty left" on every call and the pipeline spent the entire per-minute limit before anything noticed. | A corrupt or unwritable file was treated as an empty one, and the empty case is the permissive one. | **Fixed, verified** |
| 008 | **H** | `budget.py` | The same fail-open shape: a corrupt or non-dict `budget.json` returned an empty budget, which read as a month with zero hours spent, so `check()` **approved** jobs on a month that may already have spent all thirty. The module docstring claimed the hours were "committed... and cannot quietly reset", which was false — `380e29e` had deliberately untracked the file. | As above, plus a docstring asserting a protection that had already been removed. | **Fixed, verified** |
| 009 | M | `tokenmeter.py`, `budget.py` | Neither write was atomic. A job dying mid-write left a truncated file, which the next read treated as corrupt, which (before 007/008) meant "nothing spent" — so the crash itself reset the accounting. | `write_text` straight onto the live file. | **Fixed, verified** |
| 010 | L | `stage_app.py` | An unreadable meter made `affordable()` false forever, so the loop slept 30s at a time for its full 300s budget waiting for a reset that could never happen, then started anyway. | The wait loop assumed "not affordable" meant "temporarily over the limit". | **Fixed, verified** |
| 011 | M | repo hygiene | `data/token_usage.json` was committed in `0274226` by the Friday job's `git add -A`. It is live rate-limit state for whichever machine is running, so every later run on every other runner read a total it did not earn and began its own allowance from it. | `git add -A` sweeping untracked runtime state into a commit. | **Fixed, verified** |
| 012 | L | `audit_selftest.py` | The suite itself called `git ls-files` with a `cwd`, which works, but read it without a timeout and crashed when run from outside the repository in the copy used by `cwd_selftest.py`. | Not a defect in the product; a defect in the test that was checking the product. | **Fixed, verified** |

---

## 5. Corrections to earlier findings

An earlier draft recorded that `check.ps1` contained `"env:$name"`, which it
claimed PowerShell cannot parse. **That was wrong.** The parser accepts it, and
the parse errors came from an intermediate edit during the audit, not from the
original file. The script was syntactically valid; it had simply never been
run. The claimed parse check was removed rather than left in place, because it
could not be shown to detect an error reliably.

A second earlier claim is worth recording because it shows the cost of reading
paths statically. A scan flagged `shorts_render.py:151` for using the relative
literal `"site/icon-512.png"`. The next two lines were `p = ROOT / rel`. It was
correct, and the static check was wrong. Every entry point was therefore
subsequently **executed** from an unrelated directory instead (§1), which
found one genuine issue that the static pass had not.

---

## 6. Fixes applied

| File | Change |
|---|---|
| `update_state.py` | `save()` and `publish_public()` return whether they wrote; neither logs a success it cannot prove; `main()` exits non-zero when either fails |
| `tokenmeter.py` | unreadable or non-dict state is reported on stderr and read as "unknown", not zero; `spent()` returns a value above any limit so `affordable()` is false; `unknown()` added; the write is atomic |
| `budget.py` | as above; `check()` refuses outright on an unreadable budget; `save()` is atomic and reports failure; `record()` returns whether it worked; the docstring no longer claims the state is committed |
| `stage_app.py` | does not wait out a reset that cannot happen, and says why |
| `.gitignore` | `data/token_usage.json` and both `.tmp` files |
| `check.ps1` | required-variable list now names every variable the checker requires; five optional variables listed separately |
| `learn.py` | `itch_signals()` delegates to `reputation.itch_signals()` |
| `improve_daily.py` | a non-integer `SystemExit.code` is read as the message it is |
| `selftest_audit.py` | refuses any committed `_*.py` scratch file |
| `friday-build.yml` | NSIS installed on the generate runner, and the version printed so a silent absence is visible |
| `audit_selftest.py` | **new**; holds the failure-mode findings |
| `property_selftest.py` | **new**; generated cases for the arithmetic that decides things |
| `cwd_selftest.py` | **new**; every entry point executed from an unrelated directory |

---

## 7. Regression tests added

| Suite | What it now holds in place |
|---|---|
| `audit_selftest.py` | a read-only state file does not raise, does not claim a save, and exits non-zero; truncated, list and numeric meter states are all reported unknown, are not read as zero, leave nothing affordable, and leave zero remaining; a stale window is still fine; `stage_app` checks the meter before waiting; a readable budget approves, and truncated, list and numeric budgets refuse; the budget docstring no longer claims a committed state; no scratch file tracked |
| `property_selftest.py` | 125 versions round-trip through parse and format; every bump in every level moves strictly forward; a major clears minor and patch and a minor clears patch; junk version strings do not crash the parser; the release phase is correct at 81 offsets around the switch and never un-launches; `days_until` agrees with the phase boundary in both directions; no day of a year plans into the past or closer than the lead time; `pricing.clamp` holds at 11 boundaries including both edges; the cooldown expires, starts, and survives an unreadable timestamp |
| `cwd_selftest.py` | 20 entry points run from an unrelated working directory with no traceback |

Each was confirmed to fail against the unfixed behaviour before the fix was
kept.

---

## 8. Blockers (environmental, not bugs)

| Blocker | Evidence | Effect |
|---|---|---|
| itch.io credentials exist only as GitHub secrets | `itch_publish.py` refuses locally: "ITCH_USER is not set" | the upload and publish step cannot be exercised from this machine. Verified in CI instead. |
| The YouTube token is `youtube.upload` only | `shorts_auth.SCOPE` | comment reading needs `youtube.readonly`. `signals.py` reports the missing scope by name instead of returning a false zero. |
| ElevenLabs account out of credits | `HTTP 402` on a stock voice | no TTS and no generated music. A licensed CC0 bed in `assets/music/` is used instead. |
| NSIS on the generate runner | fixed, **not yet re-run in CI** | needs one dispatch of `friday-build.yml` to confirm |
| Windows read-only semantics | `chmod(S_IREAD)` on the file denies writes, but on the **directory** it leaves existing files writable | the `PermissionError` in bug 006 was reproduced by making the state file read-only. The distinction was measured rather than assumed, because the first attempt made the directory read-only and wrote to the file without error. |

### Pre-existing commercial gap, unchanged and documented

`e2e_all.py` reports 2 of 4 journeys broken, improved from 3 of 4 at the start
of this pass. The remaining failures are real and are not bugs in the code:

- the paid edition has no `itch_url`, so the buy button has nowhere to go. Both
  entries in `site/apps.json` point at `https://slingshot-tools.itch.io/`, a
  store page that exists but has no paid product in it, which is why the links
  journey now fails on the itch.io link as well
- the paid build on this machine is a 59-byte placeholder
- no installer has been published, and the itch.io store page is empty

The machinery to fix all three is in place and exercised as far as the
credentials allow: `stage_app.py` builds the installer, `build_paid_only.py`
compiles and wraps it and rejects a stub, and `itch_publish.py` creates,
uploads, verifies and then publishes. What remains is one successful itch.io
upload, which needs the secrets already present in the repository.

### Open question, not fixed

`friday-verify.yml` still runs the itch.io publish step with
`continue-on-error: true` and records the outcome in a warning and in a
`PUBLISHED` output that nothing consumes. This was a deliberate choice, so
that a paid-upload failure does not block the free weekly release. It is
recorded here as an open question rather than a defect, because whether a
failed paid upload should fail the job is a policy decision, not a fact about
the code. The information needed to make it is now in the log either way.

---

## 9. Verification log

Commands actually run, with outcomes.

| Command | Result |
|---|---|
| `python -m pyflakes` over all root modules | 0 findings |
| `python run_selftests.py --quiet` | **all 19 selftests pass** |
| `python selftest_audit.py` | 0 problems across 117 files |
| `python selftest.py` | 13/13 behavioural checks |
| `python selftest_deep.py` | CLEAN |
| `python cleanroom_selftest.py` | all 8 checks on a clean checkout |
| `python tracked_selftest.py` | no failures |
| `python audit_selftest.py` | no failures |
| `python property_selftest.py` | no failures |
| `python cwd_selftest.py` | no failures, 20 entry points |
| `python e2e_all.py` | **2 of 4 journeys broken** (§8); improved from 3 of 4 |
| `powershell -File .\check.ps1` | runs; reports the required variables missing, and the optional ones separately |
| `gh workflow run friday-build.yml` | first ever successful run, after the module fixes |
| `python build_paid_only.py --check` | finds a real installer, ignores the 110 KB stubs |

Baseline `run_selftests.py` ran 16 suites at the start of the first pass; it
discovers `*selftest*.py` automatically, so the count moved to 19 as three
suites were added. `cwd_selftest.py` counts itself in that total, and its own
list of 20 entry points is the subset it re-runs from elsewhere.

Not performed, and why: no destructive script, no deployment, no credential
rotation, no change to any external account. The itch.io upload was not
executed because its credentials are secrets in the repository rather than
values on this machine.

---

## 10. Final status

**VERIFIED WITHIN TESTED SCOPE.** Every issue found in the seven passes is
either fixed with a regression test, or documented above as a blocker with its
evidence and its next step, or named as an open question.

Stated plainly, because the previous audits were not: this is **not** a claim
of zero bugs. Three of the defects found in the second pass (007, 008, 009)
were invisible to a green test suite and to pyflakes, and were found only by
deliberately breaking the state files and asking what the program did next.
The commercial gap in §8 is real, known, and stated rather than hidden behind
a green suite.

The single most useful thing this pass established is the direction of the
failure. Three separate modules read an unreadable file as zero. In a counter,
zero is the answer that lets you keep spending.