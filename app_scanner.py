"""Interactive bug scanner for a generated app.

Opens the real page in a headless browser, clicks every control, and reports
controls that do nothing - no DOM change, no state change, no navigation, no
dialog - plus any JavaScript error, unhandled rejection or missing handler.
"""
from __future__ import annotations

import json
from pathlib import Path

PROBE = r"""
(async () => {
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

  const sel = 'button, a[href], input[type=button], input[type=submit], [role=button], select, [onclick]';
  const nodes = [...document.querySelectorAll(sel)].filter(n => n.offsetParent !== null || n.tagName === 'SELECT');
  for (const n of nodes.slice(0, 120)) {
    const label = (n.tagName + ':' + (n.innerText || n.value || n.getAttribute('aria-label') || n.id || '')).slice(0, 60).trim();
    const text = (n.innerText || n.value || n.getAttribute('aria-label') || '').trim();
    if (/^(delete|remove|reset|clear|empty|wipe)\b/i.test(text)) { out.skipped.push(label); continue; }
    // A submit button on a form with a required field is refused by the browser
    // before the handler ever runs, so the app looks broken when it is not.
    // Fill anything empty first, which is what a person would do.
    if (n.tagName === 'BUTTON' && n.type === 'submit' || n.tagName === 'INPUT' && n.type === 'submit') {
      const form = n.closest('form');
      for (const f of form ? [form] : []) {
        for (const el of f.querySelectorAll('input,textarea')) {
          if (!el.value) {
            try {
              el.value = el.type === 'number' ? '1' : 'sample';
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            } catch (e) {}
          }
        }
      }
    }
    // A control that only opens a file picker cannot be exercised without a
    // person choosing a file, and the click is intercepted so the run can tell
    // that apart from a control that genuinely does nothing.
    window.__filePick = 0;
    fileEls.forEach(el => { el.click = function () { window.__filePick++; }; });
    window.__mut = 0;
    const storeBefore = JSON.stringify(localStorage) + '|' + JSON.stringify(sessionStorage);
    const valsBefore = [...document.querySelectorAll('input,textarea')].map(i=>i.value).join(',');
    const hasHandler = !!(n.onclick || n.getAttribute('onclick')) ||
      !!n.closest('form') || n.tagName === 'SELECT' || n.tagName === 'A';
    let dialog = false;
    const origAlert = window.alert; window.alert = () => { dialog = true; };
    try { n.click(); } catch (e) { out.errors.push(label + ' -> ' + e.message); }
    window.alert = origAlert;
    const openedPicker = window.__filePick > 0;
    fileEls.forEach((el, i) => { el.click = realClicks[i]; });
    await sleep(140);
    // a modal left open would swallow every later click and look like a bug
    for (const dlg of [...document.querySelectorAll('dialog[open], .modal.open, [role=dialog][data-open=true], .overlay:not(.hidden)')]) {
      try { dlg.querySelector('[data-close], .close, button')?.click(); } catch (e) {}
    }
    await sleep(40);
    const mutated = window.__mut || 0;
    const storeAfter = JSON.stringify(localStorage) + '|' + JSON.stringify(sessionStorage);
    const valsAfter = [...document.querySelectorAll('input,textarea')].map(i=>i.value).join(',');
    const responded = mutated > 0 || storeBefore !== storeAfter || valsBefore !== valsAfter;
    if (dialog) continue;
    if (n.tagName === 'A') continue;
    // it asked for a file, which no headless run can supply
    if (openedPicker) { out.skipped.push(label); continue; }
    // A dropdown the app reads is an input, not a button. Clicking one cannot
    // change anything, so demanding a DOM change from it reported every unit
    // selector in the app as a dead control and blocked publication forever.
    // dev-converter was refused over exactly this.
    if (n.tagName === 'SELECT' && window.__readIds && window.__readIds(n)) continue;
    // A submit button delegates to its form's submit handler, and a browser
    // click does submit the form, so it is judged by what the form did rather
    // than by a listener attached to the button itself.
    if (!responded) out.dead.push(label + (hasHandler ? ' (handler present but nothing happened)' : ' (no handler, nothing happened)'));
  }
  // controls that look interactive but have no handler at all
  for (const n of [...document.querySelectorAll(sel)].slice(0, 120)) {
    if (!(n.onclick || n.getAttribute('onclick') || n.tagName === 'A' || n.tagName === 'SELECT' || n.closest('form'))) {
      out.missing.push((n.tagName + ':' + (n.innerText || n.value || '')).slice(0, 50).trim());
    }
  }
  out.controls = nodes.length;
  return JSON.stringify(out);
})()
"""


def scan(index_file: Path, timeout_ms: int = 25000) -> dict:
    """Return {dead: [...], errors: [...], missing: [...], controls: n}."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"dead": [], "errors": ["playwright not installed"], "missing": [],
                "controls": 0, "skipped": [], "unavailable": True}

    url = index_file.resolve().as_uri()
    console: list[str] = []
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
                raw = page.evaluate(PROBE)
            finally:
                # A launch or navigation failure used to escape here and take
                # the whole verify job down with a traceback, leaving Chromium
                # running. "Could not look" is a result, not a crash.
                b.close()
    except Exception as e:  # noqa: BLE001
        return {"dead": [], "errors": [f"scanner could not run: {str(e)[:200]}"],
                "missing": [], "controls": 0, "skipped": [],
                "unavailable": True}
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"dead": [], "errors": ["probe returned nothing"], "missing": [],
                "controls": 0, "skipped": [], "unavailable": True}
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