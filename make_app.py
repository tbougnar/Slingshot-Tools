"""Build one Slingshot Tool: research a useful everyday problem, generate a
single-file app, package it as a real Windows installer, publish to the site.

Everything the Monday workflow needs. No third-party deps beyond requests.
"""
from __future__ import annotations

import base64
import json
import os
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
LESSONS = ROOT / "data" / "lessons.txt"
BANNED = ROOT / "data" / "already_built.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
SITE_URL = os.environ.get("SITE_URL", "https://slingshot-tools.github.io")
ITCH_PAGE = os.environ.get("ITCH_PAGE", "slingshot-tools")

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
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
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
                CHAT_MODEL = "llama-3.1-8b-instant"
                body["model"] = CHAT_MODEL
                data = json.dumps(body).encode()
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            time.sleep(5)
    raise RuntimeError(f"groq failed: {last}")


def groq_json(system, user, **kw):
    raw = groq(system, user, **kw)
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        raise RuntimeError("no JSON in reply")
    return json.loads(m.group())


def load_built():
    if BANNED.exists():
        try:
            return json.loads(BANNED.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def pick_concept():
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
        "Choose ONE concept from this list that is genuinely useful in daily life and "
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


APP_SPEC = """Build a COMPLETE single-file HTML app. This is the entire deliverable.

HARD RULES
- Output ONE file: valid HTML5 with inline CSS and inline JavaScript. No build step, no
  external CDN, no external fonts, no network calls, no frameworks. It must work offline
  forever after first open.
- Everything is stored in localStorage so the user keeps their data.
- Theme follows Slingshot Tools: dark mode is dark red (#14100F background, #C1272D red,
  #F6EFEC text) and there is a working light mode toggle that switches instantly and is
  remembered. Use CSS variables and a data-theme attribute on <html>.
- Modern, clean, genuinely good looking: rounded cards, soft shadows, clear hierarchy,
  generous spacing, a header with the app name, and a footer. It must look like a paid app.
- Fully responsive on phone and desktop. Accessible: real labels, keyboard operable.
- Useful for real: actually solve the problem, with sensible defaults, validation and
  helpful empty states. No placeholder buttons, no "coming soon".
- Add a small "export my data" and "import my data" control (JSON) so nothing is trapped.
- No analytics, no tracking, no network.

CONTENT RULES
- Invent a short, friendly brand name for the app (not "App 1").
- Include one empty state that explains what to do first.

OUTPUT
Return JSON only, exactly this shape:
{"filename":"index.html","html":"<the entire file as one string, starting with <!DOCTYPE html>"}
The html value must be a single JSON string with all quotes escaped. Do not add commentary."""


def build_html(concept, lessons):
    d = groq_json(
        "You are a senior front-end engineer shipping a polished, genuinely useful "
        "single-file web app. You return JSON only.",
        APP_SPEC + f"\n\nTHE APP: {json.dumps(concept, indent=2)}\n"
        f"\nLESSONS FROM REAL USERS (apply them):\n{lessons or '(none yet)'}",
        max_tokens=8000, temperature=0.5,
    )
    html = d.get("html") or ""
    if "<!DOCTYPE" not in html or "</html>" not in html:
        raise RuntimeError("generated html looks incomplete")
    if len(html) < 1200:
        raise RuntimeError(f"generated html too small ({len(html)} bytes)")
    return html


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


def write_app(concept, html):
    out = APPS_DIR / concept["slug"]
    (out / "app").mkdir(parents=True, exist_ok=True)
    (out / "app" / "index.html").write_text(html, encoding="utf-8")
    (out / "concept.json").write_text(json.dumps(concept, indent=2), encoding="utf-8")
    return out


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
    r = subprocess.run(["makensis", "/V3", nsi.name],
                       cwd=app_dir, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists():
        log(f"installer build failed: {(r.stderr or r.stdout)[-400:]}")
        return None
    log(f"installer built: {out.name} ({out.stat().st_size//1024} KB)")
    return out


def publish(concept, app_dir, installer):
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
    entry = {
        "slug": concept["slug"],
        "title": concept["title"],
        "tag": concept["tag"],
        "blurb": concept["blurb"],
        "tags": concept["tags"],
        "url": f"{SITE_URL.rstrip('/')}/apps/{concept['slug']}/",
        "download": "",
        "badge": "New",
        "date": date.today().isoformat(),
    }
    if installer and installer.exists():
        rel = "apps/" + concept["slug"] + "/" + installer.name
        shutil.copy2(installer, SITE_APPS / concept["slug"] / installer.name)
        entry["download"] = f"{SITE_URL.rstrip('/')}/{rel}"
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
    concept = pick_concept()
    log(f"concept: {concept['title']} ({concept['slug']})")
    for attempt in range(1, 3):
        html = build_html(concept, lessons)
        issues = html_looks_fine(html)
        if issues:
            log(f"attempt {attempt} rejected: {issues}")
            continue
        log(f"attempt {attempt} ok ({len(html)} bytes)")
        app_dir = write_app(concept, html)
        installer = build_installer(app_dir, concept)
        entry = publish(concept, app_dir, installer)
        built = load_built()
        built.append({"slug": concept["slug"], "title": concept["title"],
                      "date": date.today().isoformat()})
        BANNED.parent.mkdir(parents=True, exist_ok=True)
        BANNED.write_text(json.dumps(built, indent=2), encoding="utf-8")
        log(f"DONE: {entry['title']} -> {entry['url']}")
        return 0
    log("both attempts failed the quality gate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
