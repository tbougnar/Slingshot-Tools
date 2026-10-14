"""Do escaped single quotes survive the unescape?

Replacing \\' with ' turned \"it\\'s\" into \"it's\", which is not valid
JavaScript. Five consecutive generate attempts were refused for it, and every
message pointed at a line of the generated app rather than at the decode.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import make_app

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


# the model sends this inside a JSON string value
CASES = [
    (r"const s=\"it\\'s here\";", "an escaped quote in a double-quoted string"),
    (r"const s='it\\'s here';", "an escaped quote in a single-quoted string"),
    (r"b.split('\\n');", "a backslash-n inside a single-quoted string"),
    (r"b.split(\"\\n\");", "a backslash-n inside a double-quoted string"),
    (r"const RE=/\\d+/.test(v);", "a digit class"),
    (r"const s='plain';", "a plain single-quoted string"),
]

print("\nESCAPES INSIDE STRINGS SURVIVE\n")
for raw, label in CASES:
    got = make_app._unescape(raw)
    # whatever it becomes, it must not have lost a backslash that was load
    # bearing, and the result must parse
    errs = make_app.js_syntax_errors(f"<script>{got}</script>")
    check(f"{label} parses", not errs, f"got {got!r} -> {errs[:1]}")

print("\nAN ESCAPED QUOTE IS NOT STRIPPED\n")
got = make_app._unescape(r"const s='it\\'s';")
check("the backslash before the quote survives",
      "\\'" in got, f"got {got!r}")

print("\nA SINGLE-QUOTED STRING WITH AN ESCAPE\n")
got2 = make_app._unescape(r"const parts=b.split('\\n');const t=parts[0];")
check("it parses", not make_app.js_syntax_errors(f"<script>{got2}</script>"),
      f"got {got2!r}")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)