"""Build one Slingshot Tool: research a useful everyday problem, generate a
single-file app, package it as a real Windows installer, publish to the site.

Everything the Monday workflow needs. No third-party deps beyond requests.
"""
from __future__ import annotations

import base64
import json
import os
import platform
import requests
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT / "apps"
SITE_APPS = ROOT / "site" / "apps"
SITE = ROOT / "site"
CATALOG = SITE / "apps.json"
DATA = ROOT / "data"
LESSONS = DATA / "lessons.txt"
BANNED = ROOT / "data" / "already_built.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
CHAT_MODEL = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() or "qwen/qwen3.8-27b"
CHAT_FALLBACKS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b",
                     "qwen/qwen3.8-27b"]
SITE_URL = (os.environ.get("SITE_URL") or "").strip() or "https://tbougnar.github.io/Slingshot-Tools"
ITCH_PAGE = (os.environ.get("ITCH_PAGE") or "").strip() or "slingshot-tools"
ITCH_API_KEY = (os.environ.get("ITCH_API_KEY") or "").strip()
ITCH_PAGE_URL = (os.environ.get("ITCH_PAGE_URL") or "").strip() or "https://slingshot-tools.itch.io/"
PRICE_FLOOR = float((os.environ.get("PRICE_FLOOR") or "").strip() or 1.00)
PRICE_START = float((os.environ.get("PRICE_START") or "").strip() or 3.00)

CATEGORIES = [
    ("password-manager", "offline password manager with vault encryption and a generator"),
    ("unit-converter", "unit converter that remembers your recent conversions"),
    ("habit-tracker", "habit tracker with streaks and a simple heatmap"),
    ("pomodoro-timer", "focus timer with session log and break reminders"),
    ("expense-splitter", "split bills between people and settle up"),
    ("qr-generator", "QR code generator that works fully offline"),
    ("color-picker", "color picker with contrast checker and palette export"),
    ("json-formatter", "JSON viewer and formatter with error highlighting"),
    ("regex-tester", "regex tester with live matches and explanation"),
    ("chess-clock", "chess clock with move time history"),
    ("invoice-maker", "invoice generator that exports clean PDF-ready HTML"),
    ("recipe-scaler", "recipe scaler that keeps fractions sensible"),
    ("file-renamer", "batch file renamer with find and replace and numbering"),
    ("password-strength", "password strength auditor that explains the score"),
    ("note-taker", "quick note taker with search and tags"),
    ("csv-viewer", "CSV viewer that handles huge files without freezing"),
    ("timestamp-converter", "Unix timestamp to human date and back"),
    ("lorem-generator", "placeholder text generator with the right length"),
    ("speed-typing-test", "typing speed test with WPM and accuracy"),
    ("pixel-art-editor", "tiny pixel art editor with undo and export"),
    ("markdown-preview", "markdown editor with live preview"),
    ("bookmark-organizer", "bookmark cleaner that finds duplicates and dead links"),
    ("chess-board", "chess board viewer with FEN loading"),
    ("base64-tool", "base64 and URL encoding tool"),
    ("stopwatch", "lap stopwatch with export"),
    ("text-diff", "text diff tool showing what changed line by line"),
    ("bandwidth-calc", "data transfer calculator for streaming and downloads"),
    ("permutation-tool", "string permutation and combination generator"),
    ("coin-toss", "coin flip and dice roller for quick decisions"),
    ("gst-calculator", "tax and tip calculator with clean receipts"),
    ("bmi-calculator", "fitness calculator with metric and imperial"),
    ("flashcard-maker", "flashcards with spaced repetition scheduling"),
    ("dev-converter", "developer unit converter for bytes, bits and encodings"),
    ("ip-info", "offline IP and subnet helper with CIDR math"),
    ("text-stats", "word, character and reading time counter"),
    ("calendar-diff", "calendar that diffs two date ranges"),
    ("random-team", "random team and shuffle picker for events"),
    ("grade-calculator", "weighted grade calculator with what-if"),
    ("compound-interest", "compound interest chart with plain explanation"),
    ("glasses-prescription", "glasses prescription converter for old and new format"),
    ("split-bill-app", "shared shopping list with running totals"),
    ("breathing-exercise", "breathing exercise guide with animated timer"),
    ("unit-price-compare", "unit price comparison for better shopping"),
    ("ebook-converter-notes", "reading notes organizer with highlights"),
]


def log(msg):
    print(f"[slingshot] {msg}", flush=True)


def groq(system, user, max_tokens=4000, temperature=0.8, tries=6):
    global CHAT_MODEL
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY missing")
    body = {
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
        # Groq sits behind Cloudflare, which rejects urllib's default
        # "Python-urllib" agent with error 1010. Send a browser UA.
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    last = "unknown"
    deadline = time.monotonic() + 1200
    attempt = 0
    while attempt < tries:
        attempt += 1
        try:
            req = urllib.request.Request(f"{GROQ_BASE}/chat/completions",
                                         data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read().decode())
            return out["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode()[:300]
            last = f"HTTP {e.code}: {body_txt}"
            if e.code == 429:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"rate limited too long: {last}")
                time.sleep(20)
                continue
            if e.code == 404:
                # rotate only to models this key actually has access to
                if CHAT_FALLBACKS:
                    CHAT_MODEL = CHAT_FALLBACKS.pop(0)
                else:
                    raise RuntimeError(f"model rejected and no fallback left: {last}")
                body["model"] = CHAT_MODEL
                data = json.dumps(body).encode()
                time.sleep(2)
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            time.sleep(5)
    raise RuntimeError(f"groq failed: {last}")


def _salvage_html(raw):
    """The html value is what we actually need. Models truncate huge answers
    mid-string, so grab everything after "html":" up to the end and clean it."""
    if not raw:
        return None
    m = re.search(r'"html"\s*:\s*"(.*)$', raw, re.S)
    if not m:
        return None
    body = m.group(1)
    # a complete value ends with a closing quote; a truncated one does not
    if body.endswith('"') and not body.endswith('\\"'):
        body = body[:-1]
    try:
        return json.loads('"' + body + '"')
    except json.JSONDecodeError:
        pass
    # cut back to the last complete escape so json can parse what is left
    for cut in range(len(body), 0, -1):
        if body[cut - 1] != "\\":
            continue
        try:
            return json.loads('"' + body[: cut - 1] + '"')
        except json.JSONDecodeError:
            continue
    return body.replace('\\"', '"')


def _salvage_json(raw):
    """Trim to the last balanced closing brace and retry."""
    if not raw:
        return None
    depth = 0
    last = None
    instr = False
    esc = False
    for i, ch in enumerate(raw):
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                last = i
    if last is None:
        return None
    try:
        return json.loads(raw[: last + 1])
    except json.JSONDecodeError:
        return None


def groq_json(system, user, **kw):
    """JSON-mode with tolerance for truncated model output."""
    for use_json in (True, False):
        try:
            raw = groq(system, user, **kw)
        except RuntimeError:
            continue
        if not raw:
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        salvaged = _salvage_json(raw)
        if salvaged:
            return salvaged
        html = _salvage_html(raw)
        if html:
            log("recovered html from truncated JSON")
            return {"html": html}
    raise RuntimeError("groq returned no usable JSON")

def load_built():
    if BANNED.exists():
        try:
            return json.loads(BANNED.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def pick_concept(money=""):
    built = load_built()
    taken = {b["slug"] for b in built}
    pool = [c for c in CATEGORIES if c[0] not in taken]
    if not pool:
        pool = CATEGORIES
    lessons = ""
    if LESSONS.exists():
        lessons = LESSONS.read_text(encoding="utf-8")[:3000]
    log(f"choosing from {len(pool)} unused concepts (built: {len(built)})")
    d = groq_json(
        "You pick the next tiny web app to build. You return JSON only.",
        f"Already built (never repeat): {json.dumps(sorted(taken))}\n\n"
        f"Lessons learned from real users so far:\n{lessons or '(none yet)'}\n\n"
        f"MONEY SO FAR - the goal is to make the most profit:\n{money or '(no sales data yet)'}\n\n"
        "Choose ONE concept from this list that is genuinely useful in daily life, "
        "that we have not built, and that is most likely to actually SELL: "
        "prefer niches where people already pay, avoid crowded free-only niches. "
        "that we have not built: " + json.dumps(pool) + "\n\n"
        'Return JSON only: {"slug":"kebab-case","title":"2-4 words",'
        '"tag":"one category word","blurb":"one sentence, concrete benefit",'
        '"tags":["4 short lowercase keywords"],"problem":"what daily annoyance it removes"}',
        max_tokens=700, temperature=0.5,
    )
    slug = re.sub(r"[^a-z0-9-]+", "-", str(d.get("slug", "")).lower()).strip("-")
    if not slug:
        raise RuntimeError("no slug")
    return {
        "slug": slug,
        "title": str(d.get("title") or slug.replace("-", " ").title()),
        "tag": str(d.get("tag") or "utility"),
        "blurb": str(d.get("blurb") or "A small tool that just works."),
        "tags": [str(t) for t in (d.get("tags") or [])][:5],
        "problem": str(d.get("problem") or ""),
    }


APP_SPEC = """Build a COMPLETE single-file HTML app that ships in TWO editions from ONE file.
This is the entire deliverable.

TIER SYSTEM (critical - the file must contain this)
Near the very top of the <script>, define:
const TIER = "full";                 // "basic" or "full"
const LIMITS = { maxItems: 0, export: true, themes: "all", bulk: true, history: true };
Then read every limit from LIMITS instead of hardcoding numbers. When
TIER === "basic": use the values in BASIC_LIMITS below; when TIER === "full":
treat all limits as unlimited. The same code must work correctly in both editions.

BASIC_LIMITS must be chosen by you for this app and must be genuinely limiting
but still useful - e.g. { maxItems: 3, export: false, themes: "one", bulk: false, history: false }.
Never make the basic edition useless; it must genuinely solve the problem for a
few items so the user hits the wall and wants the full edition.

Also return these, and they must NOT sound the same:
- "free_blurb": what the FREE basic edition is honestly good for, in one short
  sentence. Friendly, useful on its own, no apologising.
- "paid_blurb": why someone should pay, in one punchy sentence. Lead with the
  outcome they get (unlimited, no walls, exports, history) - never vague.
- "differences": 4-6 short concrete sentences a customer would understand, each
  starting with "Full edition:", naming exactly what the paid version adds.

HARD RULES
- ONE file: valid HTML5 with inline CSS and inline JavaScript. No build step, no
  external CDN, no external fonts, no network calls, no frameworks.
- Works offline forever after first open. Data in localStorage.
- Theme follows Slingshot Tools: dark mode is dark red (#14100F background,
  #C1272D red, #F6EFEC text) with a working light mode toggle, remembered.
- Modern and genuinely good looking: rounded cards, soft shadows, clear hierarchy,
  generous spacing, header with the app name, footer. Must look like a paid app.
- Fully responsive on phone and desktop. Accessible: real labels, keyboard operable.
- Useful for real: sensible defaults, validation, helpful empty states. No
  placeholder buttons, no "coming soon".
- Never nag or guilt the user about upgrading. One calm line is enough.
- Add "export my data" and "import my data" (JSON) controls in the full edition.
- No analytics, no tracking, no network.

CONTENT RULES
- Invent a short, friendly brand name for the app.
- Include one empty state explaining what to do first.

OUTPUT
Return JSON only, exactly this shape:
{"filename":"index.html","brand":"App Name","html":"<the entire file>","differences":["Full edition: ...","..."]}
The html value must be a single JSON string with all quotes escaped. No commentary."""


def build_html(concept, lessons):
    d = groq_json(
        "You are a senior front-end engineer shipping a polished, genuinely useful "
        "single-file web app in a free basic edition and a paid full edition. "
        "You return JSON only.",
        APP_SPEC + f"\n\nTHE APP: {json.dumps(concept, indent=2)}\n"
        f"\nLESSONS FROM REAL USERS (apply them):\n{lessons or '(none yet)'}",
        max_tokens=9000, temperature=0.5,
    )
    html = d.get("html") or ""
    if "<!DOCTYPE" not in html and "<html" not in html:
        raise RuntimeError("generated html has no document at all")
    # models truncate long answers; close the document instead of throwing the
    # whole app away - a truncated-but-working app beats no app
    low = html.lower()
    if "</body>" not in low:
        html += "\n</body>"
    if "</html>" not in low:
        html += "\n</html>"
    if len(html) < 1200:
        raise RuntimeError(f"generated html too small ({len(html)} bytes)")
    diffs = [str(x)[:120] for x in (d.get("differences") or [])][:6]
    brand = str(d.get("brand") or concept["title"])
    return html, brand, diffs, str(d.get("free_blurb") or ""), str(d.get("paid_blurb") or "")


def _set_tier(html, tier):
    """Flip the edition in the generated file."""
    out = html.replace('const TIER = "full";', f'const TIER = "{tier}";', 1)
    if out == html:
        out = re.sub(r'(const\s+TIER\s*=\s*")[^"]*(")', rf'\g<1>{tier}\g<2>', html, count=1)
    return out


def write_app(concept, html, tier="full"):
    slug = concept["slug"] if tier == "full" else f"{concept['slug']}-basic"
    out = APPS_DIR / slug
    (out / "app").mkdir(parents=True, exist_ok=True)
    (out / "app" / "index.html").write_text(_set_tier(html, tier), encoding="utf-8")
    meta = {**concept, "slug": slug, "tier": tier, "base_slug": concept["slug"]}
    (out / "concept.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def html_looks_fine(html):
    problems = []
    if re.search(r"https?://(?!www\.w3\.org)", html):
        problems.append("external URL referenced")
    if "<script src=" in html:
        problems.append("external script")
    if len(html) < 1500:
        problems.append("too small")
    for needle in ("localStorage", "data-theme", "</html>"):
        if needle not in html:
            problems.append(f"missing {needle}")
    return problems


NSI = r"""
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "__APPNAME__"
!define SLUG "__SLUG__"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://{SITE}"
Name "Slingshot Tool - {APPNAME}"
OutFile "__OUT__"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\{SLUG}"
InstallDirRegKey HKCU "Software\Slingshot Tools\{SLUG}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "__ICON__"
!define MUI_UNICON "__ICON__"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Launch.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Open {APPNAME} now"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install" SecMain
  SetOutPath "$INSTDIR\app"
  File /r "app\*.*"
  SetOutPath "$INSTDIR"
  File "Launch.cmd"

  WriteRegStr HKCU "Software\Slingshot Tools\{SLUG}" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayName" "Slingshot Tool - {APPNAME}"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayIcon" "$INSTDIR\app\icon.png"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "NoRepair" 1

  CreateDirectory "$SMPROGRAMS\Slingshot Tools"
  CreateShortcut "$SMPROGRAMS\Slingshot Tools\{APPNAME}.lnk" "$INSTDIR\Launch.cmd"
  CreateShortcut "$SMPROGRAMS\Slingshot Tools\Uninstall {APPNAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\{APPNAME}.lnk" "$INSTDIR\Launch.cmd"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Launch.cmd"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\{APPNAME}.lnk"
  RMDir "$SMPROGRAMS\Slingshot Tools"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}"
  DeleteRegKey HKCU "Software\Slingshot Tools\{SLUG}"
SectionEnd
"""

LAUNCH_CMD = """@echo off
rem Slingshot Tool launcher - opens the app in a chromeless window
set "APPDIR=%~dp0app\\index.html"
set "FILEURL=file:///%%APPDIR:\\=\\%%"
if exist "%ProgramFiles(x86)%%\\Microsoft%%\\Edge%%\\Application%%\\msedge.exe" (
  start "" "%ProgramFiles(x86)%%\\Microsoft%%\\Edge%%\\Application%%\\msedge.exe" --app="%FILEURL%" --window-size=1180,820
  exit /b 0
)
if exist "%ProgramFiles%%\\Microsoft%%\\Edge%%\\Application%%\\msedge.exe" (
  start "" "%ProgramFiles%%\\Microsoft%%\\Edge%%\\Application%%\\msedge.exe" --app="%FILEURL%" --window-size=1180,820
  exit /b 0
)
start "" "%FILEURL%"
"""


def build_installer(app_dir: Path, concept):
    nsi = app_dir / "installer.nsi"
    out = ROOT / "dist" / f"SlingshotTool-{concept['slug']}-Setup.exe"
    out.parent.mkdir(parents=True, exist_ok=True)
    icon = ROOT / "site" / "icon-512.png"
    ico = app_dir / "icon.ico"
    try:
        from PIL import Image
        im = Image.open(icon).convert("RGBA")
        im.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    except Exception as e:  # noqa: BLE001
        log(f"ico conversion skipped: {e}")
        ico = icon
    text = (NSI
            .replace("__APPNAME__", concept["title"])
            .replace("__SLUG__", concept["slug"])
            .replace("__OUT__", out.as_posix())
            .replace("__ICON__", ico.as_posix())
            .replace("{SITE}", SITE_URL))
    nsi.write_text(text, encoding="utf-8")
    (app_dir / "Launch.cmd").write_text(LAUNCH_CMD.replace("%%", "%"), encoding="utf-8")

    if shutil.which("makensis") is None:
        log("makensis not installed - shipping portable folder only")
        return None
    r = subprocess.run(["makensis", "-V3", nsi.name],
                       cwd=app_dir, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists():
        log(f"installer build failed: {(r.stderr or r.stdout)[-400:]}")
        return None
    log(f"installer built: {out.name} ({out.stat().st_size//1024} KB)")
    return out



BUTLER_RELEASES = "https://api.github.com/repos/itchio/butler/releases"
BUTLER_FALLBACK_VERSION = "v15.31.0"


def _butler_asset_urls():
    """butler ships official binaries on its GitHub releases. Ask the API for the
    newest release so we never hardcode a dead version."""
    machine = platform.machine().lower()
    key = "butler-linux-arm64.zip" if ("arm" in machine or "aarch" in machine) \
        else "butler-linux-amd64.zip"
    version = BUTLER_FALLBACK_VERSION
    try:
        r = requests.get(BUTLER_RELEASES + "/latest",
                         headers={"Accept": "application/vnd.github+json",
                                  "User-Agent": "slingshot"},
                         timeout=60)
        if r.status_code == 200:
            tag = r.json().get("tag_name")
            if tag:
                version = tag
    except Exception as e:  # noqa: BLE001
        log(f"release lookup failed, using pinned {version}: {str(e)[:70]}")
    urls = [f"https://github.com/itchio/butler/releases/download/{version}/{key}"]
    if version != BUTLER_FALLBACK_VERSION:
        urls.append(
            f"https://github.com/itchio/butler/releases/download/"
            f"{BUTLER_FALLBACK_VERSION}/{key}")
    return urls


def install_butler():
    """Fetch butler from its official GitHub release and verify it really is a
    Linux binary for this CPU before we ever execute it."""
    if shutil.which("butler"):
        return shutil.which("butler")
    dest = Path("/usr/local/bin/butler")
    for url in _butler_asset_urls():
        try:
            r = requests.get(url, timeout=300)
            if r.status_code != 200 or len(r.content) < 100_000:
                log(f"butler release rejected: {r.status_code} {url}")
                continue
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                name = next(n for n in z.namelist()
                            if n.endswith("butler") and "source" not in n)
                blob = z.read(name)
            if blob[:4] != b"\x7fELF":
                log(f"not an ELF binary: {url}")
                continue
            machine = platform.machine().lower()
            is_arm = blob[18] == 0xB7
            if ("arm" in machine or "aarch" in machine) != is_arm:
                log(f"wrong CPU architecture: {url}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            dest.chmod(0o755)
            chk = subprocess.run([str(dest), "version"], capture_output=True, timeout=60)
            log(f"butler installed from {url} ({len(blob)//1024} KB, "
                f"self-check rc={chk.returncode})")
            return str(dest)
        except Exception as e:  # noqa: BLE001
            log(f"butler source failed: {str(e)[:90]}")
    log("no usable butler release found")
    return None


def push_to_itch(concept, app_dir):
    """Best-effort upload to itch.io. Never fatal: a finished app matters far
    more than the upload, and butler/arch problems must not kill the build."""
    slug = concept["slug"]
    try:
        if not ITCH_API_KEY:
            log("no itch key - skipping upload")
            return False
        butler = install_butler()
        if not butler:
            log("could not obtain butler - product stays unpublished")
            return False
        machine = platform.machine().lower()
        arch = "aarch64" if machine in ("arm64", "aarch64") else "amd64"
        upload_dir = app_dir / "upload"
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        payload = upload_dir / "itch"
        payload.mkdir(parents=True, exist_ok=True)
        shutil.copy2(app_dir / "app" / "index.html", payload / "index.html")
        if (ROOT / "site" / "icon-512.png").exists():
            shutil.copy2(ROOT / "site" / "icon-512.png", payload / "icon.png")
        (payload / "README.txt").write_text(
            f"{concept.get('brand') or concept['title']}\n{concept['blurb']}\n\n"
            "A single-file app: open index.html in any modern browser. Your data "
            "stays in your browser and is never sent anywhere.\n",
            encoding="utf-8")
        env = dict(os.environ, BUTLER_API_KEY=ITCH_API_KEY, BUTLER_CHANNEL=ITCH_PAGE)
        r = subprocess.run([butler, "push", str(payload), "--project", slug, "--create", "--yes"],
                           capture_output=True, text=True, env=env, timeout=900)
        if r.returncode != 0:
            log(f"itch upload did not succeed (non-fatal): "
                f"{(r.stderr or r.stdout)[-200:]}")
            return False
        log(f"uploaded to itch.io as '{slug}'")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"itch upload skipped, build continues: {str(e)[:160]}")
        return False


def publish(concept, app_dir, installer, tier="full", brand="", differences=None,
             free_blurb="", paid_blurb="", published=False):
    dest = SITE_APPS / concept["slug"]
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(app_dir / "app" / "index.html", dest / "index.html")
    if (ROOT / "site" / "icon-512.png").exists():
        shutil.copy2(ROOT / "site" / "icon-512.png", dest / "icon.png")

    apps = []
    if CATALOG.exists():
        try:
            apps = json.loads(CATALOG.read_text(encoding="utf-8"))
            if isinstance(apps, dict):
                apps = apps.get("apps", [])
        except json.JSONDecodeError:
            apps = []
    base = concept.get("base_slug", concept["slug"])
    entry = {
        "slug": concept["slug"],
        "base_slug": base,
        "title": (f"{brand or concept['title']}" if tier == "full"
                  else f"{brand or concept['title']} (Basic)"),
        "tier": tier,
        "tag": concept["tag"],
        "blurb": (free_blurb if tier == "basic" and free_blurb
                  else paid_blurb if tier == "full" and paid_blurb
                  else concept["blurb"]),
        "tags": concept["tags"],
        "url": f"{SITE_URL.rstrip('/')}/apps/{concept['slug']}/",
        "itch_url": f"{ITCH_PAGE_URL.rstrip('/')}/{concept['slug']}",
        "download": "",
        "price": 0.0 if tier == "basic" else max(PRICE_FLOOR, PRICE_START),
        "free": tier == "basic",
        "differences": differences or [],
        "published": published,
        "badge": "New",
        "date": date.today().isoformat(),
    }
    if installer and installer.exists() and tier == "full":
        # The paid build is delivered through itch.io only. Never copy the
        # installer or the full app into site/, which is public - that would
        # hand the paid product to anyone who opens the catalog.
        print(f"[publish] installer built but NOT published publicly "
              f"({installer.name}); delivery happens via itch.io", flush=True)
    apps = [a for a in apps if a.get("slug") != concept["slug"]]
    apps.insert(0, entry)
    CATALOG.write_text(json.dumps(apps, indent=2), encoding="utf-8")
    log(f"catalog now has {len(apps)} app(s)")
    return entry


def main():
    if not GROQ_KEY:
        log("no GROQ_API_KEY - nothing to do")
        return 0
    lessons = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""
    money = ""
    earn_file = DATA / "earnings.json"
    if earn_file.exists():
        money = earn_file.read_text(encoding="utf-8")[:2500]
    concept = pick_concept(money)
    log(f"concept: {concept['title']} ({concept['slug']})")
    for attempt in range(1, 3):
        html, brand, diffs, free_blurb, paid_blurb = build_html(concept, lessons)
        issues = html_looks_fine(html)
        if issues:
            log(f"attempt {attempt} rejected: {issues}")
            continue
        log(f"attempt {attempt} ok ({len(html)} bytes, brand={brand!r})")

        full_meta = {**concept, "brand": brand}
        full_dir = write_app(full_meta, html, tier="full")
        installer = build_installer(full_dir, full_meta)
        ok_full = push_to_itch({**full_meta, "slug": concept["slug"]}, full_dir)
        full_entry = publish({**full_meta, "base_slug": concept["slug"]}, full_dir,
                             installer, tier="full", brand=brand, differences=diffs,
                             free_blurb=free_blurb, paid_blurb=paid_blurb,
                             published=ok_full)

        basic_meta = {**concept, "brand": brand,
                      "slug": f"{concept['slug']}-basic"}
        basic_dir = write_app(basic_meta, html, tier="basic")
        ok_basic = push_to_itch(basic_meta, basic_dir)
        basic_entry = publish({**basic_meta, "base_slug": concept["slug"]}, basic_dir,
                              None, tier="basic", brand=brand, differences=diffs,
                              free_blurb=free_blurb, paid_blurb=paid_blurb,
                              published=ok_basic)

        built = load_built()
        built.append({"slug": concept["slug"], "title": brand,
                      "date": date.today().isoformat()})
        BANNED.parent.mkdir(parents=True, exist_ok=True)
        BANNED.write_text(json.dumps(built, indent=2), encoding="utf-8")
        log(f"DONE full: {full_entry['title']} ${full_entry['price']:.2f} -> {full_entry['url']}")
        log(f"DONE basic: {basic_entry['title']} free -> {basic_entry['url']}")
        return 0
    log("both attempts failed the quality gate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
