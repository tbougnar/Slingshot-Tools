"""Run every end-to-end test and give one honest answer.

The other suites answer "does the code do what it says it does". This answers
the only question that matters commercially: can a stranger find the product
and buy it, and is what they get when they arrive worth having.

It runs the four journeys in order and ends with a plain verdict. Nothing here
is mocked and nothing is assumed; every check either went through a browser or
went out over the network.

    python e2e_all.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

JOURNEYS = [
    ("arrive and try to buy", "e2e_customer.py", []),
    ("is there a product to buy", "e2e_product.py", []),
    ("does the free app work", "e2e_app.py", []),
    ("do the links work", "e2e_links.py", []),
]


def main() -> int:
    results: list[tuple[str, int, str]] = []

    for label, script, args in JOURNEYS:
        print("\n" + "#" * 66)
        print(f"# {label.upper()}   ({script})")
        print("#" * 66)
        r = subprocess.run([sys.executable, script, *args],
                           cwd=str(ROOT), capture_output=True, text=True,
                           timeout=600)
        out = r.stdout
        print(out[-2600:] if len(out) > 2600 else out)
        if r.returncode != 0 and not out.strip():
            print((r.stderr or "")[-800:])
        results.append((label, r.returncode, out))

    print("\n" + "=" * 66)
    print("THE HONEST ANSWER")
    print("=" * 66)
    for label, code, out in results:
        mark = "ok " if code == 0 else "BROKEN"
        line = next((ln.strip() for ln in out.splitlines()
                     if "checks pass" in ln or "steps reached" in ln), "")
        print(f"  {mark:7} {label:26} {line}")

    broke = [r for r in results if r[1] != 0]
    print()
    if broke:
        print(f"{len(broke)} of {len(results)} journeys are broken.")
        print()
        for label, _, out in broke:
            for ln in out.splitlines():
                if ln.startswith("  - "):
                    print(f"  {label}: {ln.strip()[:90]}")
    else:
        print("Every journey works end to end.")
    print("=" * 66)
    return 1 if broke else 0


if __name__ == "__main__":
    raise SystemExit(main())