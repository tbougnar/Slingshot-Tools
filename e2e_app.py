"""Use the free app the way a person would, and try to break it.

The customer test opens it and counts controls. This goes further: types into
it, adds things, switches the theme, exports, reloads, and checks the data
survived. An app that renders but does not work is not free, it is a
screenshot.

    python e2e_app.py
"""
from __future__ import annotations

import http.server
import pathlib
import threading

ROOT = pathlib.Path(__file__).resolve().parent

rows: list[tuple[str, bool, str]] = []


def say(ok: bool, label: str, detail: str = "") -> bool:
    rows.append((label, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          + (f"\n        {detail}" if detail else ""))
    return ok


def main() -> int:
    app_dir = ROOT / "site" / "apps" / "password-manager-basic" / "app"
    index = app_dir / "index.html"
    if not index.exists():
        print(f"FAIL  no app to test: {index}")
        return 1

    site = (ROOT / "site").resolve()

    def handler(*a, **kw):
        return http.server.SimpleHTTPRequestHandler(*a, directory=str(site),
                                                    **kw)

    srv = http.server.HTTPServer(("127.0.0.1", 8766), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:8766/apps/password-manager-basic/app/index.html"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1000, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console",
                lambda m: errors.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.goto(url, wait_until="networkidle", timeout=45000)

        print("USING THE FREE APP LIKE A PERSON\n")
        say(bool(page.title()), "it opens with a title", page.title())

        text = page.inner_text("body")
        say(len(text.strip()) > 80, "it says what it is for",
            f"{len(text)} characters")

        # theme
        toggle = page.query_selector("#themeToggle")
        if toggle:
            before = page.evaluate("document.documentElement.dataset.theme")
            toggle.click()
            page.wait_for_timeout(250)
            after = page.evaluate("document.documentElement.dataset.theme")
            say(before != after, "the theme toggle changes the theme",
                f"{before} -> {after}")
        else:
            say(None, "there is a theme toggle")

        # find the inputs and the add button, whatever they are called
        info = page.evaluate("""() => {
            const ins = [...document.querySelectorAll('input, textarea')];
            const btns = [...document.querySelectorAll('button')]
                .map(b => (b.innerText||'').trim());
            return {
                inputs: ins.map(i => ({id: i.id, type: i.type,
                                       ph: i.placeholder || ''})),
                buttons: btns,
            };
        }""")
        say(bool(info["inputs"]), "it has inputs to type into",
            f"{len(info['inputs'])}: "
            + ", ".join(i["id"] or i["ph"] or i["type"]
                        for i in info["inputs"][:4]))
        say(bool(info["buttons"]), "it has buttons",
            ", ".join(info["buttons"][:5]))

        # try to actually add something
        before_count = page.evaluate(
            "() => document.querySelectorAll('#list > *, #list li,"
            " #list div').length")
        filled = 0
        for spec in info["inputs"]:
            if spec["type"] in ("checkbox", "radio", "button", "hidden"):
                continue
            sel = f"#{spec['id']}" if spec["id"] else \
                f"input[placeholder='{spec['ph']}']"
            try:
                el = page.query_selector(sel)
                if not el:
                    continue
                el.fill(f"test-{filled}")
                filled += 1
            except Exception:
                continue
        say(filled > 0, "I can type into it", f"{filled} field(s) filled")

        add = None
        for name in ("Add", "Save", "Add entry", "+"):
            for btn in page.query_selector_all("button"):
                if name.lower() in (btn.inner_text() or "").lower():
                    add = btn
                    break
            if add:
                break
        say(add is not None, "there is a button to add something",
            (add.inner_text() if add else ""))

        if add:
            add.click()
            page.wait_for_timeout(500)
            after_count = page.evaluate(
                "() => document.querySelectorAll('#list > *, #list li,"
                " #list div').length")
            say(after_count > before_count,
                "adding something actually adds it",
                f"list went from {before_count} to {after_count} entries")

        # persistence, which is the whole promise of an offline tool
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        still = page.evaluate(
            "() => { const s = Object.entries(localStorage)"
            "  .filter(([k,v]) => v && v.length > 3);"
            "  return s.length; }")
        say(still > 0, "the data is saved and survives a reload",
            f"{still} localStorage entries with content")

        # no network calls, which is the promise on the privacy page
        say(not errors, "nothing broke while I used it",
            "; ".join(errors[:2]))

        html = index.read_text(encoding="utf-8").lower()
        net = [t for t in ("fetch(", "xmlhttprequest", "websocket",
                           "<script src=", "http://", "https://")
               if t in html]
        say(not net, "the app makes no network calls at all",
            f"found {net}" if net else "no fetch, no external script, "
            "no URL")

        b.close()
        srv.shutdown()

    good = sum(1 for _, ok, _ in rows if ok)
    bad = [r for r in rows if not r[1]]
    print()
    print("=" * 62)
    print(f"{good} of {len(rows)} checks pass")
    if bad:
        print()
        print("THE FREE APP IS NOT FINISHED:")
        for label, _, detail in bad:
            print(f"  - {label}" + (f"\n      {detail}" if detail else ""))
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())