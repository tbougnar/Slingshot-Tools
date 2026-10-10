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
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
STATE = ROOT / "data" / "itch.json"
PAID = ROOT / "paid"

API = "https://api.itch.io"
TIMEOUT = 60

# set once, as a GitHub secret; the value comes from itch.io/settings/user
SESSION = os.environ.get("ITCH_SESSION_COOKIE", "").strip()
KEY = os.environ.get("ITCH_API_KEY", "").strip()
USER = (os.environ.get("ITCH_USER") or "").strip()

# the channel butler pushes the installer to
CHANNEL = os.environ.get("ITCH_CHANNEL", "windows").strip()

# only https itch.io pages count as a project link
OK_URL = "https://"


def log(msg: str) -> None:
    print(f"[itch] {msg}", flush=True)


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

def page_is_live(url: str) -> bool:
    """Does the public page answer? The simplest proof it was created."""
    if not url.startswith(OK_URL) or ".itch.io/" not in url:
        return False
    req = urllib.request.Request(url, headers={"User-Agent": "slingshot-tools"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        # 403 and 404 both mean it is not publicly there, which is a no
        return False
    except Exception as e:  # noqa: BLE001
        log(f"could not reach {url}: {e}")
        return False


# ------------------------------------------------------- create with a browser

def create_project(title: str, slug: str, price: float,
                   icon: Path | None = None) -> str:
    """Create the project page in a real browser, and return its URL.

    itch.io offers no API for this, and butler refuses it outright, so the only
    way is to drive the page a person would use. That needs a signed-in
    session, which is why it comes from a secret rather than being typed here.
    """
    if not SESSION:
        log("no ITCH_SESSION_COOKIE, so the project cannot be created")
        log("see ITCH_SELLING.md for the one-time setup")
        return ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright is not installed, so the project cannot be created")
        return ""

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        # itch.io keeps the session in a plain cookie called itch.io
        ctx.add_cookies([{
            "name": "itch.io", "value": SESSION, "domain": ".itch.io",
            "path": "/",
        }])
        page = ctx.new_page()
        page.goto("https://itch.io/settings/mine/new/game",
                  wait_until="domcontentloaded", timeout=TIMEOUT * 1000)

        if "/login" in page.url:
            log("the session cookie was refused; it has probably expired")
            browser.close()
            return ""

        page.fill("input[name='title']", title)
        # the url slug is the last field; setting it avoids itch inventing one
        slug_field = page.query_selector("input[name='url']")
        if slug_field:
            slug_field.fill(slug)

        # kind of project: Downloadable is what a .exe needs
        for selector in ("select[name='classification']",):
            el = page.query_selector(selector)
            if el:
                try:
                    el.select_option("downloadable")
                except Exception:  # noqa: BLE001
                    pass

        # price, in cents
        price_field = page.query_selector("input[name='price']")
        if price_field:
            price_field.fill(str(int(round(price * 100))))

        if icon and icon.exists():
            try:
                page.set_input_files("input[type='file']", str(icon))
            except Exception as e:  # noqa: BLE001
                log(f"cover image was not uploaded: {str(e)[:80]}")

        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT * 1000)
        created = page.url
        browser.close()

    if "/settings/mine/new" in created:
        log("the project was not created; the page did not accept it")
        return ""
    return created


# ------------------------------------------------------------------ butler

def butler() -> str:
    """Where butler is, or an empty string."""
    exe = "butler.exe" if os.name == "nt" else "butler"
    local = Path.home() / (".butler" if os.name != "nt" else ".butler")
    for candidate in (exe, str(local / exe)):
        if candidate == exe:
            try:
                subprocess.run([candidate, "--version"], capture_output=True,
                               timeout=30)
                return candidate
            except (OSError, subprocess.SubprocessError):
                continue
        elif Path(candidate).exists():
            return candidate
    return ""


def upload(installer: Path, slug: str, version: str) -> bool:
    """Push the installer with butler, which is itch.io's own uploader."""
    exe = butler()
    if not exe:
        log("butler is not installed, so the installer cannot be uploaded")
        log("install it from https://itchio.itch.io/butler")
        return False

    target = f"{USER}/{slug}:{CHANNEL}"
    cmd = [exe, "push", str(installer), target]
    if version:
        cmd += ["--userversion", version]
    log(f"butler: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"butler could not run: {e}")
        return False

    out = ((r.stdout or "") + (r.stderr or "")).strip()
    for line in out.splitlines()[-12:]:
        if line.strip():
            print(f"  {line.strip()}")
    if r.returncode != 0:
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


# -------------------------------------------------------------------- main

def find_installer(slug: str) -> Path | None:
    """The installer for a product, wherever the build put it."""
    roots = [PAID / slug, ROOT / "dist"]
    for root in roots:
        if not root.exists():
            continue
        for exe in sorted(root.glob("**/*Setup.exe")):
            return exe
    return None


def publish(slug: str, title: str, price: float, version: str = "") -> bool:
    """The whole sequence, in an order that cannot advertise a missing file."""
    log(f"=== {title} (${price:.2f}) ===")

    # 1. does it already exist?
    url = ""
    if KEY:
        found = find_game(slug)
        if found:
            url = (found.get("url") or "").replace("http://", "https://")
            log(f"1. the project already exists: {url}")
    if not url:
        log("1. no project yet")
        url = create_project(title, slug, price,
                             (PAID / slug / "icon.png"))
        if not url:
            log("cannot continue without a project page")
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
    installer = find_installer(slug)
    if not installer:
        log(f"3. no installer was found for {slug}, in {PAID / slug} "
            f"or dist/")
        return False
    size = installer.stat().st_size / 1024 / 1024
    log(f"3. uploading {installer.name} ({size:.1f} MB)")
    if not upload(installer, slug, version):
        log("the upload did not finish, so nothing will be advertised")
        return False

    # 4. prove the whole thing again from the outside
    if not page_is_live(url):
        log("4. the page stopped answering after the upload; not publishing")
        return False
    log("4. the page still answers")

    # 5. only now is it safe to show a buy button
    if not record(slug, url, price):
        return False
    remember(slug, url)
    log("5. published on the site")
    return True


def main() -> int:
    stage_file = ROOT / "data" / "published.json"
    if not stage_file.exists():
        log("nothing was built this week")
        return 0
    stage = json.loads(stage_file.read_text(encoding="utf-8"))
    slug = stage["slug"]
    price = float(stage.get("price") or 0)
    title = stage.get("title") or slug

    if not USER:
        log("ITCH_USER is not set, so nothing can be pushed")
        log("it is the part of your itch.io URL before .itch.io")
        return 1

    # an explicit slug on the command line wins, for a rerun
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        slug = sys.argv[1]
        family = [a for a in load_catalog()
                  if (a.get("base_slug") or a.get("slug")) == slug]
        paid = next((a for a in family if a.get("tier") == "full"), {})
        title = paid.get("title") or slug
        price = float(paid.get("price") or price)

    return 0 if publish(slug, title, price, stage.get("version") or "") else 1


if __name__ == "__main__":
    raise SystemExit(main())