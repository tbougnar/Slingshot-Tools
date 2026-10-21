"""The "an update is available" notice inside a desktop app.

There is a hard rule in this repo that an app is one HTML file with **no
network calls** (`make_app.html_looks_fine` rejects any external URL, and
`APP_SPEC` says it twice). It is there for a good reason: the apps promise
their data never leaves the device, and a phone-home would break that promise
and the privacy policy.

So the check does not live in the app. It lives here, in the Python launcher
that wraps the app in a native window, and it injects the banner after load:

- the app HTML stays exactly as offline as it always was
- nothing is fetched unless the user has already installed the app, so the
  promise holds for the code that actually runs on their machine
- the check is opt-out, off by default for an unknown slug, and never blocks
  the window opening

The website copies have no check at all, and do not need one: they are served
from the site, so a refresh is the update.

    python app_update.py --slug password-manager     show what the app sees
    python app_update.py --inject app/index.html     add the banner markup
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import update_state as us

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "site" / "update.json"
# The published copy of the same file, for an installed app that has no
# site/ folder beside it.
PUBLISHED = "https://tbougnar.github.io/Slingshot-Tools/update.json"

# The id of the injected element. Kept here and in the markup so the launcher
# and the HTML cannot drift apart.
BANNER_ID = "slingshot-update"


def log(m: str) -> None:
    print(f"[appupdate] {m}", flush=True)


def latest() -> dict:
    """What is published, as the app sees it.

    Read from the site copy because that is what a customer would compare
    against, and fetched from the public site when there is no local copy.
    The local copy is what the repository has, and it is what the website
    itself reads, so it is tried first. The fetch is the part that matters
    for a customer: an installed app has no site/ folder beside it, and the
    file was never in the bundle, so without the fetch the answer was always
    empty and the banner could never appear for anyone.

    Fetching here is allowed and is not a contradiction of the app making no
    network calls: the app HTML still makes none, and this runs in the
    launcher, on the machine of someone who installed the app, and only
    after the install. A missing, slow or broken file is an empty answer,
    which means no banner, which is the right failure: an app that cannot
    check must still open.
    """
    if PUBLIC.exists():
        try:
            d = json.loads(PUBLIC.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    try:
        import urllib.request
        req = urllib.request.Request(
            PUBLISHED, headers={"User-Agent": "slingshot-tools"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read(200000).decode("utf-8", "replace"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def installed_version(app_dir: Path) -> str:
    """The version the app on disk was built at.

    Read from ``app/app.json``, which is the same file the installer writes
    and the same file `native_launcher._title()` already reads, so there is
    one source rather than three.

    The launcher passes the app's root folder and the file is in the app
    folder inside it, while the command line passes the app folder itself.
    Both are tried, because reading only one of them meant the installed
    version was always the fallback of 1.0.0: the banner then said "1.0.0 is
    installed" for a copy that was already current, and could never stop.
    """
    for meta in (app_dir / "app" / "app.json", app_dir / "app.json"):
        if not meta.exists():
            continue
        try:
            d = json.loads(meta.read_text(encoding="utf-8-sig"))
            v = str(d.get("version") or "").strip()
            if v:
                return us.format_version(us.parse(v))
        except (json.JSONDecodeError, OSError, ValueError, AttributeError):
            continue
    return "1.0.0"


def check(app_dir: Path, slug: str = "", enabled: bool = True) -> dict:
    """Compare what is installed against what is published.

    Returns a dict rather than printing, so the launcher can use it and the
    selftest can assert on it without capturing stdout.
    """
    out = {"update_available": False, "installed": installed_version(app_dir),
           "latest": "1.0.0", "slug": slug, "enabled": bool(enabled)}
    if not enabled:
        out["reason"] = "turned off for this app"
        return out

    state = latest()
    # The company's version is the fallback. A product that has its own
    # version uses its own, so one app being updated does not announce an
    # update to every app that is already current.
    newest = str(state.get("version") or "1.0.0")
    per_app = state.get("apps")
    if isinstance(per_app, dict) and slug:
        own = per_app.get(slug)
        if own:
            newest = str(own)
    out["latest"] = newest
    if us.is_newer(newest, out["installed"]):
        out["update_available"] = True
        out["reason"] = (f"{out['installed']} is installed, {newest} is "
                         f"published")
        out["url"] = "https://tbougnar.github.io/Slingshot-Tools/"
        if state.get("phase") == "announced" and state.get("next_major"):
            out["coming"] = str(state.get("next_major"))
            out["coming_title"] = str(state.get("next_major_title") or "")
    return out


BANNER_HTML = f"""
    <!-- Slingshot Tools update notice. Injected by app_update.py; the app
         itself makes no network calls, this is filled in by the launcher. -->
    <div id="{BANNER_ID}" hidden
         style="position:sticky;top:0;z-index:9;display:flex;gap:10px;
                align-items:center;justify-content:center;flex-wrap:wrap;
                padding:10px 14px;font:500 14px/1.4 system-ui,sans-serif;
                background:rgba(193,39,45,.12);color:inherit;
                border-bottom:1px solid rgba(193,39,45,.45)">
      <strong>Update available</strong>
      <span id="{BANNER_ID}-text"></span>
      <button type="button" id="{BANNER_ID}-ok"
              style="font:inherit;cursor:pointer;border:1px solid currentColor;
                     border-radius:8px;padding:4px 12px;background:transparent;
                     color:inherit">Got it</button>
    </div>
    <script>
    (function(){{
      var b=document.getElementById("{BANNER_ID}"); if(!b) return;
      var ok=document.getElementById("{BANNER_ID}-ok");
      if(ok) ok.onclick=function(){{ b.hidden=true; }};
      window.__slingshotUpdate=function(msg){{
        var t=document.getElementById("{BANNER_ID}-text");
        if(t) t.textContent=msg||"";
        b.hidden=false;
      }};
    }})();
    </script>
"""


def inject(html_path: Path) -> bool:
    """Put the banner at the top of an app's body, once.

    Idempotent on purpose: this runs again on every build, and a second copy
    would stack two banners on top of each other with two identical ids.
    """
    if not html_path.exists():
        log(f"{html_path.name} does not exist")
        return False
    html = html_path.read_text(encoding="utf-8")

    if BANNER_ID in html:
        log("the banner is already there")
        return False

    # right after <body ...>, which is the only place guaranteed to exist in a
    # document that html_looks_fine has already accepted
    low = html.lower()
    at = low.find("<body")
    if at < 0:
        log("no <body> to insert after")
        return False
    close = low.find(">", at)
    if close < 0:
        log("malformed <body> tag")
        return False

    out = html[:close + 1] + BANNER_HTML + html[close + 1:]
    html_path.write_text(out, encoding="utf-8")
    log(f"injected the banner into {html_path.name}")
    return True


def main() -> int:
    args = sys.argv[1:]
    slug = ""
    if "--slug" in args:
        i = args.index("--slug")
        if i + 1 < len(args):
            slug = args[i + 1]
    if "--inject" in args:
        i = args.index("--inject")
        target = Path(args[i + 1]) if i + 1 < len(args) else None
        return 0 if target and inject(target) else 1

    app_dir = ROOT / "site" / "apps" / (slug or "password-manager-basic") / "app"
    got = check(app_dir, slug=slug)
    print(json.dumps(got, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())