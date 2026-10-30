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

# The live Base64 tool was reported dead on URL Decode. It works: its free
# edition keeps three items and silently ignores a fourth, and the scanner had
# already spent the cap with three earlier clicks. Every free edition has a
# cap like this, so without a clean page per control the scanner condemns the
# whole catalogue for behaving exactly as designed.
CAPPED = """<!DOCTYPE html><html><body>
<button id="a">One</button>
<button id="b">Two</button>
<button id="c">Three</button>
<button id="d">Four</button>
<ul id="list"></ul>
<script>
let kept = 0;
const add = () => {
  if (kept >= 3) return;
  kept++;
  const li = document.createElement('li');
  li.textContent = 'item ' + kept;
  document.getElementById('list').appendChild(li);
};
for (const id of ['a', 'b', 'c', 'd']) {
  document.getElementById(id).addEventListener('click', add);
}
</script>
</body></html>"""

CAPPED_DEAD = """<!DOCTYPE html><html><body>
<button id="a">One</button>
<button id="b">Two</button>
<ul id="list"></ul>
<script>
document.getElementById('a').addEventListener('click', () => {
  const li = document.createElement('li');
  li.textContent = 'item';
  document.getElementById('list').appendChild(li);
});
</script>
</body></html>"""

capped = tmp / "capped.html"
capped.write_text(CAPPED, encoding="utf-8")
capped_dead = tmp / "capped-dead.html"
capped_dead.write_text(CAPPED_DEAD, encoding="utf-8")

got = app_scanner.scan(capped)
dead = " ".join(got.get("dead", []))
check("a free-tier cap is not a dead control",
      not dead, f"dead={got.get('dead')}")
check("and the capped app passes the gate", app_scanner.verdict(got),
      f"dead={got.get('dead')}")

got = app_scanner.scan(capped_dead)
dead = " ".join(got.get("dead", []))
check("a control that does nothing next to a working one is still dead",
      "Two" in dead, f"dead={got.get('dead')}")

# A paid edition's Export saves a file and changes nothing on the page. The
# paid Invoice generator build was refused for exporting exactly as designed.
SAVER = """<!DOCTYPE html><html><body>
<button id="saveIt">Export Data</button>
<script>
document.getElementById('saveIt').addEventListener('click', () => {
  const blob = new Blob(['{"x":1}'], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'data.json';
  a.click();
  URL.revokeObjectURL(a.href);
});
</script>
</body></html>"""

SAVER_DEAD = """<!DOCTYPE html><html><body>
<button id="saveIt">Export Data</button>
<script>
document.getElementById('saveIt').addEventListener('click', () => {});
</script>
</body></html>"""

saver = tmp / "saver.html"
saver.write_text(SAVER, encoding="utf-8")
saver_dead = tmp / "saver-dead.html"
saver_dead.write_text(SAVER_DEAD, encoding="utf-8")

got = app_scanner.scan(saver)
dead = " ".join(got.get("dead", []))
check("a button that saves a file is not dead", not dead, f"dead={got.get('dead')}")
check("and its handler is not reported missing",
      not any("Export" in m for m in got.get("missing", [])),
      f"missing={got.get('missing')}")

got = app_scanner.scan(saver_dead)
dead = " ".join(got.get("dead", []))
check("a Save button that really saves nothing is still dead",
      "Export" in dead, f"dead={got.get('dead')}")

# A disabled control cannot be clicked by a person, so it is neither alive nor
# dead. The live timestamp converter keeps Export disabled in the free edition.
DISABLED = """<!DOCTYPE html><html><body>
<button id="exportBtn" disabled>Export My Data</button>
<button id="live">Export Too</button>
<script>
document.getElementById('live').addEventListener('click', () => {
  document.body.appendChild(document.createElement('p'));
});
</script>
</body></html>"""

# prompt() blocks a headless run and returns null, so a working "Add bookmark"
# that asks for a URL was reported dead. The live bookmark organizer does this.
PROMPTER = """<!DOCTYPE html><html><body>
<button id="addBtn">Add Bookmark</button>
<ul id="list"></ul>
<script>
document.getElementById('addBtn').addEventListener('click', () => {
  const url = prompt('Enter URL');
  if (!url) return;
  const li = document.createElement('li');
  li.textContent = url;
  document.getElementById('list').appendChild(li);
});
</script>
</body></html>"""

# A control that reads an empty box cannot respond. The live unit converter
# returns early on an empty value, which is what a person fills in first.
FILLER = """<!DOCTYPE html><html><body>
<input id="value" type="number">
<button id="convert">Convert</button>
<p id="result"></p>
<script>
document.getElementById('convert').addEventListener('click', () => {
  const val = parseFloat(document.getElementById('value').value);
  if (isNaN(val)) return;
  document.getElementById('result').textContent = 'Result: ' + val;
});
</script>
</body></html>"""

FILLER_DEAD = """<!DOCTYPE html><html><body>
<input id="value" type="number">
<button id="convert">Convert</button>
<script>
document.getElementById('convert').addEventListener('click', () => {});
</script>
</body></html>"""

disabled = tmp / "disabled.html"
disabled.write_text(DISABLED, encoding="utf-8")
prompter = tmp / "prompter.html"
prompter.write_text(PROMPTER, encoding="utf-8")
filler = tmp / "filler.html"
filler.write_text(FILLER, encoding="utf-8")
filler_dead = tmp / "filler-dead.html"
filler_dead.write_text(FILLER_DEAD, encoding="utf-8")

got = app_scanner.scan(disabled)
dead = " ".join(got.get("dead", []))
check("a disabled control is skipped, not dead", "Export My Data" not in dead,
      f"dead={got.get('dead')} skipped={got.get('skipped')}")
check("and the enabled control beside it still works", app_scanner.verdict(got),
      f"dead={got.get('dead')}")

got = app_scanner.scan(prompter)
dead = " ".join(got.get("dead", []))
check("a button that asks with prompt() is not dead", "Add Bookmark" not in dead,
      f"dead={got.get('dead')}")

got = app_scanner.scan(filler)
dead = " ".join(got.get("dead", []))
check("a button that needs a number typed in is not dead",
      "Convert" not in dead, f"dead={got.get('dead')}")

got = app_scanner.scan(filler_dead)
dead = " ".join(got.get("dead", []))
check("a Convert button that really does nothing is still dead",
      "Convert" in dead, f"dead={got.get('dead')}")

print()
print("FAILURES:", fails if fails else "none")
raise SystemExit(1 if fails else 0)