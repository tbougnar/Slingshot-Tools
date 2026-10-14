"""best_variant: fix an over-escaped quote, never touch a working app.

These assertions need node, which is on the CI runner and not necessarily on a
developer's machine. Without it the fallback check is all there is, and it
cannot see this class of fault at all, so the suite says so rather than
reporting a pass it did not earn.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_app

fails = []
HAVE_NODE = bool(shutil.which("node"))


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


BROKEN = ("const TIER=\"full\";let parts=b.split(\\'\\');"
          "const x=document.getElementById(\\'new\\').value;")
GOOD = ("const TIER=\"full\";let parts=b.split('');"
        "const x=document.getElementById('new').value;"
        "const s='it\\'s here';const RE=/\\d+/;")

if not HAVE_NODE:
    print("skip  node is not installed here, so the javascript check is the")
    print("      fallback one and cannot see this class of fault. Run this on a")
    print("      machine with node, or read the result from the CI log.")
else:
    print("\nAN OVER-ESCAPED QUOTE IS FIXED\n")
    html = f"<html><body><script>{BROKEN}</script></body></html>"
    check("it does not parse to begin with",
          bool(make_app.js_syntax_errors(html)),
          "the rest of this would prove nothing")
    fixed, ok = make_app.best_variant(html)
    check("a variant is found that does parse", ok)
    check("and the chosen variant parses", not make_app.js_syntax_errors(fixed),
          str(make_app.js_syntax_errors(fixed)[:1]))
    check("the backslashes around the bare quotes are gone",
          "\\'" not in fixed.split("split(")[1].split(")")[0],
          fixed[fixed.find("b.split"):][:28])

    print("\nA WORKING APP IS LEFT COMPLETELY ALONE\n")
    good_html = f"<html><body><script>{GOOD}</script></body></html>"
    check("a parsing app is returned unchanged",
          make_app.best_variant(good_html) == (good_html, True),
          "best_variant rewrote something that already worked")

    print("\nSOMETHING GENUINELY BROKEN IS NOT FORCED THROUGH\n")
    junk = "<html><body><script>function ( { ]</script></body></html>"
    check("unfixable code stays unfixable",
          make_app.best_variant(junk)[1] is False,
          "it accepted a variant node rejects")

# These hold either way.
print("\nTHE CONTRACT, WHICH NEEDS NO NODE\n")
src = (Path(__file__).resolve().parent / "make_app.py").read_text(
    encoding="utf-8")
check("best_variant exists", "def best_variant(" in src)
check("it decides by parsing, not by a rule",
      "if not js_syntax_errors(candidate):" in src,
      "it takes a variant without evidence that it is better")
check("stage_app uses it before the gate",
      "make_app.best_variant(html)" in
      (Path(__file__).resolve().parent / "stage_app.py").read_text(
          encoding="utf-8"))
check("a clean app is returned as it came in",
      make_app.best_variant("<script>const a=1;</script>")
      == ("<script>const a=1;</script>", True))
check("html with no script at all is left alone",
      make_app.best_variant("<html><body>hi</body></html>")
      == ("<html><body>hi</body></html>", True))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)