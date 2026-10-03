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
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PRICES = DATA / "prices.json"
LOG = DATA / "price_log.json"
CATALOG = ROOT / "site" / "apps.json"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
CHAT_MODEL = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() or "qwen/qwen3.8-27b"

FLOOR = float((os.environ.get("PRICE_FLOOR") or "").strip() or "1.00")
CEILING = float((os.environ.get("PRICE_CEILING") or "").strip() or "10.00")
START_PRICE = float((os.environ.get("PRICE_START") or "").strip() or "3.00")
MIN_SALES_BEFORE_MOVE = int((os.environ.get("PRICE_MIN_SAMPLES") or "").strip() or "5")
STEP = float((os.environ.get("PRICE_STEP") or "").strip() or "0.50")
ITCH_KEY = (os.environ.get("ITCH_API_KEY") or "").strip() or ""
ITCH_USER = (os.environ.get("ITCH_USER") or "").strip() or "slingshot-tools"


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


# Fee model: itch.io takes its cut and PayPal takes a percentage plus a fixed
# fee. Money below FLOOR is not revenue, it is a loss - so the floor is real.
ITCH_CUT = float(os.environ.get("ITCH_CUT", "0.0"))        # 0 unless they opt in
PAYPAL_PCT = float(os.environ.get("PAYPAL_PCT", "0.049"))
PAYPAL_FIXED = float(os.environ.get("PAYPAL_FIXED", "0.30"))


def profit_per_sale(price):
    """What actually lands in the account after processing."""
    return round(price - (price * PAYPAL_PCT + PAYPAL_FIXED) - price * ITCH_CUT, 4)


def break_even_price():
    """Lowest price where one sale still pays for itself."""
    for p10 in [x / 100 for x in range(5, 3000)]:
        if profit_per_sale(p10) > 0:
            return round(p10, 2)
    return FLOOR


def summarise_earnings(apps, prices):
    """Real money: revenue, net profit, and which product earns most."""
    rows = []
    for a in apps:
        e = prices.get(a["slug"], {}) or {}
        sales = int(e.get("sales") or 0)
        price = 0.0 if e.get("tier") == "basic" else float(e.get("price") or 0)
        net_each = profit_per_sale(price) if price else 0.0
        revenue = round(sales * price, 2)
        net = round(sales * net_each, 2)
        rows.append({"slug": a["slug"], "title": a.get("title", a["slug"]),
                     "tier": e.get("tier", "full"), "sales": sales,
                     "views": int(e.get("views") or 0), "price": price,
                     "revenue": revenue, "net": net,
                     "per_sale": net_each})
    total_rev = round(sum(r["revenue"] for r in rows), 2)
    total_net = round(sum(r["net"] for r in rows), 2)
    return rows, total_rev, total_net


def profit_directives(apps, prices, rows, total_net):
    """The coach's job: make the most money. Concrete, fee-aware decisions."""
    tips = []
    be = break_even_price()
    if be > FLOOR:
        tips.append(f"A sale at ${FLOOR:.2f} LOSES money after fees "
                    f"(keep ${be:.2f}+ to actually profit).")

    paid = [r for r in rows if r["price"] > 0]
    if not paid:
        tips.append("No paid product yet - the priority is getting the first "
                    "full edition listed, then the free basic edition as the funnel.")
        return tips

    zero = [r for r in paid if r["sales"] == 0]
    if zero:
        tips.append(f"{len(zero)} paid product(s) have zero sales: "
                    f"{', '.join(r['slug'] for r in zero[:4])}. Either cut the "
                    f"price to the break-even floor (${be:.2f}), change the pitch, "
                    f"or stop building in that niche and build what sells.")

    star = max(paid, key=lambda r: (r["net"], r["sales"]))
    if star["sales"] >= 3:
        tips.append(f"'{star['slug']}' is the proven earner (${star['net']:.2f} "
                    f"net). Raise its price and build the next app in the same "
                    f"niche - buyers of one are buyers of the other.")

    best_viewed = sorted(paid, key=lambda r: -r["views"])[:3]
    for r in best_viewed:
        if r["views"] >= 10 and r["sales"] == 0:
            tips.append(f"'{r['slug']}' got {r['views']} views and 0 sales - it is "
                        f"the price or the page, not the app. Try a bigger price "
                        f"drop first, then a sharper title.")

    if total_net > 0:
        tips.append(f"Net so far: ${total_net:.2f}. The cheapest way to raise it "
                    f"is a modest price rise on anything already selling - it "
                    f"costs nothing and keeps the same buyers.")
    else:
        tips.append("Nothing has netted positive yet. Do not build more apps: fix "
                    "price and the itch.io page for what exists first.")
    return tips


def groq(system, user, max_tokens=900, temperature=0.4):
    if not GROQ_KEY:
        return ""
    body = json.dumps({
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": temperature,
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


def assign_tiers(apps, prices):
    """Every month ships a pair: a BASIC app that is always free but limited,
    and the FULL version that is paid. The free one is never on a timer."""
    basic = [a for a in apps if a.get("tier") == "basic"]
    full = [a for a in apps if a.get("tier") in (None, "full")]
    log(f"tiers: {len(basic)} basic (free, limited), {len(full)} full (paid)")
    return basic, full


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    apps = load(CATALOG, [])
    prices = load(PRICES, {})
    history = load(LOG, [])
    sales = {a["slug"]: sales_from_itch(a["slug"]) or {} for a in apps} if apps else {}

    for a in apps:
        entry = prices.setdefault(a["slug"], {})
        entry.setdefault("price", START_PRICE)
        entry.setdefault("tier", a.get("tier") or "full")
        s = sales.get(a["slug"]) or {}
        entry["sales"] = s.get("sales", entry.get("sales", 0))
        entry["views"] = s.get("views", entry.get("views", 0))
        if a.get("itch_url"):
            entry["itch_url"] = a["itch_url"]

    basic, full = assign_tiers(apps, prices)

    moved = []
    for a in apps:
        slug = a["slug"]
        entry = prices[slug]
        if entry.get("tier") == "basic":
            entry["price"] = 0.0
            continue
        cur = float(entry["price"])
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

    for a in apps:
        entry = prices.get(a["slug"], {})
        a["tier"] = entry.get("tier", "full")
        a["free"] = a["tier"] == "basic"
        a["price"] = 0 if a["free"] else entry.get("price", START_PRICE)
        a["itch_url"] = a.get("itch_url") or os.environ.get(
            "ITCH_PAGE_URL", "https://slingshot-tools.itch.io/")

    PRICES.write_text(json.dumps(prices, indent=2), encoding="utf-8")
    LOG.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")
    if apps:
        CATALOG.write_text(json.dumps(apps, indent=2), encoding="utf-8")

    rows, total_rev, total_net = summarise_earnings(apps, prices)
    tips = profit_directives(apps, prices, rows, total_net)
    earnings = {"date": date.today().isoformat(), "revenue": total_rev,
                "net_profit": total_net, "break_even": break_even_price(),
                "products": rows, "directives": tips}
    (DATA / "earnings.json").write_text(json.dumps(earnings, indent=2), encoding="utf-8")
    log(f"EARNINGS revenue=${total_rev:.2f} net=${total_net:.2f} "
        f"break_even=${break_even_price():.2f}")
    for tip in tips:
        log("  PROFIT: " + tip)

    log(f"wrote {len(apps)} app(s); {len(moved)} price move(s)")
    for a in apps:
        tag = "BASIC free" if a.get("free") else "FULL $%.2f" % a["price"]
        log(f"   {a['slug']}: {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())