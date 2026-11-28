"""Put a built tool on itch.io, then and only then publish it on the site.

itch.io has no API for creating a project, so the order is deliberate:

1. **check** whether the project already exists, through the read-only API
2. **create** it if it does not, in a real browser, signed in as you
3. **upload** the installer with butler, which is itch.io's own tool
4. **verify** the page is really live and really has the download on it
5. **publish** it in the site catalog, which is the last step

Step 5 comes last on purpose. Before this existed, the catalog marked a tool as
sold before anything could buy it, so the site showed a buy button that led to
a payment endpoint which could never take money. Now the site only ever
advertises something itch.io has already confirmed it is serving.

Nothing here is guessed. If a step cannot be proven, it stops and says so.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from urllib.parse import quote, urlparse

import auditlog

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
STATE = ROOT / "data" / "itch.json"
# The Discord steps are in a different job, on a fresh checkout, so the only
# way they can know what actually went on sale is a pointer written here.
HANDOFF = ROOT / "data" / "published.json"
PAID = ROOT / "paid"

API = "https://api.itch.io"
TIMEOUT = 60

# Where a project is created. The old address, /settings/mine/new/game,
# answers 404 - the page moved - and that 404 was read for months as "the
# session expired", which sent everyone looking in the wrong place.
CREATE_URL = "https://itch.io/game/new"

# set once, as a GitHub secret; the value comes from itch.io/settings/user
SESSION = os.environ.get("ITCH_SESSION_COOKIE", "").strip()
KEY = os.environ.get("ITCH_API_KEY", "").strip()
USER = (os.environ.get("ITCH_USER") or "").strip()
# Each product owns one itch.io project. The old shared project accumulated
# every installer in one Purchase block; that is why a $3 purchase could see
# four tools. There is deliberately no store-wide fallback URL here: a product
# with no page of its own stays unpublished until that page is created.
LAST_URL = ""
SHARED_PROJECT = "slingshot-tools"

# the channel butler pushes the installer to
# butler requires the target as user/project:channel and refuses anything else
# with "missing channel".
#
# Each product has its own project now, so one stable channel per product is
# enough. The slug-derived name is kept: it makes a butler target readable and
# means an operator who pins ITCH_CHANNEL for one tool cannot accidentally
# reuse another tool's channel.
#
# ITCH_CHANNEL overrides this for anyone who genuinely wants one channel.
CHANNEL = os.environ.get("ITCH_CHANNEL", "").strip()


def channel_for(slug: str) -> str:
    """The itch.io channel one product's build goes to."""
    if CHANNEL:
        return CHANNEL
    clean = "".join(c for c in slug.lower() if c.isalnum() or c in "-_")
    return f"{clean or 'build'}-win"

# only https itch.io pages count as a project link
OK_URL = "https://"


def _say(text: str) -> None:
    """Print a line without letting the console's code page abort the run.

    butler writes UTF-8 progress lines. On a Windows runner the console is
    cp1252, so print() raised UnicodeEncodeError inside upload() - after the
    push had already happened - and the release died with no record of the
    sale. A log line must never be able to decide whether something was
    published.
    """
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, "replace").decode(enc, "replace"), flush=True)


def log(msg: str) -> None:
    _say(f"[itch] {msg}")


# ------------------------------------------------------------------ the API

def api(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """One authenticated call to the itch.io server-side API."""
    if not KEY:
        return 0, "no ITCH_API_KEY"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read().decode("utf-8")
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:200]


def games() -> list:
    st, data = api("GET", "/profile/games")
    if st != 200 or not isinstance(data, dict):
        log(f"cannot list projects ({st}): {data}")
        return []
    return data.get("games") or []


def find_game(slug: str) -> dict | None:
    """The project for a slug, matched on its url, which is unambiguous."""
    want = slug.lower().replace("_", "-")
    for g in games():
        url = (g.get("url") or "").rstrip("/").lower()
        if url.endswith(f"/{want}"):
            return g
        if (g.get("title") or "").strip().lower() == want.replace("-", " "):
            return g
    return None


# ------------------------------------------------------------- page is real

def page_probe(url: str) -> tuple[bool | None, str]:
    """Is the public page there?

    Three outcomes, not two. True and False are facts. None means the page
    could not be reached or answered with something that is not a verdict,
    which is not the same as the page being absent and must not be reported as
    though it were.
    """
    if not url.startswith(OK_URL) or ".itch.io/" not in url:
        return False, "not an itch.io page"
    req = urllib.request.Request(url, headers={"User-Agent": "slingshot-tools"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        # 403 and 404 are verdicts: it is not publicly there.
        if e.code in (403, 404):
            return False, f"HTTP {e.code}"
        # 429 and 5xx are the server declining to answer right now.
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:90]


def build_is_listed(url: str, filename: str, attempts: int = 3) -> bool:
    """Is this exact build on the page, the way a buyer would see it?

    itch.io publishes a build asynchronously after the upload returns, so the
    page can answer for a moment before the file appears. Retried rather than
    concluded, because concluding too early means a product that is genuinely
    on its way is never sold. Cached per URL and filename for the same reason
    page_is_live caches: one fetch, not one per question.
    """
    key = f"{url}|{filename}"
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key][0]
    needle = quote(filename.lower())
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "slingshot-tools"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(400_000).decode("utf-8", "replace").lower()
                status = r.status
            found = needle in body or filename.lower() in body
            if found:
                _PROBE_CACHE[key] = (True, f"HTTP {status}")
                return True
            # A successful fetch that does not list the build yet is the
            # normal case, not a verdict: butler returns as soon as the bytes
            # are accepted and says "Build is now processing". Returning here
            # used to end the release after the first unlucky fetch, a few
            # seconds after the push, while the build was still being
            # published. Keep looking until the attempts run out.
        except Exception:  # noqa: BLE001
            pass
        if i < attempts - 1:
            time.sleep(min(3 * (i + 1), 8))
    _PROBE_CACHE[key] = (False, "not listed")
    return False


_PROBE_CACHE: dict[str, tuple[bool, str]] = {}


def _buy_box(body: str) -> str:
    """The purchase block of an itch.io page, lowercased, or "" when absent."""
    m = re.search(r'class="buy_message"[^>]*>(.*?)</div>', body, re.S | re.I)
    if m:
        return m.group(1).lower()
    # Some layouts put the price on the buy button itself ("Buy Now $3.00").
    m = re.search(r'<div class="donate">(.{0,400}?)</div>', body, re.S | re.I)
    return m.group(1).lower() if m else ""


def _advertised_minimum(body: str) -> float | None:
    """The least a buyer can pay on this page, or None when it is not shown.

    itch.io marks a pay-what-you-want page with "Name your own price" and, when
    there is a floor, "Pay $3.00 or more". A page with no floor says only the
    first, and its button reads "Download Now": that page sells nothing.
    """
    box = _buy_box(body)
    if not box:
        return None
    m = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", box)
    if "name your own price" in box:
        if m and "or more" in box:
            return float(m.group(1))
        return 0.0
    if "free" in box:
        return 0.0
    if m:
        return float(m.group(1))
    return None


def asks_for_price(body: str, price: float) -> bool:
    """Does the store page charge exactly the price the site advertises?

    A money gate has to fail closed. An unreadable page is not evidence that
    the price is right: publishing on a guess is how the store advertised
    $3.00 while its button said "Download Now". Retrying is cheap; charging
    the wrong amount is not.
    """
    minimum = _advertised_minimum(body)
    if minimum is None:
        log("   the purchase block could not be read, so the price is unverified")
        return False
    # Exact match, not "at least". A $5.00 floor also satisfies ">= 3.00",
    # which would advertise $3.00 and charge $5.00 at checkout.
    return abs(minimum - price) < 0.005


def price_is_asked(url: str, price: float, attempts: int = 2) -> bool:
    """ask_for_price, over the wire. A page that cannot be read is refused."""
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "slingshot-tools"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(600_000).decode("utf-8", "replace")
            return asks_for_price(body, price)
        except Exception:  # noqa: BLE001
            if i < attempts - 1:
                time.sleep(2)
    log(f"   could not read the price on {url}, so it is not verified")
    return False


def _probe_cached(url: str):
    """One answer per URL per process.

    publish() asks about the same store page several times and the selftests run
    it repeatedly. Re-probing on each call while itch.io is rate-limiting made
    a full report take over twenty minutes, which is long enough to time out.
    """
    if url not in _PROBE_CACHE:
        _PROBE_CACHE[url] = page_probe(url)
    return _PROBE_CACHE[url]


def page_is_live(url: str, attempts: int = 3) -> bool:
    """Does the public page answer, retrying while it declines to.

    itch.io rate-limits and a single probe alternated between answering and not
    on consecutive calls, so one unlucky request decided the store project did
    not exist. The publish path then told the account holder to go and create a
    project they had already created, which is the opposite of help.
    """
    live, detail = _probe_cached(url)
    if live is not None:
        return live
    for i in range(1, attempts):
        time.sleep(min(2 ** i, 6))
        _PROBE_CACHE.pop(url, None)
        live, detail = page_probe(url)
        if live is not None:
            _PROBE_CACHE[url] = (live, detail)
            return live
    log(f"   {url} did not answer after {attempts} tries ({detail})")
    return False


def project_from_url(url: str) -> str:
    """The itch.io project name, the first segment after the host."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[0].lower() if parts else ""


def project_url(slug: str) -> str:
    """This product's own live itch.io page, or nothing.

    The catalogue is the authority once it has been set with set_itch_url.py.
    It used to hold the one shared page for every product, which is exactly the
    bug that put four installers behind one Purchase button. A URL whose
    project is not this product is therefore refused, not inherited. For a
    product that has never been recorded, the account plus the slug gives the
    only safe guess, and the public page has to prove it is really there.
    """
    clean = slug.strip().lower()
    # A page that declines to answer is not the same as not existing: it has
    # been rate-limited before. This path stops rather than borrowing another
    # product's page, because a wrong page is worse than no page at all.
    for a in load_catalog():
        if (a.get("base_slug") or a.get("slug")) != slug:
            continue
        candidate = str(a.get("itch_url") or "").strip().rstrip("/")
        if not candidate:
            continue
        project = project_from_url(candidate)
        if project == SHARED_PROJECT:
            log(f"   the catalogue still points at the old shared project "
                f"({candidate}); one product needs one page")
            continue
        if project and project != clean:
            log(f"   the catalogue points {slug} at another product's page "
                f"({project}); refusing to sell one tool as another")
            return ""
        if page_is_live(candidate):
            return candidate
        log(f"   the catalogued page for {slug} is not live: {candidate}")
        return ""

    if USER:
        derived = f"https://{USER}.itch.io/{clean}"
        if page_is_live(derived):
            return derived
    if KEY:
        found = find_game(clean)
        url = str(found.get("url") or "").replace("http://", "https://") \
            if found else ""
        if url and project_from_url(url) == clean and page_is_live(url):
            return url.rstrip("/")
    return ""


# ------------------------------------------------------- create with a browser

def session_cookie() -> str:
    """The itch.io login session, from whatever shape it arrives in.

    The cookie is named ``itchio_token``, not ``itch.io``. A pasted browser
    Cookie header often arrives whole, so the value is pulled out of it and
    everything else dropped: analytics cookies are noise, and Cloudflare's
    ``cf_clearance`` is bound to one IP and browser, so sending it from a
    runner on a different IP gets the request blocked outright.
    """
    raw = (SESSION or "").strip()
    if not raw:
        return ""
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith("itchio_token="):
            return part.split("=", 1)[1].strip()
        # a bare value was pasted instead of a header
        if "=" not in part and "itchio" not in part and len(part) > 20:
            return part
    return ""


def mint_session() -> str:
    """Log in with the account credentials and return a fresh itchio_token.

    This is the answer to a session cookie that expires. The cookie was the
    only thing the publisher needed and the only thing that ever stopped it:
    itch.io has no API for creating a project, so a browser session is
    unavoidable, but a session does not have to be pasted. The account's user
    name and password do not expire, so the publisher logs in and mints a
    cookie whenever the stored one is refused.

    That converts a credential that breaks every few weeks into two that do not
    expire, and it is the difference between a pipeline that needs a person
    every month and one that runs itself.

    Returns the cookie, or "" if the login did not work. The password is never
    logged and never written to disk.
    """
    user = (os.environ.get("ITCH_LOGIN") or os.environ.get("ITCH_USERNAME")
            or "").strip()
    password = os.environ.get("ITCH_PASSWORD") or ""
    if not user or not password:
        log("no ITCH_LOGIN and ITCH_PASSWORD, so a new session cannot be made")
        return ""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright is not installed, so a new session cannot be made")
        return ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto("https://itch.io/login", wait_until="domcontentloaded",
                      timeout=TIMEOUT * 1000)
            # itch.io renders its login form after load, so waiting only for
            # the document got there before the inputs existed and every named
            # selector missed. Wait for an input to appear instead.
            try:
                page.wait_for_selector("input", timeout=TIMEOUT * 1000)
            except Exception:  # noqa: BLE001
                pass
            try:
                page.wait_for_timeout(1500)
            except Exception:  # noqa: BLE001
                pass

            filled_user = _fill_first(page, ("input[name='user']",
                                             "input[name='username']",
                                             "input[name='login']",
                                             "input[id='user']",
                                             "#user", "input[type='email']"),
                                      user)
            filled_pass = _fill_first(page, ("input[name='password']",
                                             "input[type='password']",
                                             "#password"),
                                      password)
            if not (filled_user and filled_pass):
                # Last resort that does not depend on any of itch.io's naming:
                # the password box is the one of type password, and the user
                # box is whichever other input comes first. Any login form on
                # the page has that shape.
                filled_user, filled_pass = _fill_by_shape(page, user, password)
            if not (filled_user and filled_pass):
                # The one case that no amount of fixing the form solves.
                # itch.io sits behind Cloudflare Turnstile, which shows a "Just
                # a moment..." interstitial with a single hidden
                # cf-turnstile-response input to a headless browser. It is a
                # bot check, not a login form, and it cannot be automated away
                # without evading an anti-abuse control, which is not
                # something this will do.
                try:
                    title = page.title() or ""
                    turnstile = bool(page.query_selector(
                        "input[name='cf-turnstile-response']"))
                except Exception:  # noqa: BLE001
                    title, turnstile = "", False
                if turnstile or "just a moment" in title.lower():
                    log("itch.io served a Cloudflare bot challenge instead of "
                        "the login form")
                    log("  a headless browser cannot pass a Turnstile check, "
                        "and working around one is not something this does")
                    log("  the way in is a session cookie from a browser you "
                        "have logged in with:")
                    log("  gh secret set ITCH_SESSION_COOKIE "
                        "--repo tbougnar/Slingshot-Tools")
                    auditlog.blocked(
                        "itch-login",
                        reason="itch.io served a Cloudflare Turnstile "
                               "challenge; a headless browser cannot pass it",
                        evidence={"title": title})
                    browser.close()
                    return ""
                log(f"the login form was not what was expected "
                    f"(user field: {filled_user}, password field: "
                    f"{filled_pass})")
                try:
                    log(f"  the page is titled {title!r} and has "
                        f"{len(page.query_selector_all('input'))} input(s): "
                        + ", ".join(
                            (el.get_attribute("name") or el.get_attribute("id")
                             or el.get_attribute("type") or "?")
                            for el in page.query_selector_all("input")[:8]))
                except Exception:  # noqa: BLE001
                    pass
                browser.close()
                return ""

            _click_first(page, ("button[type='submit']", "input[type='submit']",
                                "form button", "button:has-text('Log in')",
                                "button:has-text('Sign in')"))
            page.wait_for_load_state("networkidle", timeout=TIMEOUT * 1000)
            landed = (page.url or "")

            token = ""
            for c in ctx.cookies():
                if c.get("name") == "itchio_token" and c.get("value"):
                    token = c["value"]
                    break
            browser.close()

            if not token:
                log(f"logging in did not produce a session cookie "
                    f"(landed on {landed})")
                return ""
            if "/login" in landed or "itch.io/login" in landed:
                log("itch.io refused those credentials")
                return ""
            log("logged in and got a fresh session")
            return token
    except Exception as e:  # noqa: BLE001
        log(f"could not log in: {str(e)[:110]}")
        return ""


def _fill_by_shape(page, user: str, password: str) -> tuple[bool, bool]:
    """Fill a login form by its shape rather than by any field name.

    The password box is the input of type password, and the user box is the
    first other input on the page. Every login form has that arrangement, so
    this keeps working if itch.io renames a field, and it is what caught the
    fact that none of the named selectors matched.
    """
    try:
        inputs = page.query_selector_all("input")
    except Exception:  # noqa: BLE001
        return False, False
    pass_done = False
    user_done = False
    for el in inputs:
        try:
            kind = (el.get_attribute("type") or "text").lower()
        except Exception:  # noqa: BLE001
            continue
        if kind == "password" and not pass_done:
            try:
                el.fill(password)
                pass_done = True
            except Exception:  # noqa: BLE001
                pass
        elif kind in ("text", "email", "") and not user_done:
            # a hidden field or a submit button is not the user box
            try:
                if el.is_hidden():
                    continue
            except Exception:  # noqa: BLE001
                pass
            try:
                el.fill(user)
                user_done = True
            except Exception:  # noqa: BLE001
                pass
        if pass_done and user_done:
            break
    return user_done, pass_done


def _fill_first(page, selectors: tuple[str, ...], value: str) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
        except Exception:  # noqa: BLE001
            continue
        if el is None:
            continue
        try:
            el.fill(value)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _click_first(page, selectors: tuple[str, ...]) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
        except Exception:  # noqa: BLE001
            continue
        if el is None:
            continue
        try:
            el.click()
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def working_session() -> str:
    """A session cookie that works, from the stored one or a fresh login.

    The stored cookie is tried first because it is free. Only when it is
    refused, or absent, does this spend a login.
    """
    cookie = session_cookie()
    if cookie and check_session(cookie):
        return cookie
    if not cookie:
        log("no stored session cookie")
    fresh = mint_session()
    if not fresh:
        return ""
    if not check_session(fresh):
        log("the freshly minted session was refused too")
        return ""
    return fresh


def _form_state(cookie: str) -> bool | None:
    """Open the create form with this cookie. True, False, or None = unknown.

    True  the form is there, so the session works
    False the page sent us to /login, so the session is dead
    None  no browser could be started, or neither appeared, so this says
          nothing about the cookie
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context()
            ctx.add_cookies([{"name": "itchio_token", "value": cookie,
                              "domain": ".itch.io", "path": "/"}])
            page = ctx.new_page()
            try:
                page.goto(CREATE_URL, wait_until="domcontentloaded",
                          timeout=TIMEOUT * 1000)
            except Exception as e:  # noqa: BLE001
                log(f"could not open the create form: {str(e)[:80]}")
                browser.close()
                return None
            found = refused = False
            # Cloudflare's JS challenge clears itself in a few seconds in a
            # browser it accepts, so this waits rather than judging the first
            # paint - which is how a working page was once called a challenge.
            for _ in range(40):
                if "/login" in page.url:
                    refused = True
                    break
                if page.query_selector("input[name='game[title]']"):
                    found = True
                    break
                page.wait_for_timeout(500)
            browser.close()
            if found:
                return True
            if refused:
                return False
            return None
    except Exception as e:  # noqa: BLE001
        log(f"could not start a browser to check the session: {str(e)[:80]}")
        return None


def check_session(cookie: str = "") -> bool:
    """Is the cookie still good? Asked by opening the form it has to open.

    A plain GET cannot answer this any more. itch.io sits behind Cloudflare,
    which hands a script a challenge and a browser the page, so urllib
    reported "refused" for a perfectly good session. Because a refused cookie
    is meant to trigger a fresh login, that meant a valid session caused a
    login attempt instead - and the login is behind a captcha, so the whole
    publish stopped while everything was actually fine.
    """
    cookie = cookie or session_cookie()
    if not cookie:
        return False
    state = _form_state(cookie)
    if state is not None:
        if not state:
            log("the create form redirected to the login page, so the "
                "session cookie has expired")
        return state
    # No browser on this machine. A plain request is all that is left, and it
    # is the unreliable answer this function exists to avoid.
    req = urllib.request.Request(
        CREATE_URL,
        headers={"Cookie": f"itchio_token={cookie}",
                 "User-Agent": "slingshot-tools"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read()
            landed = r.geturl()
    except Exception as e:  # noqa: BLE001
        log(f"could not check the session: {e}")
        return False
    # a refused session redirects to the login page
    return "/login" not in landed and "itch.io/login" not in landed


def create_project(title: str, slug: str, price: float,
                   icon: Path | None = None, session: str = "",
                   blurb: str = "", description: str = "") -> str:
    """Create the project page in a real browser, and return its URL.

    itch.io has no API for this - the serverside reference is all reads - and
    butler says outright that it will not create one, so the only way is to
    submit the form a person submits.

    Every selector below was read off the live form rather than guessed. The
    first version of this function asked for input[name='title'],
    input[name='url'] and input[name='price'], none of which exist: the real
    names are nested under game[], and the price is not on the page at all
    until the paid button in the pricing widget is pressed, which swaps
    game[suggested_price] out for game[min_price]. It filled nothing and
    clicked blindly, and it never once created anything.

    The session is passed in rather than read here, because the caller may
    have just minted it by logging in. Reading the stored cookie from inside
    this function is what let an expired cookie reach the browser and produce
    a redirect to the login page instead of a clear message.
    """
    cookie = session or session_cookie()
    if not cookie:
        log("no session cookie, so the project cannot be created")
        return ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright is not installed, so the project cannot be created")
        return ""

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        # the name matters: the session cookie is "itchio_token"
        ctx.add_cookies([{
            "name": "itchio_token", "value": cookie,
            "domain": ".itch.io", "path": "/",
        }])
        page = ctx.new_page()
        try:
            page.goto(CREATE_URL, wait_until="domcontentloaded",
                      timeout=TIMEOUT * 1000)
        except Exception as e:  # noqa: BLE001
            log(f"could not open the create form: {str(e)[:120]}")
            browser.close()
            return ""

        # The form only appears once the session is accepted, and a refused
        # one lands on /login, so both are waited for rather than assumed.
        refused = False
        for _ in range(40):
            if "/login" in page.url or "itch.io/login" in page.url:
                refused = True
                break
            if page.query_selector("input[name='game[title]']"):
                break
            page.wait_for_timeout(500)
        if refused:
            log("the session cookie was refused; it has expired or was "
                "invalidated by logging out")
            browser.close()
            return ""
        if not page.query_selector("input[name='game[title]']"):
            log(f"the create form did not appear (landed on {page.url})")
            browser.close()
            return ""

        try:
            page.fill("input[name='game[title]']", title)
            # the slug is set rather than left for itch to invent, because the
            # butler target and every stored URL are derived from it
            page.fill("input[name='game[slug]']", slug)
            if blurb:
                page.fill("input[name='game[short_text]']", str(blurb)[:140])
            if description:
                page.fill("textarea[name='game[description]']",
                          str(description)[:4000])

            # These are tools, not games. selectize owns this dropdown, so the
            # underlying <select> only ever carries the current value and
            # filling it would change nothing visible or submitted.
            page.eval_on_selector(
                "select[name='game[user_classification]']",
                "s => s && s.selectize ? s.selectize.setValue('tool') : null")

            # Paid: the price is not on the form until this button is pressed.
            # Pressing it removes game[suggested_price] from the document and
            # replaces it with a single text field named game[min_price].
            page.click("button.payment_mode_paid")
            page.wait_for_selector("input[name='game[min_price]']",
                                   timeout=10000)
            page.fill("input[name='game[min_price]']", f"${price:.2f}")

            # Released, and honest about being generated.
            page.check("input[name='game[published]'][value='published']",
                       force=True)
            page.check(
                "input[name='ai_disclosure[ai_generated]'][value='yes']",
                force=True)

            if icon and icon.exists():
                try:
                    page.set_input_files("input[type='file']", str(icon))
                except Exception as e:  # noqa: BLE001
                    log(f"cover image was not uploaded: {str(e)[:80]}")

            page.click("button.save_btn")
            page.wait_for_load_state("domcontentloaded",
                                     timeout=TIMEOUT * 1000)
        except Exception as e:  # noqa: BLE001
            log(f"the create form could not be filled: {str(e)[:200]}")
            browser.close()
            return ""

        created = page.url
        # If itch refused the submission it stays on the form and shows why;
        # reading that here is the difference between "created" and silence.
        complaint = ""
        if created.rstrip("/") == CREATE_URL.rstrip("/"):
            try:
                complaint = page.eval_on_selector_all(
                    ".error, .errors, .notice, [class*=error]",
                    "els => els.map(e => e.textContent.trim())"
                    ".filter(t => t).slice(0, 3).join(' | ')")
            except Exception:  # noqa: BLE001
                complaint = ""
        browser.close()

    if created.rstrip("/") == CREATE_URL.rstrip("/") or "/login" in created:
        log("the project was not created; the page did not accept it"
            + (f": {complaint[:200]}" if complaint else ""))
        return ""
    log(f"created {created}")
    return created


# ------------------------------------------------------------------ butler

def butler() -> str:
    """Where butler is, or an empty string.

    The workflow downloads it with 7z into ./butler and appends that folder to
    GITHUB_PATH, which only reaches later steps and only when the folder
    really holds the executable. Checking the places it can actually land is
    what stops upload() from reporting "not installed" while butler is sitting
    in the working directory.
    """
    exe = "butler.exe" if os.name == "nt" else "butler"
    for cand in (Path.home() / ".butler" / exe,
                 ROOT / "butler" / exe,
                 ROOT / exe,
                 ROOT / "bin" / exe):
        if cand.exists():
            return str(cand)
    try:
        subprocess.run([exe, "--version"], capture_output=True, timeout=30)
        return exe
    except (OSError, subprocess.SubprocessError):
        return ""


def _identity_file(secret: str) -> str:
    """Write the API key where butler expects it and return the path.

    butler v15 does not take a key on the command line at all: -i/--identity
    is the path of a file holding the token. Passing the key itself, under
    either --api-key or --api_key, is refused as an unknown flag before butler
    reaches the network, so uploads could never have authenticated.
    """
    import tempfile
    fd, name = tempfile.mkstemp(prefix="butler-identity-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(secret)
    try:
        os.chmod(name, 0o600)
    except OSError:
        pass
    return name


def upload(installer: Path, slug: str, version: str,
           project: str = "") -> bool:
    """Push the installer with butler, itch.io's own uploader.

    `project` is the itch.io project to push into, which is not the product
    slug. The store is one project holding every product as a build, so
    pushing to user/<product-slug> asks for a project that does not exist and
    itch.io answers 'invalid game'. The target comes from the page the product
    was resolved to, so the two cannot drift apart.

    butler authenticates with the API key, not with the browser session, so
    this half keeps working after the session cookie expires.
    """
    exe = butler()
    if not exe:
        log("butler is not installed, so the installer cannot be uploaded")
        log("install it from https://itchio.itch.io/butler")
        return False

    # The target is user/project:channel, so without the user there is nothing
    # to push to. Butler answers an empty user with 'invalid target (bad
    # user)', which is a remote call that cannot succeed and says less than
    # the truth. Refuse here instead, before anything leaves the machine.
    if not USER:
        log("no itch.io user is set, so there is no project to push the "
            "build to")
        log("set it with: gh variable set ITCH_USER <your itch.io user>")
        return False

    target = f"{USER}/{project or slug}:{channel_for(slug)}"
    cmd = [exe, "push", str(installer), target]
    if version:
        cmd += ["--userversion", version]
    # butler itself tells CI to hand over the key in the environment rather
    # than in a file or an argument, because an argument is visible in the
    # process list to everything else on the runner.
    env = dict(os.environ)
    ident = None
    if KEY:
        env["BUTLER_API_KEY"] = KEY
    log(f"butler: pushing to {target}")
    try:
        # Bytes, not text. On the Windows runner Python decodes a text pipe with
        # the console code page, and butler writes progress bytes that cp1252
        # cannot represent. The reader thread raised UnicodeDecodeError, which
        # hid butler's own output and left the caller unable to tell a failed
        # push from a good one. Decode explicitly, and never fail on a byte.
        r = subprocess.run(cmd, capture_output=True, timeout=1800, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"butler could not run: {e}")
        return False
    finally:
        if ident:
            try:
                os.unlink(ident)
            except OSError:
                pass

    out = ((r.stdout or b"") + (r.stderr or b"")).decode(
        "utf-8", "replace").strip()
    for line in out.splitlines()[-12:]:
        if line.strip():
            _say(f"  {line.strip()}")
    if r.returncode != 0:
        if "403" in out or "own the target" in out:
            log("butler was refused: the project does not exist yet")
        log(f"butler failed with exit {r.returncode}")
        return False
    return True


# ------------------------------------------------------------- the catalog

def load_catalog() -> list:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"cannot read the catalog: {e}")
        return []


def save_catalog(apps: list) -> None:
    CATALOG.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")


def record(slug: str, url: str, price: float) -> bool:
    """Put the URL in the catalog and only then show the product for sale."""
    apps = load_catalog()
    family = [a for a in apps
              if (a.get("base_slug") or a.get("slug")) == slug]
    if not family:
        log(f"{slug} is not in the catalog")
        return False
    if not (1.0 <= price <= 10.0):
        log(f"the price ${price:.2f} is outside the $1-$10 rule, refusing")
        return False

    for entry in family:
        # Only the paid edition gets a store URL, and only once its own build
        # is on the store. The free edition is served from this site and has
        # never been uploaded to itch.io, so recording a store URL for it is a
        # claim that is not true. set_itch_url.py --all enforces the same rule
        # and this enforces it on every release, which is the path that runs.
        if entry.get("tier") == "basic":
            entry.pop("itch_url", None)
            continue
        entry["itch_url"] = url
        entry["built"] = True
        entry["published"] = True
    save_catalog(apps)
    log(f"{slug} is on itch.io at {url}")
    log(f"  and is now shown on the site at ${price:.2f}")
    return True


def remember(slug: str, url: str) -> None:
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    state[slug] = {"url": url, "at": int(__import__("time").time())}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def handoff(slug: str, title: str, price: float, url: str) -> None:
    """Record the product that is really on sale for the Discord steps.

    The installer job publishes from the paid artifact, so the generator's
    stage file is never present there. The article and announcement scripts
    both read data/published.json, and used to say "no published product" in
    the same run that had just put the tool on itch.io. Write the pointer right
    after the publication succeeds, so it can only describe a real sale.
    """
    body = {"slug": slug, "title": title, "price": float(price),
            "itch_url": url, "published": True,
            "at": int(__import__("time").time())}
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


# -------------------------------------------------------------------- main

def find_installer(slug: str, title: str = "",
                   dist: Path | None = None) -> Path | None:
    """The installer for one product, and only that product.

    The dist/ folder is shared between builds, so a name match is required:
    taking whatever .exe happens to be there would upload one tool's installer
    under another tool's page, and nobody would notice until a customer
    installed the wrong thing.

    There are two builders and they name their output differently:
    build_installer_app.py writes '<title>-Setup.exe' and make_app.py writes
    '<slug>-Setup.exe'. The store is selling the titles - 'Base64 and URL
    encoding tool-Setup.exe', 'Offline password manager-Setup.exe' - so a
    slug-only match returns nothing for exactly the products that are live.
    Both forms are accepted, each still as an exact match, so a product is
    found under the name it actually shipped with and a foreign installer is
    never substituted.
    """
    own = PAID / slug
    if own.exists():
        for exe in sorted(own.glob("**/*Setup.exe")):
            return exe

    def norm(text: str) -> str:
        s = text.lower().replace("-", "").replace("_", "")
        s = s.replace(" ", "").replace("slingshottool", "")
        return s.replace("setup.exe", "").replace("setup", "")

    needles = {norm(slug)}
    if not title:
        title = _title_for_slug(slug)
    if title:
        needles.add(norm(title))
    needles.discard("")

    folder = dist if dist is not None else (ROOT / "dist")
    candidates = sorted(folder.glob("**/*Setup.exe"))

    # an exact stem match first, so a leftover file from an older naming
    # cannot win over the one this build actually produced
    for exe in candidates:
        if norm(exe.name) in needles:
            return exe
    # Anything less than an exact match is refused. This used to fall back to
    # `needle in stem or stem in needle`, which is a substring test in both
    # directions: with a shared dist/ folder it could hand back one product's
    # installer for another product entirely. A missing installer stops the
    # release, which is recoverable. Shipping the wrong tool is not.
    return None


def _title_for_slug(slug: str) -> str:
    """The product's title, from its build or from the catalogue.

    build_installer_app.py names the installer after the title, so the title is
    what the file on the store is called. Prefer the concept.json that travelled
    with the artifact; fall back to the catalogue the site serves.
    """
    try:
        meta = json.loads((PAID / slug / "concept.json").read_text(encoding="utf-8"))
        if isinstance(meta, dict) and meta.get("title"):
            return str(meta["title"]).strip()
    except (OSError, ValueError):
        pass
    try:
        apps = json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(apps, list):
        return ""
    for e in apps:
        if (e.get("base_slug") or e.get("slug")) == slug and e.get("tier") == "full":
            return str(e.get("title") or "").strip()
    return ""


def publish(slug: str, title: str, price: float, version: str = "") -> bool:
    """The whole sequence, in an order that cannot advertise a missing file."""
    global LAST_URL
    LAST_URL = ""
    log(f"=== {title} (${price:.2f}) ===")

    # 1. does this product have a project of its own?
    # itch.io has no create/list API this pipeline can rely on. The catalogue
    # records each product's page, and the public page is the proof it exists.
    # A missing page is never borrowed from another product: the old shared
    # project was the reason one Purchase block offered several tools.
    url = project_url(slug)
    if url:
        log(f"1. this product has its own live project: {url}")
    else:
        log("1. no page of its own yet, so one has to be created")
        # Creating a project is the one thing the API key cannot do, because
        # itch.io has no endpoint for it. It needs a browser session, and the
        # login that would provide one is behind a bot challenge.
        cookie = working_session()
        if not cookie:
            log("   itch.io has no API for creating a project, and its web")
            log("   login is behind a bot challenge that this will not work")
            log("   around. Create one project for THIS product by hand:")
            log("     https://itch.io/game/new")
            log("   set classification Downloadable and minimum price "
                f"${price:.2f}, make it public, then record it:")
            log("     python set_itch_url.py <slug> "
                f"https://slingshot-tools.itch.io/{slug}")
            log("   after that every release uploads with the API key alone")
            return False
        url = create_project(title, slug, price, (PAID / slug / "icon.png"),
                             session=cookie)
        if not url:
            log("   the project could not be created")
            return False
        url = url.replace("http://", "https://").rstrip("/")
        log(f"1. created: {url}")

    # 2. the page has to be publicly there before anything else
    if not page_is_live(url):
        log(f"2. the page is not publicly reachable yet: {url}")
        log("   a draft project is private; publish it on itch.io first")
        return False
    log("2. the page is live")

    # 3. the file
    installer = find_installer(slug, title=title)
    if not installer:
        log(f"3. no installer was found for {slug}, in {PAID / slug} "
            f"or dist/")
        return False
    size = installer.stat().st_size / 1024 / 1024
    log(f"3. uploading {installer.name} ({size:.1f} MB)")
    if not upload(installer, slug, version,
                    project=urlparse(url).path.strip("/").split("/")[0]):
        log("the upload did not finish, so nothing will be advertised")
        return False

    # 4. prove the whole thing again from the outside
    if not page_is_live(url):
        log("4. the page stopped answering after the upload; not publishing")
        return False
    # The page answering is not enough. A project can answer while holding an
    # old build or no paid uploads at all. Advertising a product whose own
    # installer is not listed means taking money for a download nobody can be
    # given, so this product's file has to be on this product's page.
    #
    # butler returns as soon as the bytes are accepted; itch.io publishes the
    # build a little later. The first run of this checked once, seconds after
    # the push, concluded the file was absent, and left a product that WAS
    # uploaded unsold. Drop any earlier answer and give publication time.
    _PROBE_CACHE.pop(f"{url}|{installer.name}", None)
    if not build_is_listed(url, installer.name, attempts=20):
        log(f"4. the page answers but does not list {installer.name}, so this "
            "product is not being sold")
        log("   something else may occupy the build's channel, or itch.io has "
            "not published it yet; either way it is not for sale until the "
            "file is on the page")
        return False
    log(f"4. the page answers and lists {installer.name}")

    # 4b. a page that lets a buyer pay nothing is not selling a $3.00 product.
    # The project was created as pay-what-you-want, so this is not theoretical:
    # the site showed $3.00 and the store's button said "Download Now".
    if not price_is_asked(url, price):
        log(f"4. the page does not ask for ${price:.2f}: it is a "
            "pay-what-you-want page with no minimum, so a buyer can pay $0.00")
        log("   set the minimum price under the project's Pricing on itch.io, "
            "then run this again; the paid tier stays hidden until then")
        return False
    log(f"4. the page asks for at least ${price:.2f}")

    # 5. only now is it safe to show a buy button
    if not record(slug, url, price):
        return False
    remember(slug, url)
    LAST_URL = url
    log("5. published on the site")
    return True


def _built_products() -> list[str]:
    """Which products actually have a paid build on this machine.

    paid/ is what the installer job built and what the upload came from, so it
    is the authority, in the same way the artifact is for the installer.
    """
    if not PAID.is_dir():
        return []
    out = []
    for d in sorted(PAID.iterdir()):
        if d.is_dir() and (d / "app" / "index.html").exists():
            out.append(d.name)
    return out


def _describe(slug: str) -> tuple[str, float]:
    """Title and price for a product, preferring what the build itself says."""
    title, price = slug, 0.0
    meta = PAID / slug / "concept.json"
    if meta.exists():
        try:
            got = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(got, dict):
                title = got.get("title") or title
        except (ValueError, OSError):
            pass
    # The paid entry, whichever order the family is in. This used to take the
    # first entry with a matching slug and stop there, so a family written
    # basic-first described the product as the free edition, with its price
    # of zero, and the caller then quietly substituted the default price of
    # $3.00. The site advertised the catalogue price and itch.io charged the
    # substituted one. It also asked for entry["full"], a nested shape the
    # catalogue does not have, so the branch it took always found nothing.
    family = [a for a in load_catalog()
              if (a.get("base_slug") or a.get("slug")) == slug]
    paid = next((a for a in family if a.get("tier") == "full"), {})
    if paid:
        title = paid.get("title") or title
        try:
            price = float(paid.get("price") or price)
        except (TypeError, ValueError):
            pass
    return title, price


def main() -> int:
    stage_file = ROOT / "data" / "published.json"
    built = _built_products()

    if len(built) > 1:
        log(f"{len(built)} paid builds are present: {', '.join(built)}")
        log("refusing to guess which one to publish")
        auditlog.blocked("itch-publish",
                         reason="more than one paid build to choose from",
                         evidence={"builds": built})
        return 1

    slug = built[0] if built else ""

    if not stage_file.exists():
        if slug:
            # The stage file is untracked and absent on a fresh checkout, which
            # is every installer job. The build is still here and still needs
            # publishing, so it is published from what the build says.
            log(f"no published.json, but {slug} has a paid build; publishing it")
            title, price = _describe(slug)
            if not (1.0 <= price <= 10.0):
                price = float(os.environ.get("PRICE_START") or 3.0)
            auditlog.started("itch-publish", job=slug,
                             action=f"publish {title}",
                             tool="itch_publish.py",
                             reason="no stage file; taken from the paid build")
            ok = publish(slug, title, price)
            if ok:
                # The Discord steps run later on a fresh checkout; hand them
                # the pointer now, only after the sale has really succeeded.
                handoff(slug, title, price, LAST_URL or project_url(slug))
                auditlog.succeeded("itch-publish", job=slug,
                                   evidence={"exit_code": 0, "slug": slug,
                                             "price": price})
            else:
                auditlog.failed("itch-publish", job=slug,
                                error="itch_publish.publish returned false",
                                evidence={"exit_code": 1, "slug": slug})
            return 0 if ok else 1

        # Returning 0 here claimed success for doing nothing, and the release
        # gate read that as "the paid edition is on itch.io and advertised".
        # The store was fetched after that run and still listed no products.
        # A job that published nothing has not published, so it says so.
        log("there is no paid build and no published.json, so there is "
            "nothing to publish")
        log("this is not a successful publication; the paid tier stays hidden")
        auditlog.failed("itch-publish",
                        error="no paid build and no published.json; this was "
                              "previously reported as a success",
                        evidence={"exit_code": 1})
        return 1

    stage = json.loads(stage_file.read_text(encoding="utf-8"))
    slug = stage["slug"]
    price = float(stage.get("price") or 0)
    title = stage.get("title") or slug

    if not USER:
        log("ITCH_USER is not set, so nothing can be pushed")
        log("it is the part of your itch.io URL before .itch.io")
        auditlog.blocked("itch-publish", job=slug,
                         reason="ITCH_USER is not set; the store credentials "
                                "exist only as repository secrets")
        return 1

    # an explicit slug on the command line wins, for a rerun
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        slug = sys.argv[1]
        family = [a for a in load_catalog()
                  if (a.get("base_slug") or a.get("slug")) == slug]
        paid = next((a for a in family if a.get("tier") == "full"), {})
        title = paid.get("title") or slug
        price = float(paid.get("price") or price)

    auditlog.started("itch-publish", job=slug, action=f"publish {title}",
                     tool="itch_publish.py",
                     reason="the Windows installer was built and verified")
    ok = publish(slug, title, price, stage.get("version") or "")
    if ok:
        handoff(slug, title, price, LAST_URL or project_url(slug))
        auditlog.succeeded("itch-publish", job=slug,
                           evidence={"exit_code": 0, "slug": slug,
                                     "price": price})
    else:
        auditlog.failed("itch-publish", job=slug,
                        error="itch_publish.publish returned false",
                        evidence={"exit_code": 1, "slug": slug})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())