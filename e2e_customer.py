"""End to end, as a stranger who has never seen this project before.

Every other test in here checks something the code believes about itself. This
one opens the site in a real browser and tries to buy the product the way a
person would: read the page, find the product, open the options, follow the
buy button, and see whether money can change hands.

It is deliberately unkind. It does not call any project function, it does not
trust any internal state, and it does not stop at the first sign of success.
Where the journey dead-ends, it follows the dead end to prove it is one.

    python e2e_customer.py            against the live site
    python e2e_customer.py --local    against site/ served here
"""
from __future__ import annotations

import http.server
import pathlib
import sys
import threading
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parent
LIVE = "https://tbougnar.github.io/Slingshot-Tools/"

results: list[tuple[str, bool, str]] = []
step = 0


def say(ok: bool | None, label: str, detail: str = "") -> bool | None:
    """None means a warning: not a failure, but not a pass either."""
    global step
    step += 1
    mark = {True: "PASS", False: "FAIL", None: "WARN"}[ok]
    results.append((label, ok is not False, detail))
    print(f"  {step:2}. {mark}  {label}" + (f"\n        {detail}" if detail
                                           else ""))
    return ok


def serve_local(port: int = 8765):
    site = (ROOT / "site").resolve()

    def handler(*a, **kw):
        return http.server.SimpleHTTPRequestHandler(*a, directory=str(site),
                                                    **kw)

    srv = http.server.HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}/index.html"


def main() -> int:
    local = "--local" in sys.argv
    srv = None
    if local:
        srv, url = serve_local()
        print(f"(against the local copy, {url})\n")
    else:
        url = LIVE
        print(f"(against the live site, {url})\n")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console",
                lambda m: errors.append(f"console {m.type}: {m.text}")
                if m.type == "error" else None)

        # ---------------------------------------------------------- 1. arrive
        print("ARRIVING")
        page.goto(url, wait_until="networkidle", timeout=45000)
        title = page.title()
        say(bool(title), "the page loads and has a title", title)

        cards = page.query_selector_all(".card")
        say(bool(cards), "at least one product is shown",
            f"{len(cards)} card(s) on the page")

        body = page.inner_text("body")
        say("everyday" in body.lower(), "the page says what the site is for")

        # ---------------------------------------------------- 2. find the paid one
        print("\nFINDING THE PRODUCT")
        paid = None
        for c in cards:
            if "full edition" in (c.inner_text() or "").lower():
                paid = c
                break
        say(paid is not None, "a paid edition is visible",
            "nothing on the page is marked as a paid edition"
            if paid is None else "")
        if paid is None:
            b.close()
            return report()

        text = paid.inner_text()
        say("$" in text, "it shows a price",
            [ln for ln in text.splitlines() if "$" in ln][:1])

        # ---------------------------------------------------- 3. open the options
        print("\nOPENING THE BUY OPTIONS")
        btn = paid.query_selector("button")
        say(btn is not None, "it has a button to click")
        if btn is not None:
            say("option" in (btn.inner_text() or "").lower(),
                "the button says what it does",
                (btn.inner_text() or "").strip())
            btn.click()
            page.wait_for_timeout(600)

        dlg = page.query_selector("#dlg")
        opened = bool(dlg) and "open" in (dlg.get_attribute("class") or "")
        say(opened, "the options actually open")
        if not opened:
            b.close()
            return report()

        opts = page.query_selector_all(".opt")
        say(len(opts) >= 2, "a free and a paid option are both offered",
            f"{len(opts)} option(s)")

        free = next((o for o in opts
                     if "free" in (o.inner_text() or "").lower()), None)
        full = next((o for o in opts
                     if "full" in (o.inner_text() or "").lower()), None)
        say(free is not None, "there is a free option")
        say(full is not None, "there is a paid option")
        if full is not None:
            say("$" in (full.inner_text() or ""), "the paid option shows a "
                "price", [ln for ln in (full.inner_text() or "").splitlines()
                          if "$" in ln][:1])

        # --------------------------------------------------- 4. follow the buy link
        print("\nFOLLOWING THE BUY BUTTON")
        target = page.evaluate(
            """() => {
                const o = [...document.querySelectorAll('.opt')]
                    .find(x => (x.innerText||'').toLowerCase().includes('full'));
                if (!o) return null;
                const m = (o.getAttribute('onclick')||'').match(/'(.*)'/);
                return m ? m[1] : null;
            }""")
        if not target:
            say(False, "the paid option links anywhere at all",
                "it has no destination, so clicking it does nothing")
            b.close()
            return report()

        q = parse_qs(urlparse(target).query)
        itch = (q.get("itch") or [""])[0]
        say(bool(itch), "the buy link carries a real itch.io address",
            f"itch={itch!r}" + ("  <- EMPTY, there is nowhere to buy"
                                if not itch else ""))

        say(urlparse(target).netloc.endswith("itch.io")
            or bool(itch), "the link would take me to itch.io",
            f"host={urlparse(target).netloc or '(none)'}")

        # ------------------------------------------- 5. try the free thing instead
        print("\nTAKING THE FREE OPTION INSTEAD")
        free_href = page.evaluate(
            """() => {
                const o = [...document.querySelectorAll('.opt')]
                    .find(x => (x.innerText||'').toLowerCase().includes('free'));
                if (!o) return null;
                const m = (o.getAttribute('onclick')||'').match(/'(.*)'/);
                return m ? m[1] : null;
            }""")
        say(bool(free_href), "the free option has somewhere to go",
            free_href or "no destination")
        if free_href and "/apps/" in free_href:
            page.goto(free_href, wait_until="networkidle", timeout=45000)
            app = page.inner_text("body")
            say(len(app.strip()) > 60, "the free app actually opens",
                f"{len(app)} characters of real interface")
            usable = page.query_selector_all("input, button, textarea, select")
            say(len(usable) >= 3, "it has controls I can use",
                f"{len(usable)} control(s)")

        # ------------------------------------------------ 6. does anything work
        print("\nCHECKING THE PAGE HAS NO BROKEN PARTS")
        say(not errors, "no javascript errors while doing all of that",
            "; ".join(errors[:2]))

        b.close()
        if srv:
            srv.shutdown()

    return report()


def report() -> int:
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [r for r in results if not r[1]]
    print()
    print("=" * 62)
    print(f"{passed} of {len(results)} steps reached where a customer would go")
    if failed:
        print()
        print("THE CUSTOMER GETS STUCK HERE:")
        for label, _, detail in failed:
            print(f"  - {label}" + (f"\n      {detail}" if detail else ""))
    print("=" * 62)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())