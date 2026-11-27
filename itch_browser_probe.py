"""Open itch.io's real create-project page in a browser and report what happens.

Three things had never been checked together, and every earlier attempt
guessed one of them:

  1. the address. It is https://itch.io/game/new. The old
     /settings/mine/new/game answers 404, which was read for months as "the
     session expired" when it only meant the page had moved.
  2. whether the stored session cookie is still accepted.
  3. whether Cloudflare lets a headless browser through from a runner at all.

This only reads. It fills nothing and submits nothing, so it is safe to run
as often as needed.

    python itch_browser_probe.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CREATE_URL = "https://itch.io/game/new"
CHALLENGE_MARKERS = ("just a moment", "cf-turnstile", "challenge-platform",
                     "checking your browser")


def log(msg: str) -> None:
    print(f"[browser-probe] {msg}", flush=True)


def token_only(raw: str) -> str:
    """The itchio_token value, whether the secret holds it or a full header."""
    for part in (raw or "").split(";"):
        part = part.strip()
        if part.startswith("itchio_token="):
            return part.split("=", 1)[1].strip()
        if "=" not in part and len(part) > 20:
            return part
    return ""


def main() -> int:
    raw = os.environ.get("ITCH_SESSION_COOKIE", "").strip()
    token = token_only(raw)
    if not token:
        log("ITCH_SESSION_COOKIE holds no itchio_token")
        return 1
    log(f"token parsed: {len(token)} chars")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright is not installed")
        return 1

    # headless is tried first because it needs no display. HEADED=1 opens a
    # real window instead, which is the difference between a browser Cloudflare
    # recognises as a browser and one it does not; under xvfb on a runner the
    # window has nowhere to be drawn, but it is still a headed browser.
    headed = os.environ.get("HEADED", "").strip() not in ("", "0", "false")
    log(f"launching {'headed' if headed else 'headless'} chromium")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        ctx = browser.new_context()
        ctx.add_cookies([{"name": "itchio_token", "value": token,
                          "domain": ".itch.io", "path": "/"}])
        page = ctx.new_page()
        started = time.time()
        try:
            page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:  # noqa: BLE001
            log(f"goto failed: {str(e)[:200]}")
            browser.close()
            return 1
        log(f"loaded in {time.time() - started:.1f}s -> {page.url}")

        body = ""
        try:
            body = page.content()
        except Exception:  # noqa: BLE001
            pass
        low = body.lower()

        if any(m in low for m in CHALLENGE_MARKERS):
            log("RESULT: CLOUDFLARE CHALLENGE - a headless browser from this "
                "address never reached the form")
            browser.close()
            return 2
        if "/login" in page.url:
            log("RESULT: bounced to /login - the session cookie is dead")
            browser.close()
            return 3

        title_field = page.query_selector("input[name='game[title]']")
        slug_field = page.query_selector("input[name='game[slug]']")
        csrf = page.query_selector("input[name='csrf_token']")
        paid_btn = page.query_selector("button.payment_mode_paid")
        submit = page.query_selector("input[type='submit']")
        submit_txt = ""
        for b in page.query_selector_all("button"):
            t = (b.text_content() or "").strip()
            if "view page" in t.lower() or t.lower() in ("save", "publish"):
                submit_txt = t
                break

        log(f"page title: {page.title()!r}")
        log(f"game[title] field: {'FOUND' if title_field else 'missing'}")
        log(f"game[slug] field:  {'FOUND' if slug_field else 'missing'}")
        log(f"csrf_token field:  {'FOUND' if csrf else 'missing'}")
        log(f"paid-mode button:  {'FOUND' if paid_btn else 'missing'}")
        log(f"input[type=submit]: {'FOUND' if submit else 'missing'}"
            + (f" ({submit_txt})" if submit_txt else ""))
        log(f"signed in as: "
            f"{page.eval_on_selector_all('a', 'els => els.map(e=>e.textContent.trim()).filter(t=>/slingshot/i.test(t)).slice(0,3)')}")

        # What the classification dropdown really offers, which the static HTML
        # does not say: only the current value is rendered until it is opened.
        try:
            opts = page.eval_on_selector(
                "select[name='game[user_classification]']",
                "s => Array.from(s.options).map(o => o.value + '=' + o.text)")
            log(f"classification options as rendered: {opts}")
        except Exception as e:  # noqa: BLE001
            log(f"classification read failed: {str(e)[:120]}")

        if title_field and slug_field and csrf:
            log("RESULT: FORM REACHED - creation can be automated")
            browser.close()
            return 0
        log("RESULT: page loaded but the form was not found")
        browser.close()
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
