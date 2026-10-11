"""Where the price card lands in a variable length narration."""
import sys

import shorts_render as sr

fails = []


def parts(n):
    return [{"text": f"line {i}"} for i in range(n)]


# the price sits beside the proof, never first and never last
for n, want in ((1, 0), (2, 1), (3, 1), (4, 2), (5, 2), (6, 2)):
    got = sr._price_line(parts(n), "$3")
    ok = got == want and 0 <= got < n
    print(("ok   " if ok else "FAIL "), f"{n} lines -> price on {got}")
    if not ok:
        fails.append(f"{n} lines")

# a single line has nothing else to sit beside
ok = sr._price_line(parts(1), "") == 0
print(("ok   " if ok else "FAIL "), "one line still has somewhere to go")
if not ok:
    fails.append("single")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)