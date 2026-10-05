"""Reject an app that is too large to be worth building.

Size is the constraint that decides whether this project works at all. The
builder and the debugger share one model allowance per minute, so a 30 KB app
consumes the entire budget and leaves nothing for checking or fixing. A small
app fits generation and several repair rounds in the same minute.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# A file this size or larger is too big to generate and verify in one minute.
SOFT_CEILING = 9000
HARD_CEILING = 16000


def verdict(nbytes: int) -> tuple[bool, str]:
    if nbytes > HARD_CEILING:
        return False, (f"{nbytes} bytes is over the hard ceiling of {HARD_CEILING}; "
                       f"it cannot be generated and verified within the allowance")
    if nbytes > SOFT_CEILING:
        return True, (f"{nbytes} bytes is over the {SOFT_CEILING} target; "
                      f"QA will have little allowance left to repair it")
    return True, ""


def check_file(p: Path) -> tuple[bool, str]:
    return verdict(p.stat().st_size)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        f = Path(sys.argv[1])
        ok, why = check_file(f)
        print(f"{f.name}: {f.stat().st_size} bytes")
        print("verdict:", "ok" if ok else "TOO BIG")
        if why:
            print("note:", why)
    else:
        print(f"soft ceiling {SOFT_CEILING}, hard ceiling {HARD_CEILING}")