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
  const origErr = console.error;
  console.error = function (...a) { out.errors.push('console: ' + a.join(' ')); origErr.apply(console, a); };

  const sel = 'button, a[href], input[type=button], input[type=submit], [role=button], select, [onclick]';
  const nodes = [...document.querySelectorAll(sel)].filter(n => n.offsetParent !== null || n.tagName === 'SELECT');
  for (const n of nodes.slice(0, 120)) {
    const label = (n.tagName + ':' + (n.innerText || n.value || n.getAttribute('aria-label') || n.id || '')).slice(0, 60).trim();
    const text = (n.innerText || n.value || n.getAttribute('aria-label') || '').trim();
    if (/^(delete|remove|reset|clear|empty|wipe)\b/i.test(text)) { out.skipped.push(label); continue; }
    window.__mut = 0;
    const storeBefore = JSON.stringify(localStorage) + '|' + JSON.stringify(sessionStorage);
    const valsBefore = [...document.querySelectorAll('input,textarea')].map(i=>i.value).join(',');
    const hasHandler = !!(n.onclick || n.getAttribute('onclick')) ||
      !!n.closest('form') || n.tagName === 'SELECT' || n.tagName === 'A';
    let dialog = false;
    const origAlert = window.alert; window.alert = () => { dialog = true; };
    try { n.click(); } catch (e) { out.errors.push(label + ' -> ' + e.message); }
    window.alert = origAlert;
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
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox"])
        page = b.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"
                    if m.type in ("error",) else ""))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(url, wait_until="load", timeout=timeout_ms)
        page.wait_for_timeout(700)
        raw = page.evaluate(PROBE)
        b.close()
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"dead": [], "errors": ["probe returned nothing"], "missing": [],
                "controls": 0}
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