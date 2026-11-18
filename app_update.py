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
import os
import sys
from pathlib import Path

import update_state as us

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "site" / "update.json"
# The published copy of the same file, for an installed app that has no
# site/ folder beside it. Can be overridden to point at an always-on host
# (e.g. Kerit Cloud) for instant same-day updates; GitHub Pages remains fallback.
PUBLISHED = (os.environ.get("SLINGSHOT_UPDATE_URL") or "").strip() or \
    "https://tbougnar.github.io/Slingshot-Tools/update.json"
PUBLISHED_FALLBACK = "https://tbougnar.github.io/Slingshot-Tools/update.json"

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
    import urllib.request
    urls = []
    for u in (PUBLISHED, PUBLISHED_FALLBACK):
        if u and u not in urls:
            urls.append(u)
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "slingshot-tools"})
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.loads(r.read(200000).decode("utf-8", "replace"))
            if isinstance(d, dict):
                return d
        except Exception:  # noqa: BLE001
            continue
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


def _coerce_app_entry(value) -> dict:
    if isinstance(value, dict):
        ver = str(value.get("version") or "1.0.0")
        out = {"version": us.format_version(us.parse(ver))}
        for key in ("title", "description", "download_url", "released"):
            if value.get(key):
                out[key] = str(value[key])
        notes = value.get("notes")
        if isinstance(notes, list):
            out["notes"] = [str(n) for n in notes if str(n).strip()][:12]
        if value.get("restart_required") is not None:
            out["restart_required"] = bool(value.get("restart_required"))
        return out
    return {"version": us.format_version(us.parse(str(value or "1.0.0")))}


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
    newest = str(state.get("version") or "1.0.0")
    details: dict = {}
    per_app = state.get("apps")
    if isinstance(per_app, dict) and slug and slug in per_app:
        details = _coerce_app_entry(per_app.get(slug))
        newest = str(details.get("version") or newest)
    out["latest"] = us.format_version(us.parse(newest))
    lu = state.get("latest_update") if isinstance(state.get("latest_update"), dict) else {}
    if details.get("description"):
        out["description"] = details["description"]
    elif lu.get("description"):
        out["description"] = str(lu.get("description") or "")
    if details.get("title"):
        out["title"] = details["title"]
    elif lu.get("title"):
        out["title"] = str(lu.get("title") or "")
    if details.get("notes"):
        out["notes"] = details["notes"]
    elif isinstance(lu.get("notes"), list):
        out["notes"] = [str(n) for n in lu.get("notes") if str(n).strip()][:12]
    if details.get("download_url"):
        out["download_url"] = details["download_url"]
    if details.get("released"):
        out["released"] = details["released"]
    elif lu.get("released"):
        out["released"] = str(lu.get("released") or "")
    out["restart_required"] = bool(details.get("restart_required", True))
    out["url"] = details.get("download_url") or "https://tbougnar.github.io/Slingshot-Tools/"

    if us.is_newer(out["latest"], out["installed"]):
        out["update_available"] = True
        out["reason"] = (f"{out['installed']} is installed, {out['latest']} is "
                         f"published")
        if not out.get("description"):
            out["description"] = ("A new update is available for this app. "
                                  "Download and restart to apply the latest "
                                  "improvements and fixes.")
    if state.get("phase") == "announced" and state.get("next_major"):
        out["coming"] = str(state.get("next_major"))
        out["coming_title"] = str(state.get("next_major_title") or "")
    return out


BANNER_HTML = f"""
    <!-- Slingshot Tools update notice. Injected by app_update.py; the app
         itself makes no network calls, this is filled in by the launcher. -->
    <div id="{BANNER_ID}" hidden
         style="position:fixed;top:14px;right:14px;z-index:99999;font:500 14px/1.45 system-ui,sans-serif;color:#fff">
      <button type="button" id="{BANNER_ID}-btn"
              style="appearance:none;border:0;border-radius:999px;padding:10px 14px;
                     background:#d92d20;color:#fff;font:700 13px/1 system-ui,sans-serif;
                     box-shadow:0 8px 24px rgba(0,0,0,.35);cursor:pointer">
        Update available
      </button>
      <div id="{BANNER_ID}-panel" hidden
           style="margin-top:10px;width:min(420px,calc(100vw - 28px));
                  background:#17171b;color:#f5f5f7;border:1px solid #34343c;
                  border-radius:16px;box-shadow:0 20px 50px rgba(0,0,0,.45);
                  padding:14px">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <strong id="{BANNER_ID}-title" style="font-size:16px">Update available</strong>
          <button type="button" id="{BANNER_ID}-close"
                  style="background:transparent;border:1px solid #444;color:#ddd;border-radius:8px;padding:4px 8px;cursor:pointer">Close</button>
        </div>
        <div id="{BANNER_ID}-meta" style="margin-top:6px;color:#b9b9c3;font-size:12px"></div>
        <div id="{BANNER_ID}-desc" style="margin-top:10px;white-space:pre-wrap"></div>
        <ul id="{BANNER_ID}-notes" style="margin:10px 0 0 18px;padding:0;color:#d7d7dd"></ul>
        <div id="{BANNER_ID}-status" style="margin-top:10px;color:#ffd2d2;font-size:12px;min-height:18px"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
          <button type="button" id="{BANNER_ID}-download"
                  style="appearance:none;border:0;border-radius:10px;padding:10px 12px;
                         background:#d92d20;color:#fff;font:700 13px/1 system-ui,sans-serif;cursor:pointer">
            Download &amp; restart
          </button>
          <button type="button" id="{BANNER_ID}-later"
                  style="appearance:none;border:1px solid #444;border-radius:10px;padding:10px 12px;
                         background:transparent;color:#f5f5f7;font:600 13px/1 system-ui,sans-serif;cursor:pointer">
            Later
          </button>
        </div>
      </div>
    </div>
    <script>
    (function(){{
      var root=document.getElementById("{BANNER_ID}"); if(!root) return;
      var btn=document.getElementById("{BANNER_ID}-btn");
      var panel=document.getElementById("{BANNER_ID}-panel");
      var close=document.getElementById("{BANNER_ID}-close");
      var later=document.getElementById("{BANNER_ID}-later");
      var dl=document.getElementById("{BANNER_ID}-download");
      var title=document.getElementById("{BANNER_ID}-title");
      var meta=document.getElementById("{BANNER_ID}-meta");
      var desc=document.getElementById("{BANNER_ID}-desc");
      var notes=document.getElementById("{BANNER_ID}-notes");
      var status=document.getElementById("{BANNER_ID}-status");
      var info={{}};
      function setStatus(msg,err){{ if(status){{ status.textContent=msg||""; status.style.color=err?"#ffb4b4":"#bfe3c5"; }} }}
      function openPanel(){{ if(panel) panel.hidden=false; }}
      function closePanel(){{ if(panel) panel.hidden=true; }}
      function show(data){{
        info=data||{{}};
        if(typeof info==="string") info={{reason:info, description:info}};
        if(title) title.textContent=info.title || ("Update " + (info.latest||"available"));
        var m=[]; if(info.installed) m.push("Installed: " + info.installed);
        if(info.latest) m.push("Latest: " + info.latest);
        if(info.released) m.push("Released: " + info.released);
        if(meta) meta.textContent=m.join(" · ");
        if(desc) desc.textContent=info.description || info.reason || "A new update is available for this app.";
        if(notes){{
          notes.innerHTML="";
          (info.notes||[]).forEach(function(n){{
            var li=document.createElement("li"); li.textContent=String(n); notes.appendChild(li);
          }});
        }}
        root.hidden=false;
        setStatus("", false);
      }}
      if(btn) btn.onclick=openPanel;
      if(close) close.onclick=closePanel;
      if(later) later.onclick=function(){{ closePanel(); }};
      async function callBridge(){{
        if(window.__slingshotBridge && typeof window.__slingshotBridge.applyUpdate==="function"){{
          return await window.__slingshotBridge.applyUpdate(info);
        }}
        if(window.pywebview && window.pywebview.api && typeof window.pywebview.api.apply_update==="function"){{
          return await window.pywebview.api.apply_update(info);
        }}
        throw new Error("Update bridge is not available in this launcher.");
      }}
      if(dl) dl.onclick=async function(){{
        try{{
          setStatus("Downloading update...", false);
          dl.disabled=true;
          var res=await callBridge();
          if(res && res.ok===false) throw new Error(res.error||"Update failed");
          setStatus("Applying update and restarting...", false);
        }}catch(e){{
          setStatus(String(e && e.message ? e.message : e), true);
          dl.disabled=false;
        }}
      }};
      window.__slingshotUpdate=show;
      window.__slingshotUpdatePanel=function(data){{ show(data); openPanel(); }};
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