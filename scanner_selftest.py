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

# ---------------------------------------------------------------- regressions
# The Friday run generated an invoice tool that passed nothing: Save Invoice
# was refused because the scanner filled a required type=date with "sample",
# and Import My Data looked dead only because Export had already revealed the
# same upgrade note. Both controls worked. The lane could not publish any app
# with a date field or two gated buttons, which is most of them.

DATED = """<!DOCTYPE html><html><body>
<form id="f">
  <input id="when" type="date" required>
  <input id="who" type="email" required>
  <button type="submit">Save</button>
</form>
<ul id="list"></ul>
<script>
document.getElementById('f').addEventListener('submit', e => {
  e.preventDefault();
  const li = document.createElement('li');
  li.textContent = document.getElementById('who').value;
  document.getElementById('list').appendChild(li);
});
</script>
</body></html>"""

DATED_DEAD = """<!DOCTYPE html><html><body>
<form id="f">
  <input id="when" type="date" required>
  <button type="submit">Save</button>
</form>
<script>
document.getElementById('f').addEventListener('submit', e => { e.preventDefault(); });
</script>
</body></html>"""

GATED = """<!DOCTYPE html><html><body>
<div id="note" style="display:none">Upgrade for this</div>
<button id="exportIt">Export</button>
<button id="importIt">Import</button>
<script>
const note = document.getElementById('note');
document.getElementById('exportIt').addEventListener('click', () => { note.style.display = 'block'; });
document.getElementById('importIt').addEventListener('click', () => { note.style.display = 'block'; });
</script>
</body></html>"""

dated = tmp / "dated.html"
dated.write_text(DATED, encoding="utf-8")
dated_dead = tmp / "dated-dead.html"
dated_dead.write_text(DATED_DEAD, encoding="utf-8")
gated = tmp / "gated.html"
gated.write_text(GATED, encoding="utf-8")

got = app_scanner.scan(dated)
check("a required date field is filled with a valid date, so Save works",
      not any("Save" in d for d in got.get("dead", [])),
      f"dead={got.get('dead')}")
check("and the dated app passes the gate", app_scanner.verdict(got),
      f"dead={got.get('dead')} errors={got.get('errors')}")

got = app_scanner.scan(dated_dead)
check("a submit button that really does nothing is still dead",
      any("Save" in d for d in got.get("dead", [])), f"dead={got.get('dead')}")

got = app_scanner.scan(gated)
dead = " ".join(got.get("dead", []))
check("two buttons revealing the same notice are both alive",
      "Export" not in dead and "Import" not in dead, f"dead={got.get('dead')}")

print()
print("FAILURES:", fails if fails else "none")
raise SystemExit(1 if fails else 0)