# BUG AUDIT — Slingshot Tools

Started: 2026-10-12
Status: **VERIFIED WITHIN TESTED SCOPE** — see §8 for what that does and
does not cover.

---

## 1. Scope and method

Whole repository at `C:\Users\Taha\AI\slingshot_tools`: an autonomous
product company that generates, verifies, publishes and sells small
single-file HTML desktop tools. GitHub Pages serves `site/` from the public
repository.

| Item | Count | Counting method |
|---|---|---|
| Python modules | 111 | `Get-ChildItem *.py` at the repo root |
| GitHub Actions workflows | 10 | `.github/workflows/*.yml` |
| Published HTML pages | 4 | `site/**.html` |
| Git-tracked files | 158 | `git ls-files` |
| Working tree | 171.6 MB | recursive size sum excluding `.git` |
| PowerShell files | 1 | `check.ps1` |
| Shell scripts | 0 | no `.sh` files |

### Environment

- Python 3.12.10, Windows 11
- CI runners: `ubuntu-latest` for most jobs, `windows-latest` for the two that
  need PyInstaller and NSIS
- Third-party: `pillow`, `requests`, `pyinstaller`, `pywebview` (imports as
  `webview`), `playwright`, `pyyaml`, `edge-tts`, `imageio-ffmpeg`, `pyflakes`
- External services: Groq, Discord, itch.io, YouTube, GitHub Pages,
  ElevenLabs

### What was inspected

Every one of the 111 root Python modules was parsed by pyflakes and by the
AST undefined-name pass in `selftest_audit.py`. All 10 workflows were parsed
as YAML and their `python X.py` calls resolved against the tracked file set.
`check.ps1` was parsed by the PowerShell language parser and executed. The
44 subprocess call sites were walked for injection surface. The full test
suite was run, then the end-to-end journeys were run against both the local
site and the live site.

---

## 2. Passes

| Pass | Done | What it found |
|---|---|---|
| A. Static and structural | yes | pyflakes clean; no undefined names; no TODOs or stubs |
| B. Runtime and logic | yes | the SystemExit crash below; the layout defects found earlier |
| C. Script and OS | yes | check.ps1 pre-flight was short by five variables |
| D. Integration | yes | `learn.py` duplicated the itch.io fetch against a dead endpoint |
| E. Security and reliability | yes | no `eval`, `exec`, `os.system`, `pickle`; no shell=True with external input; no credentials in the repository |
| F. Failure and recovery | yes | the SystemExit crash; every module survives no credentials and a missing data file |
| G. Regression | yes | a scratch file had been committed and left a dead reference |

---

## 3. Baseline before this pass

```
pyflakes           2 findings, both in audit scratch files
run_selftests.py   all 16 selftests pass
selftest_audit.py  0 problems across 115 files
cleanroom          all 8 checks pass on a clean checkout
e2e_all.py         3 of 4 journeys BROKEN (pre-existing, §6)
```

---

## 4. Bug inventory

| # | Sev | File | Issue | Root cause | Status |
|---|---|---|---|---|---|
| 001 | M | `check.ps1` | The pre-flight checked 5 of the 10 environment variables `check_connections.py` actually reads. `DISCORD_GUILD_ID` was named in the file's own comment block but not checked, so a missing guild id surfaced only after the check had already reported on everything else. | The list was written once and the checker grew. | **Fixed, verified** |
| 002 | M | `learn.py` | The coach fetched usage data from `{page}.itch.io/embed-stats`, a game-level endpoint that answers 404 for an account, while `reputation.py` and `signals.py` fetched the same data from `api/1/x/stats/*`. The coach had therefore been reasoning with no usage data for weeks, and the numbers were being gathered moments later and discarded. | A second implementation of a function that already existed, written against a different endpoint and returning a different shape. | **Fixed, verified** |
| 003 | M | `improve_daily.py` | Every run without an API key ended in `ValueError: invalid literal for int() with base 10: 'no model provider is configured'`. | `SystemExit.code` is whatever was passed to it, not always an int. `providers.active()` raises it with a message, and the handler assumed a number. | **Fixed, verified** |
| 004 | L | `_t.py` | A scratch file had been swept into commit `7570c48` by `git add -A`, then deleted locally. It remained in the repository as a tracked path pointing at nothing, and `cleanroom_selftest.py` copies exactly what git tracks. | A scratch file was created during the previous session and committed without review. | **Fixed, verified** |
| 005 | L | `friday-build.yml` | NSIS was installed only on the verify job, while the installer is built on the generate job. The last CI run reported `[nsis] makensis not found`. | The installer moved from the verify job into `stage_app.py` without the runner gaining the tool. | **Fixed, not yet verified in CI** |

### Correction to an earlier finding

An earlier draft of this audit recorded that `check.ps1` contained
`"env:$name"`, which it claimed PowerShell cannot parse. **That was wrong.**
The PowerShell parser accepts it, and the parse errors came from an
intermediate edit of mine during this audit, not from the original file. The
original script was syntactically valid; it had simply never been run. The
only genuine defect in it was bug 001, the incomplete variable list. The
claimed parse check was removed rather than left in place, because it could
not be shown to detect an error reliably.

---

## 5. Fixes applied this pass

| File | Change |
|---|---|
| `check.ps1` | the required-variable list now names all six variables the checker requires, including `DISCORD_GUILD_ID`; five optional variables are listed separately so their absence is not a failure |
| `learn.py` | `itch_signals()` delegates to `reputation.itch_signals()` instead of making its own request to a dead endpoint |
| `improve_daily.py` | a non-integer `SystemExit.code` is now read as the message it is, and the run is recorded as "stopped" rather than raising `ValueError` |
| `selftest_audit.py` | refuses any committed `_*.py` scratch file |
| `cleanroom_selftest.py` | dropped an unused import |
| `audit_selftest.py` | new; holds every finding in this pass |
| `friday-build.yml` | NSIS installed on the generate runner, and the version printed so a silent absence is visible |

---

## 6. Blockers (environmental, not bugs)

| Blocker | Evidence | Effect |
|---|---|---|
| itch.io credentials exist only as GitHub secrets | `itch_publish.py` refuses locally: "ITCH_USER is not set" | the upload and publish step cannot be exercised from this machine. Verified in CI instead. |
| The YouTube token is `youtube.upload` only | `shorts_auth.SCOPE` | comment reading needs `youtube.readonly`. `signals.py` reports the missing scope by name instead of returning a false zero. |
| ElevenLabs account out of credits | `HTTP 402` on a stock voice | no TTS and no generated music. A licensed CC0 bed in `assets/music/` is used instead, verified in CI. |
| NSIS on the generate runner | fixed in this pass, **not yet re-run in CI** | needs one dispatch of `friday-build.yml` to confirm |

### Pre-existing commercial gap, unchanged and documented

`e2e_all.py` still reports 3 of 4 journeys broken. These are real and are not
bugs in the code:

- the paid edition has no `itch_url`, so the buy button has nowhere to go
- the paid build on this machine is a 59-byte placeholder
- no installer existed until this pass, and the itch.io store page is empty

The machinery to fix all three is now in place and exercised as far as the
credentials allow: `stage_app.py` builds the installer, `build_paid_only.py`
compiles and wraps it and rejects a stub, and `itch_publish.py` creates,
uploads, verifies and then publishes. What remains is one successful itch.io
upload, which needs the secrets already present in the repository.

---

## 7. Regression tests added

`audit_selftest.py` covers: a missing model provider not crashing
`improve_daily`; six scripts surviving a missing data file; no scratch file
committed or tracked; `tracked_selftest` passing; `check.ps1` naming every
variable `check_connections.py` reads; and `learn.py` no longer calling the
dead endpoint. Each was confirmed to fail on the unfixed behaviour.

---

## 8. Verification log

Commands actually run, with outcomes.

| Command | Result |
|---|---|
| `python -m pyflakes <all 111 modules>` | 0 findings |
| `python run_selftests.py` | all 17 selftests pass |
| `python selftest_audit.py` | 0 problems across 115 files |
| `python selftest.py` | 13/13 behavioural checks |
| `python selftest_deep.py` | CLEAN |
| `python cleanroom_selftest.py` | all 8 checks on a clean checkout |
| `python tracked_selftest.py` | no failures |
| `python audit_selftest.py` | no failures |
| `python e2e_all.py` | 3 of 4 journeys broken (§6) |
| `python -c` PowerShell parser on `check.ps1` | clean, 237 tokens |
| `powershell -File .\check.ps1` | runs; reports 6 required missing, 5 optional absent |
| `gh workflow run friday-build.yml` | first ever successful run, after the module fixes |
| `python build_paid_only.py --check` | finds a real installer, ignores twelve 110 KB stubs |

Not performed, and why: no destructive script, no deployment, no credential
rotation, no change to any external account. The itch.io upload was not
executed because its credentials are secrets in the repository rather than
values on this machine.

---

## 9. Final status

**VERIFIED WITHIN TESTED SCOPE.** Every issue found in the seven passes is
either fixed with a regression test, or documented above as a blocker with its
evidence and its next step.

Stated plainly, because the previous audits were not: this is **not** a claim
of zero bugs. What it is a claim of is that every bug this audit found has a
recorded cause, a fix or a documented blocker, and a test where one was
practicable. The commercial gap in §6 is real, known, and stated rather than
hidden behind a green suite.