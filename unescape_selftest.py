"""Does the unescape eat backslashes that were meant to survive?

Collapsing "\\\\" to "\\" repeatedly turns a regex that means a literal
backslash, /\\\\/, into //, which is not a valid regular expression. That
produced "Invalid regular expression: missing /" on generated apps, which the
new gate then correctly refused to stage. The gate was right; the decode was
wrong.
"""
import json
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


def oracle(raw: str) -> str | None:
    """What one correct JSON decode gives. json.loads is the authority."""
    try:
        return json.loads('"' + raw + '"')
    except (json.JSONDecodeError, ValueError):
        return None


print("\nONE JSON DECODE IS THE CORRECT ANSWER\n")
# Each case is what a model writes inside a JSON string value.
for label, raw in (
        ("a digit class", r"const RE=/\\d+/;"),
        ("a literal backslash", r"const RE=/\\\\/;"),
        ("a quoted string", r'const K=\"x\";'),
        ("a word boundary", r"const RE=/\\bword\\b/;"),
        ("an escaped quote in a string", r'const K=\"a\\\"b\";'),
        ("a newline escape", r"const K=\"a\\nb\";"),
        ("alternation", r"const RE=/\\d+|\\s+/;")):
    want = oracle(raw)
    got = make_app._unescape(raw)
    check(f"{label} decodes to what JSON says", got == want,
          f"got {got!r} want {want!r}")

print("\nA DOUBLE-ESCAPED REPLY IS STILL UNWRAPPED\n")
# A model that escapes its own output leaves escaped quotes behind. The decode
# repeats only while that marker survives, which is detectable rather than
# guessed.
double = r'const K=\"x\"; const Y=\"y\";'
once = make_app._unescape(double)
check("a doubly escaped reply is unwrapped", '\\"' not in once, once)
check("and the result is still usable javascript",
      not make_app.js_syntax_errors(f"<script>{once}</script>"),
      str(make_app.js_syntax_errors(f"<script>{once}</script>")))

print("\nREGULAR EXPRESSIONS SURVIVE INTACT\n")
for label, raw in (("digit class", r"const RE=/\\d+/;"),
                   ("literal backslash", r"const RE=/\\\\/;"),
                   ("alternation", r"const RE=/\\d+|\\s+/;")):
    got = make_app._unescape(raw)
    errs = make_app.js_syntax_errors(f"<script>{got}</script>")
    check(f"{label} still contains a backslash", "\\" in got, f"got {got!r}")
    check(f"{label} parses as javascript", not errs, "; ".join(errs[:1]))

print("\nTHE PAYLOAD THE GENERATOR WAS ACTUALLY REFUSING\n")
# Run 38572964326, attempt 2, verbatim in shape: a twice-escaped body with the
# closing quote and some prose after it. One layer of escaping survived and
# every handler in the app was dead, because the script could not parse.
real = (r'const TIER=\\"full\\";const LIMITS={maxItems:0,export:true,'
        r'themes:\\"all\\",bulk:true};localStorage.getItem("k");')
for label, payload in (("bare", real),
                       ("with trailing junk", real + '"}  and here is prose.')):
    out = make_app._unescape(payload)
    check(f"no escape survives ({label})", '\\"' not in out,
          f"got {out[:60]!r}")
    check(f"and the code parses ({label})",
          not make_app.js_syntax_errors(out),
          "; ".join(make_app.js_syntax_errors(out)[:1]))

print("\nESCAPED TEMPLATE MARKERS ARE LEFT ALONE\n")
# \` inside a JavaScript template literal is a valid escape that means
# backtick, and \${ means a literal ${. Decoding them would change what the
# code does, so they must survive.
#
# The fixture has to BE a template literal. An earlier version wrapped the
# escaped backtick in ordinary quotes (const t=\`a ...\`), which is a syntax
# error whatever the unescape does, so the two checks below could never both
# pass and the suite failed for weeks on a test that was wrong, not code.
tmpl = "const t=`a \\` b ${c}`;"
got_t = make_app._unescape(tmpl)
check("an escaped backtick survives", "\\`" in got_t, f"got {got_t!r}")
check("and it parses", not make_app.js_syntax_errors(
    f"<script>{got_t}</script>"),
    str(make_app.js_syntax_errors(f"<script>{got_t}</script>")))

print("\nNORMAL CODE IS UNTOUCHED\n")
plain = 'const K="x"; localStorage.setItem(K,"1"); const n=1+2;'
check("clean javascript passes through unchanged",
      make_app._unescape(plain) == plain, make_app._unescape(plain))

print("\nA DOUBLY ESCAPED REPLY IS STILL UNWRAPPED\n")
# The app that originally shipped unparseable had const TIER=\\"full\\" in its
# source: two backslashes before each quote. That payload is not valid JSON at
# all, because the quote after the escaped backslash closes the string, so it
# never reaches the decode above and has to be handled by the fallback.
double_quote = 'const TIER=\\\\"full\\\\";'
_got = make_app._unescape(double_quote)
check("a doubly escaped quote becomes a real quote",
      _got == 'const TIER="full";', f"got {_got!r}")
check("and no escape survives it", "\\\\" not in _got, f"got {_got!r}")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)