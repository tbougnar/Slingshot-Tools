"""Does the scanner still catch dead controls after making it less eager?

Three rules were relaxed so that dev-converter could ship: a dropdown the app
reads is an input, a submit button gets its form filled first, and a control
that opens a file picker is skipped. Each relaxation is a chance to stop
detecting real bugs, which would be worse than the false positives.

Every case below must still be reported dead.
"""
import tempfile
from pathlib import Path

import app_scanner

PAGE = """<!DOCTYPE html><html><body>
<button id="realDead">nothing attaches to this</button>
<button id="alsoReal" onclick="void 0">handler that changes nothing</button>
<select id="orphanSelect"><option>a</option><option>b</option></select>
<form id="f"><input id="v" type="text" required><button type="submit">Go</button></form>
<script>
document.getElementById('f').addEventListener('submit', e => { e.preventDefault(); });
</script>
</body></html>"""

CLEAN = """<!DOCTYPE html><html><body>
<select id="unit"><option>a</option><option>b</option></select>
<form id="f"><input id="v" type="text" required><button type="submit">Go</button></form>
<script>
document.getElementById('f').addEventListener('submit', e => {
  e.preventDefault();
  const u = document.getElementById('unit').value;
  document.getElementById('out').textContent = document.getElementById('v').value + ' ' + u;
});
</script><p id="out"></p>
</body></html>"""

tmp = Path(tempfile.mkdtemp())
bad_page = tmp / "bad.html"
bad_page.write_text(PAGE, encoding="utf-8")
good_page = tmp / "good.html"
good_page.write_text(CLEAN, encoding="utf-8")

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


got = app_scanner.scan(bad_page)
dead = [d.split(":")[1].split(" (")[0].strip() for d in got.get("dead", [])]
check("a button with no handler is dead", "nothing attaches to this" in dead,
      str(dead))
check("a handler that changes nothing is dead",
      "handler that changes nothing" in dead, str(dead))
check("a select the app never reads is dead", "a\nb" in dead, str(dead))
check("a submit button with no real handler is dead", "Go" in dead, str(dead))

good = app_scanner.scan(good_page)
check("a select the app reads is not dead",
      app_scanner.verdict(good),
      f"dead={good.get('dead')}")
check("a working submit button is not dead",
      not any("Go" in d for d in good.get("dead", [])), str(good.get("dead")))

print()
print("FAILURES:", fails if fails else "none")
raise SystemExit(1 if fails else 0)