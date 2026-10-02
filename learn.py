"""Friday coach: look at the catalog and any real usage signals we can see,
then write concrete lessons that Monday's build will read and apply."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CATALOG = SITE / "apps.json"
LESSONS = ROOT / "data" / "lessons.txt"
STATS = ROOT / "data" / "stats.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "qwen/qwen3.8-27b")
ITCH_PAGE = os.environ.get("ITCH_PAGE", "slingshot-tools")


def log(m):
    print(f"[coach] {m}", flush=True)


def groq_json(system, user, max_tokens=1200, temperature=0.4):
    body = json.dumps({
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    deadline = time.monotonic() + 600
    attempt = 0
    last = "unknown"
    while attempt < 5 and time.monotonic() < deadline:
        attempt += 1
        try:
            req = urllib.request.Request(f"{GROQ_BASE}/chat/completions",
                                         data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read().decode())
            raw = out["choices"][0]["message"]["content"]
            m = re.search(r"\{[\s\S]*\}", raw or "")
            return json.loads(m.group()) if m else {}
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            time.sleep(10)
    log(f"coach model unavailable: {last}")
    return {}


def itch_signals():
    """Public page hit counts if the itch.io API key is configured; otherwise
    an honest 'no data yet' so we never invent numbers."""
    key = os.environ.get("ITCH_API_KEY", "")
    if not key:
        return None
    try:
        req = urllib.request.Request(f"https://{ITCH_PAGE}.itch.io/embed-stats",
                                     headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        log(f"itch stats unavailable: {str(e)[:120]}")
        return None


def main():
    apps = []
    if CATALOG.exists():
        try:
            apps = json.loads(CATALOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            apps = []
    signals = itch_signals()
    prev = {}
    if STATS.exists():
        try:
            prev = json.loads(STATS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    now = {a["slug"]: a.get("date", "") for a in apps}
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(now, indent=2), encoding="utf-8")

    week = date.today() - timedelta(days=7)
    fresh = [a for a in apps if a.get("date", "") >= week.isoformat()]

    previous_lessons = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""

    system = ("You are the product coach for Slingshot Tools, a one-person studio that "
              "ships one small useful web app every Monday and improves it on Friday. "
              "You are specific, never flattering, never inventing data. Return JSON only.")
    user = (
        f"Catalog right now ({len(apps)} apps):\n"
        f"{json.dumps([{k: a.get(k) for k in ('slug','title','tag','blurb','date')} for a in apps], indent=1)}\n\n"
        f"Shipped in the last 7 days: {[a['title'] for a in fresh] or 'none'}\n\n"
        f"Real usage signals available: {json.dumps(signals) if signals else 'NONE YET - no installs/downloads data is wired up, so reason from the catalog only and do not invent numbers.'}\n\n"
        f"Lessons carried over from last week:\n{previous_lessons or '(none)'}\n\n"
        "Write this week's lessons for the NEXT app. Focus on: picking a problem people "
        "genuinely feel daily, one clear job per app, a real empty state, and making the "
        "app feel premium in CSS. Drop any lesson that no longer applies.\n\n"
        'Return JSON only: {"keep":["short durable lessons"],"add":["new lessons for next app"],'
        '"drop":["lessons to retire"],"next_concepts":["6 kebab-case tool ideas for daily life"]}'
    )
    d = groq_json(system, user)
    if not d:
        log("no coach output; lessons unchanged")
        return 0

    keep = [str(x) for x in (d.get("keep") or [])][:6]
    add = [str(x) for x in (d.get("add") or [])][:6]
    drop = {str(x) for x in (d.get("drop") or [])}
    kept = [l for l in previous_lessons.splitlines()
            if l.strip() and not any(k[:20] in l for k in drop)]
    lines = kept + add
    text = ("# Slingshot Tools lessons (updated %s)\n\n" % date.today()
            + "\n".join(f"- {l}" for l in lines[:14]) + "\n")
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    LESSONS.write_text(text, encoding="utf-8")
    log(f"wrote {len(lines[:14])} lessons")

    ideas = ROOT / "data" / "next_concepts.json"
    ideas.write_text(json.dumps(d.get("next_concepts") or [], indent=2), encoding="utf-8")
    log(f"saved {len(d.get('next_concepts') or [])} future concepts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
