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
from datetime import date
from pathlib import Path

import set_itch_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PRICES = DATA / "prices.json"
LOG = DATA / "price_log.json"
CATALOG = ROOT / "site" / "apps.json"

# The model backend (OpenRouter first, Groq fallback) lives in providers.py.
# This file used to carry its own Groq URL, key and model, so a provider change
# had to be repeated here or the price advisor silently stopped working.

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


def _atomic(path: Path, text: str) -> None:
    """Write a tracked file via a temp file, so a crash cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    """Real numbers if the itch API key is present, else an honest None.

    This used to call /profile/{user}/games, which does not exist, and then
    match on id/slug although itch identifies a project by its url. The result
    was an exception every time, so sales and views stayed zero and the price
    engine never had a number to react to. itch_publish.games() is the working
    path and already reads the right shape.
    """
    if not (ITCH_KEY and slug):
        return None
    try:
        import itch_publish as ip
        want = slug.lower().replace("_", "-")
        for g in ip.games():
            url = (g.get("url") or "").rstrip("/").lower()
            title = (g.get("title") or "").strip().lower()
            if url.endswith(f"/{want}") or title == want.replace("-", " "):
                stats = g.get("extra") or {}
                return {"sales": int(g.get("num_sales") or 0),
                        "views": int(stats.get("views") or 0),
                        "rating": g.get("rating") or None}
    except Exception as e:  # noqa: BLE001
        log(f"itch stats unavailable ({str(e)[:90]}) - using what we have stored")
    return None


# Fee model: itch.io is the merchant, so its cut is the only one to model.
# Buyers pay itch.io and it pays us, so PayPal's fee applies to the payout
# rather than the sale. Roughly: itch.io default cut, plus a little for the
# transfer, plus a little for card processing on the payout.
ITCH_CUT = float(os.environ.get("ITCH_CUT") or 0.10)
PAYOUT_PCT = float(os.environ.get("PAYOUT_PCT") or 0.02)
PAYOUT_FIXED = float(os.environ.get("PAYOUT_FIXED") or 0.30)


def profit_per_sale(price):
    """What actually lands in the account after itch.io's cut and the payout."""
    fees = (price * ITCH_CUT) + (price * PAYOUT_PCT) + PAYOUT_FIXED
    return round(price - fees, 4)


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
    """Structured price advice from the live backend. {} means "no advice".

    providers.chat walks the free-model chain and handles a per-day cap, so the
    retry loop that slept for eight seconds here is gone.
    """
    try:
        import providers
        if not providers.configured():
            return {}
        raw = providers.chat(providers.best_model("chat"), system, user,
                             temperature, max_tokens, role="debug")
    except Exception as e:  # noqa: BLE001
        log(f"model unavailable: {str(e)[:90]}")
        return {}
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except (json.JSONDecodeError, ValueError):
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
        # The price the catalogue already carries is the price of record. The
        # engine's own state file is untracked, so on a fresh runner it does
        # not exist, and the old code defaulted every product to the starting
        # price. That reset the whole shop to $3.00 every Friday and silently
        # reverted any price that had been set by hand, and the engine could
        # never learn from a run because it started from nothing every time.
        # The catalogue is tracked, so it is what the price is read from.
        entry.setdefault("price", a.get("price", START_PRICE))
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
        # decide() returns the current price to mean "hold", so charm() must not be
        # applied to it: charm subtracts a cent unconditionally, which turned
        # every hold into a real one-cent drop and slid the price down a cent
        # per run for ever. Clamp after charm, never before, or charm(clamp(x))
        # can land below the hard floor and the product could never be listed.
        if round(new - cur, 2) == 0.0:
            # A hold is still a price, and it still has to be a legal one. The
            # clamp was applied only to a move, so a stored price of zero or
            # of ninety-nine was written back unchanged, published, and then
            # refused by publish_paid.py, which cannot list a product outside
            # the rule. A product that is held can never move, because decide
            # holds it for want of sales, so it would be stuck for ever.
            entry["price"] = clamp(cur)
            continue
        new = clamp(charm(new))
        if abs(round(new - cur, 2)) >= 0.01:
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
        # The catalogue decides the tier. The engine's state file is a note
        # about the price, and letting a stale note override the catalogue
        # meant a price engine could move a product between the free and the
        # paid tier, from a file nobody reviews.
        a["tier"] = a.get("tier") or entry.get("tier") or "full"
        a["free"] = a["tier"] == "basic"
        a["price"] = 0 if a["free"] else entry.get("price", START_PRICE)
        # No fallback. This line used to fill every entry without an
        # itch_url with https://slingshot-tools.itch.io/, which is the
        # account's front page and lists nothing. It reintroduced the exact
        # dead end the audit had just fixed, on every run, and check_exposure
        # then failed the release. An empty value means "not for sale yet",
        # which is true and is what publish_paid.py needs to see.
        #
        # The environment variable was the same fallback with the page
        # hidden, and it was worse: it applied to the free editions as well,
        # so one variable put a buy button on every free product in the
        # catalogue, and no test could see it, because they look for a
        # literal URL and not for a value read from the environment. It is
        # only used for a paid edition, and only when it is a real product
        # page and not the account's front page.
        if a.get("tier") == "basic":
            a.pop("itch_url", None)
        else:
            _fallback = os.environ.get("ITCH_PAGE_URL", "").strip()
            if _fallback and set_itch_url.valid(_fallback):
                a["itch_url"] = a.get("itch_url") or _fallback
            else:
                a["itch_url"] = a.get("itch_url") or ""

    _atomic(PRICES, json.dumps(prices, indent=2))
    _atomic(LOG, json.dumps(history[-200:], indent=2))
    if apps:
        # site/apps.json is the live storefront manifest. Writing it in place
        # meant a crash mid-write could publish a truncated catalogue.
        _atomic(CATALOG, json.dumps(apps, indent=2))

    rows, total_rev, total_net = summarise_earnings(apps, prices)
    tips = profit_directives(apps, prices, rows, total_net)
    earnings = {"date": date.today().isoformat(), "revenue": total_rev,
                "net_profit": total_net, "break_even": break_even_price(),
                "products": rows, "directives": tips}
    _atomic(DATA / "earnings.json", json.dumps(earnings, indent=2))
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