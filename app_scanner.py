"""Interactive bug scanner for a generated app.

Opens the real page in a headless browser, clicks every control, and reports
controls that do nothing - no DOM change, no state change, no navigation, no
dialog - plus any JavaScript error, unhandled rejection or missing handler.

Each control is judged on a freshly loaded page with its storage cleared. The
first version clicked them all in one session, which made an app that caps how
much it will store look broken: the Base64 tool's free edition keeps three
items and silently ignores a fourth, so Encode, Decode and URL Encode used up
the cap and URL Decode - a working button - was reported dead. A free tier
with a limit is normal, and every free edition has one, so the scanner has to
put the app back before judging the next control.
"""
from __future__ import annotations

import json
from pathlib import Path

SELECTOR = ("button, a[href], input[type=button], input[type=submit], "
            "[role=button], select, [onclick]")

# How many controls are worth clicking, and which of them a person can see.
COUNT = r"""
() => {
  const sel = %s;
  return [...document.querySelectorAll(sel)]
    .filter(n => n.offsetParent !== null || n.tagName === 'SELECT')
    .slice(0, 120).length;
}
""" % json.dumps(SELECTOR)

# Controls that look interactive but have nothing attached at all.
MISSING = r"""
() => {
  const sel = %s;
  const src = [...document.querySelectorAll('script:not([src])')].map(s => s.textContent).join('\n');
  const out = [];
  for (const n of [...document.querySelectorAll(sel)].slice(0, 120)) {
    if (n.onclick || n.getAttribute('onclick') || n.tagName === 'A' ||
        n.tagName === 'SELECT' || n.closest('form')) continue;
    // a listener added with addEventListener leaves no attribute behind; an id
    // the script mentions is the best evidence there is that one exists
    if (n.id && (src.includes("'" + n.id + "'") || src.includes('"' + n.id + '"'))) continue;
    out.push((n.tagName + ':' + (n.innerText || n.value || '')).slice(0, 50).trim());
  }
  return out;
}
""" % json.dumps(SELECTOR)

CLEAR = r"""
() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }
"""

# Click exactly one control. The page is reloaded and cleared before each call,
# so nothing an earlier click stored, hid or spent can change the verdict.
PROBE = r"""
async (index) => {
  const out = {dead: [], errors: [], missing: [], skipped: []};
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  window.addEventListener('error', e => out.errors.push('error: ' + (e.message || '')));
  window.addEventListener('unhandledrejection', e => out.errors.push('reject: ' + e.reason));
  // Any real response to a click mutates the DOM or storage. Counting
  // mutations catches changes that keep the page length identical.
  const mo = new MutationObserver(list => { window.__mut = (window.__mut || 0) + list.length; });
  mo.observe(document.body, {childList:true, subtree:true, attributes:true, characterData:true});
  // Ids the app's own script reads are inputs. Reading a dropdown or a text
  // box is how it receives a value, so clicking one cannot be expected to
  // change the page.
  const src = [...document.querySelectorAll('script:not([src])')].map(s => s.textContent).join('\n');
  const readIds = new Set();
  for (const m of src.matchAll(/getElementById\(\s*["'`]([^"'`]+)["'`]\s*\)/g)) readIds.add(m[1]);
  for (const m of src.matchAll(/\$\(\s*["'#]([^"'`]+)["'`]\s*\)/g)) readIds.add(m[1].replace(/^#/, ''));
  window.__readIds = n => readIds.has(n.id);
  // A control whose only job is to open a file picker cannot be exercised
  // without a person choosing a file, so clicking it proves nothing either
  // way. Rather than guess from the button's text, the file inputs' click is
  // intercepted for the duration of each click: if the click reached one, that
  // control opened a picker and is reported as skipped rather than dead.
  const fileEls = [...document.querySelectorAll('input[type=file]')];
  const realClicks = fileEls.map(el => el.click);
  const origErr = console.error;
  console.error = function (...a) { out.errors.push('console: ' + a.join(' ')); origErr.apply(console, a); };

  // A paid edition's Export button saves a file and deliberately changes
  // nothing on the page, so a DOM/storage test called it dead. The paid build
  // of the Invoice generator was refused for exporting exactly as designed.
  // Creating a blob or clicking a download link is a response.
  window.__saved = 0;
  const origCreate = URL.createObjectURL;
  URL.createObjectURL = function (blob) { window.__saved++; return origCreate.call(URL, blob); };
  const origAnchorClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.download) window.__saved++;
    return origAnchorClick.call(this);
  };
  const origOpen = window.open;
  window.open = function () { window.__saved++; return origOpen.apply(window, arguments); };

  // A sample value must satisfy the field's own type. Filling a required
  // type=date with "sample" leaves it invalid, the browser refuses the submit
  // before the handler runs, and the Save button is reported dead. That is how
  // a working invoice generator failed every repair round.
  const fillValue = (el) => {
    const t = (el.type || 'text').toLowerCase();
    if (t === 'date') return '2026-01-15';
    if (t === 'time') return '09:30';
    if (t === 'datetime-local') return '2026-01-15T09:30';
    if (t === 'month') return '2026-01';
    if (t === 'week') return '2026-W03';
    if (t === 'email') return 'sample@example.com';
    if (t === 'url') return 'https://example.com';
    if (t === 'tel') return '5550100';
    if (t === 'number' || t === 'range') return '1';
    if (t === 'color') return '#336699';
    if (t === 'password') return 'sample-pass';
    // A textarea whose placeholder is JSON is asking for JSON.
    const ph = (el.placeholder || '').trim();
    if (ph.startsWith('[') || ph.startsWith('{')) {
      try { JSON.parse(ph); return ph; } catch (e) {}
    }
    return 'sample';
  };

  // Elements the page hides at load and reveals on a click (an upgrade note, a
  // toast, an inline panel) are hidden again before the click. With one click
  // per load this is belt and braces; it also covers an app that reveals
  // something during its own start-up.
  const hiddenAtStart = [];
  const shown = (el) => !!(el.offsetParent !== null || el.getClientRects().length);
  for (const el of [...document.querySelectorAll('body *')].slice(0, 800)) {
    if (shown(el)) continue;
    hiddenAtStart.push({el, style: el.getAttribute('style'),
                        cls: el.getAttribute('class'),
                        hidden: el.hasAttribute('hidden')});
  }
  const undoReveals = () => {
    for (const r of hiddenAtStart) {
      if (!shown(r.el)) continue;
      if (r.style === null) r.el.removeAttribute('style');
      else r.el.setAttribute('style', r.style);
      if (r.cls === null) r.el.removeAttribute('class');
      else r.el.setAttribute('class', r.cls);
      if (r.hidden) r.el.setAttribute('hidden', '');
      else r.el.removeAttribute('hidden');
    }
  };

  const sel = %s;
  const nodes = [...document.querySelectorAll(sel)]
    .filter(n => n.offsetParent !== null || n.tagName === 'SELECT');
  const n = nodes[index];
  if (!n) return JSON.stringify(out);
  {
    const label = (n.tagName + ':' + (n.innerText || n.value || n.getAttribute('aria-label') || n.id || '')).slice(0, 60).trim();
    const text = (n.innerText || n.value || n.getAttribute('aria-label') || '').trim();
    if (/^(delete|remove|reset|clear|empty|wipe)\b/i.test(text)) { out.skipped.push(label); return JSON.stringify(out); }
    undoReveals();
    // A disabled control cannot be clicked by a person either. The timestamp
    // converter keeps its Export button in the page with `disabled` set until
    // the paid edition, and clicking it with JS only produced "handler present
    // but nothing happened" - a verdict about markup, not about behaviour.
    if (n.disabled || n.getAttribute('aria-disabled') === 'true') {
      out.skipped.push(label + ' (disabled)');
      return JSON.stringify(out);
    }
    // A control that reads a text box cannot respond while the box is empty:
    // the unit converter returns early on an empty value, so Convert looked
    // dead when it works the moment there is a number. Fill what a person
    // would fill before pressing anything. This happens before the state
    // snapshot, so the fill itself is never mistaken for the click's response.
    for (const el of [...document.querySelectorAll('input,textarea')]) {
      const t = (el.type || 'text').toLowerCase();
      if (el.disabled || el.readOnly || el.value) continue;
      if (!['text', 'number', 'range', 'search', 'url', 'email', 'tel',
            'date', 'time', 'datetime-local', 'month', 'week', 'color',
            'password', ''].includes(t) && el.tagName !== 'TEXTAREA') continue;
      if (el.offsetParent === null) continue;
      try {
        el.value = fillValue(el);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
      } catch (e) {}
    }
    // A submit button on a form with a required field is refused by the browser
    // before the handler ever runs, so the app looks broken when it is not.
    // Fill anything empty first, which is what a person would do.
    if (n.tagName === 'BUTTON' && n.type === 'submit' || n.tagName === 'INPUT' && n.type === 'submit') {
      const form = n.closest('form');
      let unusable = false;
      for (const f of form ? [form] : []) {
        for (const el of f.querySelectorAll('input,textarea')) {
          if (!el.value) {
            try {
              el.value = fillValue(el);
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            } catch (e) {}
          }
        }
        // Still invalid after a fair fill (an unusual validator, a cross-field
        // rule) means this control cannot be exercised, which is not evidence
        // that it is broken.
        if (typeof f.checkValidity === 'function' && !f.checkValidity()) unusable = true;
      }
      if (unusable) {
        out.skipped.push(label + ' (form still invalid after filling)');
        return JSON.stringify(out);
      }
    }
    // A control that only opens a file picker cannot be exercised without a
    // person choosing a file, and the click is intercepted so the run can tell
    // that apart from a control that genuinely does nothing.
    window.__filePick = 0;
    fileEls.forEach(el => { el.click = function () { window.__filePick++; }; });
    window.__mut = 0;
    window.__saved = 0;
    const storeBefore = JSON.stringify(localStorage) + '|' + JSON.stringify(sessionStorage);
    const valsBefore = [...document.querySelectorAll('input,textarea')].map(i=>i.value).join(',');
    const hasHandler = !!(n.onclick || n.getAttribute('onclick')) ||
      !!n.closest('form') || n.tagName === 'SELECT' || n.tagName === 'A' ||
      // a listener attached with addEventListener leaves no inline attribute;
      // an id the script mentions is the next best evidence one exists, and it
      // keeps the message honest about what was actually found
      !!(n.id && (src.includes("'" + n.id + "'") || src.includes('"' + n.id + '"')));
    let dialog = false;
    // prompt() and confirm() block a headless run and return null/false, so a
    // working "Add bookmark" that asks for a URL was reported dead. Answering
    // them the way a person would is the only way to exercise the control.
    const origAlert = window.alert;
    const origPrompt = window.prompt;
    const origConfirm = window.confirm;
    window.alert = () => { dialog = true; };
    window.prompt = () => { dialog = true; return 'https://example.com'; };
    window.confirm = () => { dialog = true; return true; };
    try { n.click(); } catch (e) { out.errors.push(label + ' -> ' + e.message); }
    window.alert = origAlert;
    window.prompt = origPrompt;
    window.confirm = origConfirm;
    const openedPicker = window.__filePick > 0;
    fileEls.forEach((el, i) => { el.click = realClicks[i]; });
    await sleep(140);
    // a modal left open would swallow every later click and look like a bug
    for (const dlg of [...document.querySelectorAll('dialog[open], .modal.open, [role=dialog][data-open=true], .overlay:not(.hidden)')]) {
      try { dlg.querySelector('[data-close], .close, button')?.click(); } catch (e) {}
    }
    await sleep(40);
    const mutated = window.__mut || 0;
    const saved = window.__saved || 0;
    const storeAfter = JSON.stringify(localStorage) + '|' + JSON.stringify(sessionStorage);
    const valsAfter = [...document.querySelectorAll('input,textarea')].map(i=>i.value).join(',');
    const responded = mutated > 0 || saved > 0 ||
      storeBefore !== storeAfter || valsBefore !== valsAfter;
    if (dialog) return JSON.stringify(out);
    if (n.tagName === 'A') return JSON.stringify(out);
    // it asked for a file, which no headless run can supply
    if (openedPicker) { out.skipped.push(label); return JSON.stringify(out); }
    // A dropdown the app reads is an input, not a button. Clicking one cannot
    // change anything, so demanding a DOM change from it reported every unit
    // selector in the app as a dead control and blocked publication forever.
    // dev-converter was refused over exactly this.
    if (n.tagName === 'SELECT' && window.__readIds && window.__readIds(n)) return JSON.stringify(out);
    // A submit button delegates to its form's submit handler, and a browser
    // click does submit the form, so it is judged by what the form did rather
    // than by a listener attached to the button itself.
    if (!responded) out.dead.push(label + (hasHandler ? ' (handler present but nothing happened)' : ' (no handler, nothing happened)'));
  }
  return JSON.stringify(out);
}
""" % json.dumps(SELECTOR)


def scan(index_file: Path, timeout_ms: int = 25000) -> dict:
    """Return {dead: [...], errors: [...], missing: [...], controls: n}."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"dead": [], "errors": ["playwright not installed"], "missing": [],
                "controls": 0, "skipped": [], "unavailable": True}

    url = index_file.resolve().as_uri()
    console: list[str] = []
    data = {"dead": [], "errors": [], "missing": [], "skipped": [], "controls": 0}
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=["--no-sandbox"])
            try:
                page = b.new_page()
                page.on("console", lambda m: console.append(
                    f"{m.type}: {m.text}" if m.type in ("error",) else ""))
                page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
                page.goto(url, wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(700)
                data["controls"] = int(page.evaluate(COUNT))
                for i in range(data["controls"]):
                    # clear what the last click stored, then start the app again
                    # so quotas, counters and hidden notices are all back to zero
                    page.evaluate(CLEAR)
                    page.reload(wait_until="load", timeout=timeout_ms)
                    page.wait_for_timeout(150)
                    raw = page.evaluate(PROBE, i)
                    try:
                        got = json.loads(raw)
                    except Exception:  # noqa: BLE001
                        continue
                    for key in ("dead", "errors", "missing", "skipped"):
                        for item in got.get(key) or []:
                            if item not in data[key]:
                                data[key].append(item)
                # handlers are a property of the markup, so one fresh load does
                page.evaluate(CLEAR)
                page.reload(wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(200)
                for item in page.evaluate(MISSING) or []:
                    if item not in data["missing"]:
                        data["missing"].append(item)
            finally:
                # A launch or navigation failure used to escape here and take
                # the whole verify job down with a traceback, leaving Chromium
                # running. "Could not look" is a result, not a crash.
                b.close()
    except Exception as e:  # noqa: BLE001
        return {"dead": [], "errors": [f"scanner could not run: {str(e)[:200]}"],
                "missing": [], "controls": 0, "skipped": [],
                "unavailable": True}
    for c in console:
        if c and c not in data["errors"]:
            data["errors"].append(c)
    return data


def verdict(result: dict) -> bool:
    """True when the app looks healthy.

    If the scanner could not run at all, that is NOT healthy: it must never
    report a pass just because it was unable to look.
    """
    if result.get("unavailable"):
        return False
    return not (result.get("dead") or result.get("errors"))


if __name__ == "__main__":
    import sys

    p = Path(sys.argv[1])
    r = scan(p)
    print(json.dumps(r, indent=1)[:3000])
    print("VERDICT:", "clean" if verdict(r) else "bugs found")
