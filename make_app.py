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

# Windows consoles default to a legacy code page, so any non-ASCII character in
# model output used to raise UnicodeEncodeError and kill the run. Output that
# cannot be encoded is replaced rather than fatal.
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _safe(text) -> str:
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return "<unprintable>"


import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import buglog
import qa_loop
import build_exe

ROOT = Path(__file__).resolve().parent
SITE_APPS = ROOT / "site" / "apps"
SITE = ROOT / "site"
# Only the basic edition is ever written under site/, which is the folder
# GitHub Pages publishes. Paid editions go to paid/, outside that tree.
APPS_DIR = SITE_APPS
PAID_DIR = ROOT / "paid"
CATALOG = SITE / "apps.json"
DATA = ROOT / "data"
LESSONS = DATA / "lessons.txt"
PATTERNS = ROOT / "PATTERNS.md"
BANNED = ROOT / "data" / "already_built.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
# One builder, two debuggers. gpt-oss-120b is the strongest coder available, so
# it writes the app; the other two are reserved for debugging and are only used
# here if the builder's own model is unreachable.
CHAT_MODEL = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() or "openai/gpt-oss-120b"
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
CHAT_FALLBACKS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b",
                     "qwen/qwen3.8-27b"]
SITE_URL = (os.environ.get("SITE_URL") or "").strip() or "https://tbougnar.github.io/Slingshot-Tools"
SITE_BASE = SITE_URL.rstrip("/")
# itch.io is the store. A product is only shown for sale once its itch_url is
# in the catalog, which only a person sets, so there is no payment code here.
LICENSE_SECRET = (os.environ.get("LICENSE_SECRET") or "").strip()
PRICE_FLOOR = float((os.environ.get("PRICE_FLOOR") or "").strip() or 1.00)
PRICE_START = float((os.environ.get("PRICE_START") or "").strip() or 3.00)
# Hard bounds the AI may never leave: $1.00 to $10.00.
PRICE_CEILING = float((os.environ.get("PRICE_CEILING") or "").strip() or 10.00)

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
    try:
        print(_safe(msg), flush=True)
    except Exception:  # noqa: BLE001
        pass

def groq(system, user, max_tokens=4000, temperature=0.8, tries=3):
    """Call whichever model provider is configured.

    Any provider is fine here, so the provider is chosen by whichever
    credentials exist rather than being hard-wired. Every model is tried in
    turn because a rate limit on one of them says nothing about the others.
    """
    global CHAT_MODEL
    if not GROQ_KEY and not os.environ.get("GEMINI_API_KEY") \
            and not os.environ.get("CEREBRAS_API_KEY") \
            and not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("no model provider is configured")
    import providers
    order = [CHAT_MODEL] + [x for x in MODELS if x != CHAT_MODEL]
    try:
        order = providers.models("builder") + order
    except Exception:  # noqa: BLE001
        pass
    last = ""
    for model in order:
        for attempt in range(2):
            try:
                out = providers.chat(model, system, user, temperature,
                                   max_tokens, role="builder")
                if out:
                    return out
            except Exception as e:  # noqa: BLE001
                last = str(e)[:200]
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"every model failed: {last}")

def _salvage_html(raw):
    """Pull the document out of whatever the model actually returned.

    Models wrap a long reply in prose, in markdown fences, in a JSON string, or
    in some combination of those, and often truncate it. Every one of those
    shapes used to return None, which is why a perfectly good app was thrown
    away with "no usable JSON".
    """
    if not raw:
        return None
    text = raw

    # 1. a JSON string value, which may be cut off mid-document
    m = re.search(r'"html"\s*:\s*"(.*)$', text, re.S)
    if m:
        text = m.group(1)
        text = text.replace('\\"', '"').replace("\\n", "\n")
        if text.endswith('"'):
            text = text[:-1]

    # 2. drop markdown fences if they survived
    text = re.sub(r"```(?:html|HTML)?", "", text)
    text = text.replace("```", "")

    # 3. take from the first document tag to the last closing one
    low = text.lower()
    starts = [low.find("<!doctype html"), low.find("<html")]
    starts = [i for i in starts if i != -1]
    if not starts:
        return None
    i = min(starts)
    end_tag = low.rfind("</html>")
    body = text[i:end_tag + 7] if end_tag != -1 and end_tag > i else text[i:]

    body = body.strip()
    if len(body) < 500:
        return None
    # a truncated document is still usable once closed
    if "</html>" not in body.lower():
        if "</body>" in body.lower():
            body = body[:body.lower().rindex("</body>")] + "</body></html>"
        else:
            body += "</html>"
    return body

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
    """Parse a JSON reply, saying what actually went wrong when it cannot.

    This used to loop twice over a flag it never used, so it repeated the same
    call and swallowed the exception. Every failure therefore reported the same
    unhelpful message no matter the real cause.
    """
    last = ""
    for attempt in range(2):
        try:
            raw = groq(system, user, **kw)
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:300]}"
            log(f"model call failed ({last})")
            time.sleep(2)
            continue
        if raw is None:
            last = "the model returned nothing at all"
            log(last)
            continue
        got = _as_json(raw)
        if got:
            return got
        last = "the reply was not parseable JSON"
        capture(raw)
        log(f"{last}; first 200 chars: {raw[:200]!r}")
    raise RuntimeError(f"no usable JSON - {last}")


def _as_json(raw):
    if not raw:
        return None
    text = raw.strip()
    # a reasoning model may wrap its answer in prose or a fenced block
    if text.startswith("```"):
        text = text.split("```")[1] if text.count("```") > 1 else text
        text = text[4:] if text.lower().startswith("json") else text
    for candidate in (text, text[text.find("{"):] if "{" in text else ""):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
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
    return None


def groq_json_any(system, user, models=None, **kw):
    """Try each model in turn for a small structured reply.

    Pinning one model made the whole build fail when that model would not answer
    a short JSON question, which is a far easier task than writing an app.
    """
    import providers
    order = []
    try:
        order = providers.models("debug")
    except Exception:  # noqa: BLE001
        pass
    for m in MODELS:
        if m not in order:
            order.append(m)
    if models:
        order = [x for x in models if x] + order
    last = ""
    for model in order:
        try:
            raw = providers.chat(model, system, user,
                                 kw.pop("temperature", 0.4) if not kw else 0.4,
                                 kw.get("max_tokens", 3000))
        except TypeError:
            raw = None
        except Exception as e:  # noqa: BLE001
            last = str(e)[:160]
            raw = None
        if not raw:
            continue
        got = _as_json(raw)
        if got:
            log(f"concept chosen by {model}")
            return got
    raise RuntimeError(f"no model returned usable JSON ({last})")


def load_built():
    """Everything already built, so nothing is generated twice.

    `data/already_built.json` is the record the pipeline appends to, but a
    reset or a hand edit can drop entries. The public catalog is the other
    half of the truth, so both are merged: a tool that is on the site counts
    as built even if the record lost it.
    """
    built = []
    seen = set()
    if BANNED.exists():
        try:
            built = json.loads(BANNED.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            built = []
    for b in built:
        slug = b.get("slug") if isinstance(b, dict) else None
        if slug:
            seen.add(slug)

    if CATALOG.exists():
        try:
            entries = json.loads(CATALOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
        if isinstance(entries, list):
            for a in entries:
                if not isinstance(a, dict):
                    continue
                base = strip_tier_suffix_slug(a.get("base_slug") or a.get("slug"))
                if base and base not in seen:
                    seen.add(base)
                    built.append({"slug": base, "source": "catalog"})
    return built


def pick_concept(money=""):
    """Choose the next app locally.

    This used to ask a model to pick from the unused concepts, which spent the
    first call of every run on something the code already knew. That call was
    where runs died on a rate limit, so it is gone: the pool is in CATEGORIES
    and the choice needs no intelligence.

    Community votes are honoured first: whatever won the last Discord ballot
    is built next, so the roadmap follows what people actually asked for.
    """
    built = load_built()
    taken = {b["slug"] for b in built}
    pool = [c for c in CATEGORIES if c[0] not in taken]
    if not pool:
        pool = list(CATEGORIES)

    def parts(c):
        slug, desc = c[0], c[1]
        title = desc.split(" with ")[0].split(" for ")[0].split(" that ")[0]
        return {"slug": slug,
                "title": title[:1].upper() + title[1:],
                "tag": slug.split("-")[0],
                "blurb": desc,
                "tags": [w.strip(",.") for w in desc.split()[:4]]}

    voted = _voted_next()
    if voted:
        match = next((c for c in pool if c[0] == voted), None)
        if match:
            concept = parts(match)
            log(f"community vote chose {concept['slug']} "
                f"[won the last Discord ballot]")
            return concept
        log(f"ballot winner {voted!r} is not an unused concept; ignoring vote")

    chosen = max(pool, key=lambda c: (len(c[1]), c[0]))
    concept = parts(chosen)
    log(f"choosing from {len(pool)} unused concepts (built: {len(built)})")
    log(f"concept: {concept['title']} ({concept['slug']}) "
        f"[chosen locally, no model call]")
    return concept


def _voted_next() -> str:
    """The most recent community ballot winner, if it is still buildable."""
    try:
        import discord_data
        winners = discord_data.recent_winners(1)
    except Exception:  # noqa: BLE001
        return ""
    return winners[0] if winners else ""


_CARD_FILE = ROOT / "PATTERN_CARD.txt"
PATTERN_CARD = (_CARD_FILE.read_text(encoding="utf-8")
                if _CARD_FILE.exists() else "")


def patterns() -> str:
    """The short card. The full curriculum is in PATTERNS.md for humans and for
    the debugger team; sending all of it to the builder every month would cost
    more tokens than the app itself."""
    return PATTERN_CARD


# Every raw model reply is written here. Guessing what a model returned has
# wasted more runs than any other mistake in this project, so it is always
# captured on disk.
LAST_REPLY = ROOT / "data" / "last_reply.txt"


def capture(text) -> str:
    """Write the reply verbatim so a failure can be read instead of guessed."""
    try:
        LAST_REPLY.parent.mkdir(parents=True, exist_ok=True)
        LAST_REPLY.write_text(text if isinstance(text, str) else repr(text),
                              encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return text if isinstance(text, str) else repr(text)


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
- The full edition has no limits and shows no upgrade prompts at all.
- Add "export my data" and "import my data" (JSON) controls in the full edition.
- No analytics, no tracking, no network.

CONTENT RULES
- Invent a short, friendly brand name for the app.
- Include one empty state explaining what to do first.

OUTPUT
Return JSON only, exactly this shape:
{"filename":"index.html","brand":"App Name","html":"<the entire file>","differences":["Full edition: ...","..."]}
The html value must be a single JSON string with all quotes escaped. No commentary."""


def build_html_raw(concept, lessons, attempt=1):
    """Ask for the file itself, not JSON containing a file.

    Wrapping a 30 KB document in JSON is what kept failing: the reply arrives
    as prose, or fenced, or truncated mid-object. Asking for the HTML directly
    removes the parse step entirely, which is the whole failure mode.
    """
    system = (
        "You write one complete, self-contained HTML file. You reply with the "
        "HTML and nothing else. No commentary before it, no explanation after "
        "it, no markdown fences."
    )
    user = (
        "Build this app.\n\n"
        + APP_SPEC
        + f"\n\nTHE APP: {json.dumps(concept, indent=2)}\n"
        + "\n\nPATTERNS YOU MUST FOLLOW:\n" + patterns()
        + f"\n\nKNOWN BUGS TO AVOID:\n{lessons or '(none yet)'}"
        + "\n\nReply with the HTML file only, starting with <!DOCTYPE html> "
          "and ending with </html>."
    )
    if attempt > 1:
        user += ("\n\nKeep it COMPACT and make sure it is complete: short CSS, "
                 "no comments, and it must end with </html>.")
    last = ""
    # The free allowance is per minute and it does refill, so waiting is the
    # difference between a failed run and a slow one. The local meter is empty
    # at the start of a run, so the wait has to be driven by the error itself.
    for attempt in range(8):
        for model in [CHAT_MODEL] + [m for m in MODELS if m != CHAT_MODEL]:
            try:
                raw = groq(system, user, max_tokens=16000, temperature=0.35)
            except Exception as e:  # noqa: BLE001
                last = str(e)[:200]
                raw = None
            if not raw:
                continue
            doc = _salvage_html(raw)
            if doc:
                if raw.strip().startswith("<!DOCTYPE") or raw.strip().startswith("<html"):
                    return doc, "raw", []
                return doc, "trimmed", []
            last = "the reply contained no html"
        if "429" in last or "Rate limit" in last or "still processing" in last:
            wait = min(90, 30 + attempt * 15)
            log(f"model allowance is full ({last[:60]}); waiting {wait}s "
                f"for it to refill, attempt {attempt + 1}/8")
            time.sleep(wait)
            continue
        break
    raise RuntimeError(f"no usable html after waiting - {last}")


def build_html(concept, lessons, attempt=1):
    d = groq_json(
        "You are a senior front-end engineer shipping a polished, genuinely useful "
        "single-file web app in a free basic edition and a paid full edition. "
        "You return JSON only.",
        APP_SPEC
        + f"\n\nTHE APP: {json.dumps(concept, indent=2)}\n"
        + ("\n\nIMPORTANT: keep the HTML compact - short CSS, short JS, no comments. "
           "It MUST be complete and end with </html>." if attempt > 1 else "")
        + f"\nLESSONS FROM REAL USERS (apply them):\n{lessons or '(none yet)'}"
        + f"\n\nPATTERNS YOU MUST FOLLOW:\n{patterns()}",
        max_tokens=14000, temperature=0.35,
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
    """Write one edition.

    Only the BASIC edition is ever placed under site/, which is the public
    folder GitHub Pages publishes. The FULL edition goes to paid/, outside the
    published tree, and is released solely to a buyer who has paid.
    """
    slug = concept["slug"] if tier == "full" else f"{concept['slug']}-basic"
    out = (APPS_DIR / slug) if tier == "basic" else (PAID_DIR / slug)
    if tier == "full" and out.exists():
        shutil.rmtree(out)
    (out / "app").mkdir(parents=True, exist_ok=True)
    (out / "app" / "index.html").write_text(_set_tier(html, tier), encoding="utf-8")
    meta = {**concept, "slug": slug, "tier": tier, "base_slug": concept["slug"]}
    (out / "concept.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def html_looks_fine(html):
    problems = []
    notes = []
    if re.search(r"https?://(?!www\.w3\.org)", html):
        problems.append("external URL referenced")
    if "<script src=" in html:
        problems.append("external script")
    if len(html) < 1500:
        problems.append("too small")
    for needle in ("</html>",):
        if needle not in html:
            problems.append(f"missing {needle}")
    # A theme attribute is a preference, not correctness. It used to reject
    # whole finished apps, so it is only noted now.
    if "data-theme" not in html:
        notes.append("no data-theme attribute: dark/light switching will be "
                     "default only, which is acceptable")
    if "localStorage" not in html and "indexedDB" not in html:
        problems.append("missing localStorage (the app would not save anything)")
    return problems


NSI = r"""
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "__APPNAME__"
!define BRAND "Slingshot Tools"
!define SLUG "__SLUG__"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://{SITE}"
Name "__APPNAME__"
OutFile "__OUT__"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\__SLUG__"
InstallDirRegKey HKCU "Software\Slingshot Tools\__SLUG__" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "__ICON__"
!define MUI_UNICON "__ICON__"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start __APPNAME__"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install" SecMain
  SetOutPath "$INSTDIR\app"
  File /r "app\*.*"
  SetOutPath "$INSTDIR"
  File "launcher.py"
  File "app\app.json"
  File "Start App.cmd"

  WriteRegStr HKCU "Software\Slingshot Tools\__SLUG__" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "DisplayName" "__APPNAME__"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "DisplayIcon" "__ICON__"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\__APPNAME__.lnk" "$INSTDIR\Start App.cmd" "" "__ICON__" 0
  CreateShortcut "$SMPROGRAMS\Uninstall __APPNAME__.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\__APPNAME__.lnk" "$INSTDIR\Start App.cmd" "" "__ICON__" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\__APPNAME__.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\__SLUG__"
  DeleteRegKey HKCU "Software\Slingshot Tools\__SLUG__"
SectionEnd
"""


NATIVE_LAUNCHER = '''import os, sys
from pathlib import Path
import webview

HERE = Path(__file__).resolve().parent
APP = HERE / "app" / "index.html"

def main():
    title = "Slingshot Tool"
    meta = HERE / "app" / "app.json"
    if meta.exists():
        try:
            import json
            title = json.loads(meta.read_text(encoding="utf-8-sig")).get("title", title)
        except Exception:
            pass
    if not APP.exists():
        return 1
    try:
        webview.create_window(title=title, width=1180, height=820, min_size=(760, 560))
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(APP.as_uri())
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

LAUNCH_CMD = """@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1 && (start "" pythonw launcher.py & exit /b 0)
where python  >nul 2>&1 && (start "" python  launcher.py & exit /b 0)
rem Slingshot Tool launcher - opens the app in a real native window
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
    # the installer ships these; without them makensis aborts on a missing File
    (app_dir / "Start App.cmd").write_text(LAUNCH_CMD.replace("%%", "%"), encoding="utf-8")
    (app_dir / "app" / "app.json").write_text(
        json.dumps({"title": concept["title"]}, ensure_ascii=False),
        encoding="utf-8")
    launcher_src = ROOT / "native_launcher.py"
    if launcher_src.exists():
        shutil.copy2(launcher_src, app_dir / "launcher.py")
    else:
        (app_dir / "launcher.py").write_text(NATIVE_LAUNCHER, encoding="utf-8")
    icon_png = ROOT / "site" / "icon-512.png"
    if icon_png.exists():
        shutil.copy2(icon_png, app_dir / "app" / "icon.png")

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


def already_listed(base_slug: str) -> bool:
    """Is this product already for sale on itch.io?

    A rebuild must not silently hide a product that is on sale. If the catalog
    already carries an itch_url for this family, the paid tier stays published.
    """
    try:
        entries = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any((e.get("base_slug") or e.get("slug")) == base_slug
               and (e.get("itch_url") or "").startswith("https://")
               for e in entries if isinstance(e, dict))


def stage_paid(app_dir: Path, slug: str, installer: Path | None = None) -> bool:
    """Confirm the paid build is built and kept out of the public site.

    There is no private store to upload to any more: itch.io hosts the paid file
    and a person uploads it. So this only checks that the build exists and that
    nothing paid has leaked into site/, then says where the installer is.

    The paid tier stays unpublished until ``publish_paid.py`` is run by hand,
    because only that knows whether the itch.io page is actually live.
    """
    if not app_dir.exists():
        log(f"no paid build was produced for {slug}")
        return False

    if SITE_APPS / slug in [p for p in SITE_APPS.glob("*") if p.is_dir()]:
        log(f"REFUSING: a paid edition would be written into site/ for {slug}")
        return False

    where = ""
    if installer and Path(installer).exists():
        size = Path(installer).stat().st_size / 1024 / 1024
        where = f" ({Path(installer).name}, {size:.1f} MB)"
    log(f"paid edition built for {slug}{where}")
    log(f"  upload it to itch.io, then: "
        f"python set_itch_url.py {slug} <url> && python publish_paid.py {slug}")
    return True



_JUNK_BLURBS = {"x", "n/a", "na", "none", "todo", "-", "...", "tbd", "null"}

_TAG_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
    "app", "apps", "tool", "tools", "utility", "free", "offline", "online",
    "small", "tiny", "simple", "mini", "software", "program", "web",
    "basic", "full", "edition", "version", "premium", "pro",
}


def clean_blurb(*candidates, title="", tag=""):
    """Return the first blurb that reads like a sentence.

    The generator sometimes emits a placeholder instead of a description
    (we have seen a bare "x"), and an empty card looks broken on the site,
    so fall back to a deterministic sentence built from the app's own title.
    """
    for cand in candidates:
        if not isinstance(cand, str):
            continue
        text = " ".join(cand.split()).strip().strip('"').strip()
        if len(text) < 12 or text.lower() in _JUNK_BLURBS:
            continue
        # a single repeated character is never a real description
        if len(set(text.replace(" ", ""))) <= 2:
            continue
        return text[:180]
    name = strip_tier_suffix(title) or "This tool"
    topic = (tag or "everyday tasks").strip()
    return f"A small, focused {topic} tool. {name} does one job properly, runs offline, and keeps your data on your device."


def strip_tier_suffix(title):
    """Drop the "(Basic)" suffix the catalog appends to free editions."""
    return re.sub(r"\s*\(basic\)\s*$", "", str(title or ""), flags=re.I).strip()


def strip_tier_suffix_slug(slug):
    """Return the product family slug, without a trailing tier marker."""
    s = re.sub(r"-(basic|full)$", "", str(slug or "").strip().lower())
    return s.strip("-")


def clean_tags(*candidates, tag="", title="", limit=4):
    """Return usable tags, always led by the product's own category."""
    def norm(raw):
        if not isinstance(raw, str):
            return ""
        t = " ".join(raw.split()).strip().lower()
        t = t.strip("().,;:!?-—_")          # drop "(basic)" style edges
        t = re.sub(r"\(.*?\)", " ", t).strip()   # and any bracketed aside
        t = " ".join(t.split()).strip(".")
        if not t or t in _JUNK_BLURBS or len(t) > 24:
            return ""
        if t in _TAG_STOPWORDS:
            return ""
        return t

    # seeds first, so the category leads and the tags stay specific
    lead = norm(tag)
    ordered = [lead] if lead else []
    for seed in str(title or "").lower().split():
        t = norm(seed)
        if t and t not in ordered:
            ordered.append(t)
    # then whatever the generator suggested
    for source in candidates:
        if isinstance(source, str):
            source = re.split(r"[,\n]", source)
        if not isinstance(source, (list, tuple, set)):
            continue
        for raw in source:
            t = norm(raw)
            if t and t not in ordered:
                ordered.append(t)
    return ordered[:limit] or ["utility"]


def publish(concept, app_dir, installer, tier="full", brand="", differences=None,
             free_blurb="", paid_blurb="", published=False, price_override=None):
    dest = SITE_APPS / concept["slug"]
    if tier == "full":
        # the paid build is never copied into the public site; it is kept in
        # paid/ and handed to the Worker, which releases it after payment
        print(f"[publish] paid tier kept private; no files copied into site/",
              flush=True)
    else:
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
    # Both tiers must land in the same product family, otherwise the site
    # renders two separate cards instead of one free + one full option. Strip
    # the tier suffix so an inherited base_slug can never split the family.
    base = strip_tier_suffix_slug(concept.get("base_slug") or concept["slug"])
    if not base:
        base = concept["slug"]
    entry = {
        "slug": concept["slug"],
        "base_slug": base,
        "title": (f"{brand or concept['title']}" if tier == "full"
                  else f"{brand or concept['title']} (Basic)"),
        "tier": tier,
        "tag": concept["tag"],
        "blurb": clean_blurb(free_blurb if tier == "basic" else paid_blurb,
                             concept.get("blurb", ""),
                             title=brand or concept["title"], tag=concept["tag"]),
        "tags": clean_tags(concept.get("tags", []), tag=concept["tag"],
                           title=brand or concept["title"]),
        "url": (f"{SITE_URL.rstrip('/')}/apps/{concept['slug']}/" if tier == "basic"
                else f"{SITE_URL.rstrip('/')}/apps/{concept['slug']}-basic/"),
        "download": "",
        "price": (0.0 if tier == "basic" else
                  max(PRICE_FLOOR, min(PRICE_CEILING,
                      PRICE_START if price_override is None else price_override))),
        "free": tier == "basic",
        "differences": differences or [],
        "published": published,
        "badge": "New",
        "date": date.today().isoformat(),
    }
    if installer and installer.exists() and tier == "full":
        # site/ is public, so the paid app and installer are never copied into
        # it. They live in paid/ (kept out of the published folder) and are
        # delivered only after PayPal confirms payment.
        print(f"[publish] paid build kept out of the public site "
              f"({installer.name}); delivered after payment", flush=True)
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
    lessons = (lessons + "\n\nPAST BUGS (id + symptom only):\n"
               + buglog.digest(14))[:1800]
    money = ""
    earn_file = DATA / "earnings.json"
    if earn_file.exists():
        money = earn_file.read_text(encoding="utf-8")[:2500]
    concept = pick_concept(money)
    log(f"concept: {concept['title']} ({concept['slug']})")
    for attempt in range(1, 3):
        html, brand, diffs, free_blurb, paid_blurb = build_html(
            concept, lessons, attempt=attempt)
        issues = html_looks_fine(html)
        for note in getattr(html_looks_fine, "notes", []):
            log(f"note: {note}")
        if issues:
            log(f"attempt {attempt} rejected: {issues}")
            continue
        log(f"attempt {attempt} ok ({len(html)} bytes, brand={brand!r})")

        # Interactive QA: click every control in a real browser. A majority of
        # models must agree something is broken before anything is repaired,
        # and nothing is published unless the app comes back clean.
        probe = PAID_DIR / f"{concept['slug']}.qa.html"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(html, encoding="utf-8")
        qa_ok, qa_history = qa_loop.repair_until_clean(probe, log=log)
        if qa_ok:
            repaired = probe.read_text(encoding="utf-8", errors="replace")
            if len(repaired) > 1500 and "<html" in repaired:
                if repaired != html:
                    log(f"QA changed the app ({len(html)} -> {len(repaired)} bytes)")
                    html = repaired
                else:
                    log("QA passed with no changes needed")
            else:
                log("QA returned something unusable - keeping the original")
        else:
            log(f"attempt {attempt} REJECTED by QA: {qa_history}")
            probe.unlink(missing_ok=True)
            continue
        probe.unlink(missing_ok=True)

        full_meta = {**concept, "brand": brand}
        full_dir = write_app(full_meta, html, tier="full")
        installer = build_installer(full_dir, full_meta)
        ok_full = stage_paid(full_dir, concept["slug"], installer)
        # hidden until publish_paid.py has confirmed the itch.io page, so a buy
        # button can never appear before there is anything to buy
        full_entry = publish({**full_meta, "base_slug": concept["slug"]}, full_dir,
                             installer, tier="full", brand=brand, differences=diffs,
                             free_blurb=free_blurb, paid_blurb=paid_blurb,
                             published=ok_full and already_listed(concept["slug"]))

        basic_meta = {**concept, "brand": brand,
                      "slug": f"{concept['slug']}-basic"}
        basic_dir = write_app(basic_meta, html, tier="basic")
        ok_basic = True
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
