"""Record what the end-to-end customer test found.

These are the first tests that try to do the thing the business exists to do.
Everything before them checked the code against itself.
"""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import buglog

ENTRIES = [
    ("a customer cannot buy anything: the buy button leads to an empty "
     "checkout link",
     "itch_url has never been set, so the paid card renders a real price and "
     "a real button that goes nowhere. Every test in the project passed the "
     "whole time, because all of them read the catalog directly and none of "
     "them clicked the button",
     "found by e2e_customer.py, which follows the journey a person follows. "
     "The fix needs a human to create the itch.io page and run "
     "set_itch_url.py; the tests now say so out loud on every run",
     ["e2e_customer.py", "e2e_product.py", "e2e_all.py"],
     "python e2e_customer.py: the buy link must carry an itch.io address, and "
     "the run fails until it does"),

    ("every test passed while the business could not take a single payment",
     "the suite is built from the project's own point of view: it imports the "
     "modules, calls the functions and compares against expectations written "
     "by the same author. A codebase that is internally perfect can still be "
     "commercially dead, and nothing in it noticed",
     "four end-to-end journeys now exist that go through a browser or over the "
     "network: arrive and buy, is there a product, does the free app work, do "
     "the links work. e2e_all.py runs them and refuses to call the project "
     "healthy while any of them is broken",
     ["e2e_customer.py", "e2e_product.py", "e2e_app.py", "e2e_links.py",
      "e2e_all.py"],
     "python e2e_all.py exits non-zero while any journey is broken"),

    ("the paid edition is a 59-byte file, not an application",
     "paid/password-manager/app/index.html holds one localStorage assignment. "
     "Nothing checks the size or shape of a paid build, so a placeholder is "
     "indistinguishable from a product as far as the pipeline is concerned",
     "e2e_product.py now asks whether the paid app is real: over two thousand "
     "bytes, an html document, and something to click. It reports the byte "
     "count so a placeholder cannot be mistaken for a build",
     ["e2e_product.py"],
     "python e2e_product.py fails on a paid app under 2000 bytes or with no "
     "inputs"),

    ("there is no installer, so even a working itch.io page would sell "
     "nothing",
     "no .exe is built on this machine. The catalog calls the product built "
     "and published, and neither word was checked against the filesystem",
     "e2e_product.py looks for the installer rather than trusting the catalog "
     "flag, because a flag that nothing maintains is a wish",
     ["e2e_product.py"],
     "python e2e_product.py: there is an installer to hand over"),

    ("the itch.io store answers with a 200 and an empty shop",
     "the profile page resolves and loads, so the link check passed and the "
     "footer link looked healthy. Checking that a URL answers is not the same "
     "as checking there is something behind it",
     "the link journey now reads the store page and looks for the product by "
     "name, so an empty shop fails rather than passing on its status code",
     ["e2e_links.py"],
     "python e2e_links.py: the itch.io store actually lists the product"),

    ("a real link was reported broken because the body was truncated",
     "GitHub serves a large page and closes the connection early under a "
     "plain user agent. The test treated an IncompleteRead as a dead link, so "
     "the report was wrong about the site",
     "a partial read is accepted when a status code came back, because a "
     "truncated body is a fetch problem and not a site being down. Only the "
     "status is trusted for these large pages",
     ["e2e_links.py"],
     "python e2e_links.py, and the GitHub line now passes"),
]


def main() -> int:
    existing = {e["symptom"][:60] for e in buglog.load()}
    added = 0
    for symptom, cause, fix, files, detects in ENTRIES:
        if symptom[:60] in existing:
            print(f"skip  {symptom[:60]}")
            continue
        buglog.record(symptom, cause, fix, files, detects)
        added += 1
        print(f"added {symptom[:60]}")
    print()
    print(f"{added} new entries, {len(buglog.load())} in the fixbook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())