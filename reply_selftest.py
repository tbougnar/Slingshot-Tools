"""Does a real model reply come through with its regexes intact?

The reply shape: a JSON object with an "html" value, the model closing the
string properly, and then a sentence of prose after it. The regex literal
inside the script is the thing that kept being destroyed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_app

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


SCRIPT = (
    "const TIER=\"full\";\n"
    "const bLines=b.split(/\\r?\\n/);\n"
    "const RE=/\\d+/;\n"
    "const t='it\\'s fine';\n"
    "const f=document.getElementById('f');\n"
)
# _salvage_html refuses a document under 500 bytes, which is right: that is not
# an app. The padding is real content so the test exercises the decode and not
# the length check.
HTML = ("<!DOCTYPE html><html><body><h1>Unit converter</h1>"
        "<p>Converts things. Runs offline.</p>"
        "<input id=\"f\"><div id=\"out\"></div>"
        "<script>" + SCRIPT + "</script>"
        "<p>Your data stays on your device.</p>" * 8 +
        "</body></html>")
assert len(HTML) > 500, f"only {len(HTML)} bytes"

reply = json.dumps({"html": HTML, "brand": "X"}) + "  Hope that helps!"

print("\nA WELL-FORMED REPLY WITH PROSE AFTER IT\n")
got = make_app._salvage_html(reply)
check("the document is recovered", bool(got), "it found nothing")
if got:
    check("the regex survives", "/\\r?\\n/" in got,
          "the newline escape was turned into a real one")
    check("the digit class survives", "/\\d+/" in got)
    check("the escaped quote inside a string survives", "it\\'s fine" in got,
          "it stripped a backslash that was load bearing")
    check("the script has no leftover json escapes",
          '\\"' not in got and "\\\\n" not in got, got[:120])

print("\nTHE SAME REPLY WITHOUT THE PROSE\n")
plain = json.dumps({"html": HTML})
got2 = make_app._salvage_html(plain)
check("identical result either way", got2 == got,
      "the trailing prose changed the decode")

print("\nA TRUNCATED REPLY IS STILL SALVAGED\n")
# cut inside the script, so the json string never closes. The fragment has to
# still be long enough to be an app: under 500 bytes _salvage_html refuses it
# on purpose, and refusing a fragment is not a defect.
cut = json.dumps({"html": HTML})[:int(len(json.dumps({"html": HTML})) * 0.85)]
got3 = make_app._salvage_html(cut)
check("something comes back", got3 is not None,
      f"a truncated model reply is thrown away entirely ({len(cut)} bytes)")
if got3:
    check("and it is still a document", "<html" in got3.lower())

print("\nNO JSON AT ALL\n")
check("plain html is still found",
      make_app._salvage_html("<html><body>" + "x" * 2000 +
                              "</body></html>") is not None)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)