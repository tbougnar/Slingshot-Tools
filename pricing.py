"""Slingshot Tools pricing engine.

Learns from real sales: no demand -> cut the price, strong demand -> raise it.
Hard floor and ceiling, a minimum sample size before reacting, same price for
everyone, every move logged with its reason and reversible.

Run by the Friday workflow; writes data/prices.json which the site reads.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PRICES = DATA / "prices.json"
LOG = DATA / "price_log.json"
CATALOG = ROOT / "site" / "apps.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")

FLOOR = float(os.environ.get("PRICE_FLOOR", "1.00"))
CEILING = float(os.environ.get("PRICE_CEILING", "9.00"))
START_PRICE = float(os.environ.get("PRICE_START", "3.00"))
MIN_SALES_BEFORE_MOVE = int(os.environ.get("PRICE_MIN_SAMPLES", "5"))
STEP = float(os.environ.get("PRICE_STEP", "0.50"))
ITCH_KEY = os.environ.get("ITCH_API_KEY", "")
ITCH_USER = os.environ.get("ITCH_USER", "slingshot-tools")


def log(m):
    print(f"[pricing] {m}", flush=True)


def load(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def charm(price: float) -> float:
    """$2.49 reads better than $2.50 and is a real pricing technique."""
    p = round(price, 2)
    return math_floor_to(p - 0.01) if p >= 1 else p


def math_floor_to(p):
    import math
    return math.floor(p * 100) / 100.0


def clamp(p):
    return max(FLOOR, min(CEILING, round(p, 2)))


def decide(sales_count: int, views: int, current: float) -> tuple[float, str]:
    """Pure decision function so it can be unit-tested without any network."""
    if sales_count < MIN_SALES_BEFORE_MOVE:
        return current, (f"held at ${current:.2f} - only {sales_count} sale(s), "
                         f"need {MIN_SALES_BEFORE_MOVE} before reacting")
    rate = sales_count / views if views else 0.0
    if views >= 20 and rate < 0.02:
        return clamp(current - STEP), (f"cut ${current:.2f} -> ${clamp(current - STEP):.2f} - "
                                       f"{views} views but {sales_count} sales "
                                       f"({rate:.1%} conversion)")
    if rate >= 0.12 and sales_count >= MIN_SALES_BEFORE_MOVE * 2:
        return clamp(current + STEP), (f"raised ${current:.2f} -> "
                                       f"${clamp(current + STEP):.2f} - "
                                       f"{rate:.1%} conversion on {views} views")
    return current, f"held at ${current:.2f} - conversion {rate:.1%} is healthy"


def sales_from_itch(slug):
    """Real numbers if the itch API key is present, else an honest None."""
    if not (ITCH_KEY and slug):
        return None
    try:
        req = urllib.request.Request(
            f"https://api.itch.io/profile/{ITCH_USER}/games",
            headers={"Authorization": f"Bearer {ITCH_KEY}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            games = json.loads(r.read().decode())
        for g in games:
            if g.get("id") == slug or g.get("slug") == slug:
                stats = g.get("extra") or {}
                return {"sales": int(g.get("num_sales") or 0),
                        "views": int(stats.get("views") or 0),
                        "rating": g.get("rating") or None}
    except Exception as e:  # noqa: BLE001
        log(f"itch stats unavailable ({str(e)[:90]}) - using what we have stored")
    return None


def groq(system, user, max_tokens=900, temperature=0.4):
    if not GROQ_KEY:
        return ""
    body = json.dumps({
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode()
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    deadline = time.monotonic() + 600
    attempt = 0
    while attempt < 4 and time.monotonic() < deadline:
        attempt += 1
        try:
            req = urllib.request.Request(f"{GROQ_BASE}/chat/completions",
                                         data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            m = re.search(r"\{[\s\S]*\}", raw or "")
            return json.loads(m.group()) if m else {}
        except Exception as e:  # noqa: BLE001
            log(f"model unavailable: {str(e)[:90]}")
            time.sleep(8)
    return {}


def pick_free_app(apps, prices, sales):
    """The AI decides which app is the free one: usually the newest, so the
    freebie keeps the storefront fresh and always gives a reason to return."""
    if not apps:
        return None, {}
    if len(apps) == 1:
        return apps[0]["slug"], {"reason": "only one app - it is the free sample"}

    scored = []
    for a in apps:
        s = sales.get(a["slug"], {})
        sales_n = s.get("sales", 0)
        age = a.get("date", "")
        fresh = 1.0 if age >= (date.today().isoformat()) else 0.0
        paid_now = prices.get(a["slug"], {}).get("price", 0) or 0
        # prefer a fresh app that is not the current best seller
        score = fresh * 3 + (1.0 if sales_n <= 1 else 0.0) - sales_n * 0.1
        scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    d = groq(
        "You decide which Slingshot Tool should be the free download this week. "
        "You are blunt about product value. Return JSON only.",
        f"Apps: {json.dumps([{k: a.get(k) for k in ('slug','title','blurb','date')} for a in apps])}\n"
        f"Sales so far: {json.dumps(sales)}\n"
        f"Currently free: {json.dumps(prices.get('__free__', {}))}\n\n"
        f"Pick one to be FREE this week (a free app should pull people in, not give "
        f"away your best seller). Return JSON only: "
        '{"slug":"...","why":"one sentence","marketing_hook":"one punchy sentence"}',
        max_tokens=400, temperature=0.5,
    )
    slug = (d.get("slug") if isinstance(d, dict) else None) or best["slug"]
    if slug not in {a["slug"] for a in apps}:
        slug = best["slug"]
    return slug, {"why": (d.get("why") if isinstance(d, dict) else None)
                  or "newest app with no sales yet",
                  "marketing_hook": (d.get("marketing_hook") if isinstance(d, dict) else None) or "",
                  "score": round(scored[0][0], 2)}


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    apps = load(CATALOG, [])
    prices = load(PRICES, {})
    history = load(LOG, [])
    sales = {a["slug"]: sales_from_itch(a["slug"]) or {} for a in apps} if apps else {}

    for a in apps:
        slug = a["slug"]
        entry = prices.setdefault(slug, {})
        if "price" not in entry:
            entry["price"] = START_PRICE
            entry["history"] = [{"price": START_PRICE, "date": date.today().isoformat(),
                                 "reason": "launch price"}]
        s = sales.get(slug) or {}
        entry["sales"] = s.get("sales", entry.get("sales", 0))
        entry["views"] = s.get("views", entry.get("views", 0))
        if a.get("itch_url"):
            entry["itch_url"] = a["itch_url"]

    moved = []
    for a in apps:
        slug = a["slug"]
        entry = prices[slug]
        cur = float(entry["price"])
        s = sales.get(slug) or {}
        new, why = decide(int(entry.get("sales") or 0), int(entry.get("views") or 0), cur)
        new = charm(clamp(new))
        if abs(new - cur) >= 0.01:
            entry["price"] = new
            entry.setdefault("history", []).append(
                {"price": new, "date": date.today().isoformat(), "reason": why})
            history.append({"slug": slug, "old": cur, "new": new,
                            "date": date.today().isoformat(), "reason": why})
            moved.append((slug, cur, new, why))
            log(f"MOVED {slug}: ${cur:.2f} -> ${new:.2f} ({why})")
        else:
            log(f"held {slug}: {why}")

    free_slug, free_reason = pick_free_app(apps, prices, sales)
    if free_slug:
        prices["__free__"] = {"slug": free_slug, **free_reason,
                              "date": date.today().isoformat()}
        log(f"FREE this week: {free_slug} - {free_reason.get('why')}")

    for a in apps:
        a["price"] = 0 if a["slug"] == free_slug else prices.get(a["slug"], {}).get("price", START_PRICE)
        a["free"] = a["slug"] == free_slug
        a["itch_url"] = a.get("itch_url") or os.environ.get("ITCH_PAGE_URL",
                                                            "https://slingshot-tools.itch.io/")

    PRICES.write_text(json.dumps(prices, indent=2), encoding="utf-8")
    LOG.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")
    if apps:
        CATALOG.write_text(json.dumps(apps, indent=2), encoding="utf-8")

    log(f"wrote {len(apps)} app(s); {len(moved)} price move(s); free={free_slug}")
    for a in apps:
        log(f"   {a['slug']}: {'FREE' if a.get('free') else '$%.2f' % a['price']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())