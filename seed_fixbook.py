"""Seed the fixbook with every bug hit while getting the pipeline working.

These are real, observed failures - not guesses. Each one has a check that
would catch it next time.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buglog

SEED = [
    ("itch.io projects could not be created from CI",
     "Cloudflare blocks headless browsers and plain HTTP on itch.io; there is no "
     "create-project API, and the API key alone cannot make one.",
     "Removed itch.io entirely and replaced delivery with PayPal plus a private "
     "store behind the payment API.",
     ["worker/worker.js"], "no reference to itch remains in the code"),

    ("paid builds were publicly downloadable",
     "Old paid files were still tracked in git after being moved on disk, and "
     "the build re-published them under site/apps.",
     "site/ now receives only the basic edition; paid/ is gitignored and served "
     "only after payment.",
     ["make_app.py", ".gitignore"],
     "apps/<slug> for a paid slug returns 404 while apps/<slug>-basic returns 200"),

    ("workflow could not be dispatched",
     "Duplicate PRICE_FLOOR keys made the YAML invalid, so GitHub reported the "
     "workflow had no workflow_dispatch trigger.",
     "Removed the duplicate keys and validated the file before pushing.",
     [".github/workflows/monday-build.yml"], "the workflow file parses as YAML"),

    ("build crashed with NameError: stage_paid",
     "A function was renamed during the itch removal but the call site was not.",
     "Defined stage_paid and had it build the real app folder plus installer.",
     ["make_app.py"], "python -m py_compile passes and stage_paid exists"),

    ("SameFileError while staging the paid build",
     "write_app already writes into paid/<slug>, so the copy step copied files "
     "onto themselves.",
     "Detect that source and destination are the same and skip the copy.",
     ["paid_store.py"], "staging a build whose folder already exists is a no-op"),

    ("paid customers received nothing (HTTP 413)",
     "A standalone Windows exe is about 28 MB and the store rejects any single "
     "value above 25 MB.",
     "Split the file into chunks on upload and rejoin them in the worker before "
     "replying, so the customer still gets one complete file.",
     ["paid_store.py", "worker/worker.js"],
     "the store holds every chunk and their sizes sum to the file size"),

    ("QA crashed with 'object of bool has no len'",
     "Playwright was not installed on the runner, so the scanner returned a "
     "flag instead of a list.",
     "Install Playwright on the runner, and make a scanner that cannot run report "
     "failure rather than pass.",
     ["app_scanner.py", ".github/workflows/monday-build.yml"],
     "app_scanner.verdict is False when the scanner is unavailable"),

    ("every model call failed with HTTP 403 error 1010",
     "Cloudflare refuses Python's urllib based on its fingerprint; a browser "
     "User-Agent alone does not help.",
     "All model calls go through one client built on requests.",
     ["ai.py"], "groq_check.py reports HTTP 200"),

    ("models were configured that no longer exist",
     "llama-3.3-70b, kimi-k2, deepseek, gemma2 and llama-4 are retired; only "
     "three chat models remain.",
     "Use the three the live catalogue offers: gpt-oss-120b, qwen3.8-27b, "
     "gpt-oss-20b.",
     ["debug_team.py", "make_app.py"],
     "the model list matches what the catalogue endpoint returns"),

    ("finished apps were thrown away over a missing data-theme",
     "A theme attribute was treated as a correctness requirement.",
     "It is recorded as a note, not a rejection.",
     ["make_app.py"], "html without data-theme is accepted with a note"),

    ("the self-heal debugger never produced a fix",
     "Its runner had no requests installed, so every model call it made failed "
     "with ModuleNotFoundError.",
     "Install requests in the self-heal job before it thinks.",
     [".github/workflows/monday-build.yml"],
     "the self-heal log shows a diagnosis rather than a missing-module error"),

    ("the debugger diagnosed the wrong problem",
     "It read --log-failed, which missed the build job, and concluded the "
     "pipeline had not actually failed.",
     "Fetch the build job log as well as the failed output.",
     [".github/workflows/monday-build.yml"],
     "selfheal/failure.txt contains the build step output"),

    ("repairs and app generation came back truncated",
     "Reasoning tokens are drawn from the same max_tokens budget as the reply, so "
     "a 30 KB file stopped mid-way.",
     "Raise the reply budget and turn reasoning off for repairs.",
     ["ai.py", "debug_team.py", "make_app.py"],
     "a generated file ends with </html> and contains localStorage"),

    ("votes collapsed every button into one control",
     "Vote keys used only the tag, so all buttons counted as a single control "
     "and the majority test meant nothing.",
     "Key votes on the whole label and map them back to the scanner's labels.",
     ["debug_team.py"], "distinct buttons produce distinct votes"),
]

if __name__ == "__main__":
    for symptom, cause, fix, files, detects in SEED:
        buglog.record(symptom, cause, fix, files, detects, verified=False)
    print(f"seeded {len(SEED)} entries")
    for e in buglog.load():
        print(f"  {e['id']} {e['symptom'][:66]}")