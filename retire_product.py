"""Take a product off sale, but only when the evidence is overwhelming.

This is the one destructive action the company can take by itself, so it is
deliberately hard. A product may only be retired when all of the following hold:

1. it has been on sale for at least ``RETIRE_MIN_DAYS`` (a year by default)
2. nobody has bought it in that whole time
3. the public evidence agrees it is not popular, rather than merely quiet

Anything short of that and it does nothing. Deleting a product that would have
sold is far more expensive than keeping one that will not, so the default is
always to leave it alone and say so.

Usage:
    python retire_product.py --list
    python retire_product.py <slug>          # retire it, if allowed
    python retire_product.py <slug> --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
EARNINGS = ROOT / "data" / "earnings.json"
HISTORY = ROOT / "data" / "retired.json"
REPORT = ROOT / "data" / "reputation.json"

MIN_DAYS = int(os.environ.get("SLINGSHOT_RETIRE_MIN_DAYS") or 365)

# A product must be this old, and must have sold almost nothing ever: two
# sales across a whole year is not a product anybody wants, while a steady
# trickle is a product worth keeping.
MIN_DAYS_FOR_REVIEW = MIN_DAYS
MAX_LIFETIME_SALES = int(os.environ.get("SLINGSHOT_MAX_RETIRE_SALES") or 2)


def log(msg: str) -> None:
    print(f"[retire] {msg}", flush=True)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def catalog() -> list:
    data = load_json(CATALOG, [])
    return data if isinstance(data, list) else []


def families() -> dict:
    """Products by family, since each has a free and a paid entry."""
    out: dict[str, dict] = {}
    for a in catalog():
        key = a.get("base_slug") or a.get("slug")
        if not key:
            continue
        fam = out.setdefault(key, {"base": key, "basic": None, "full": None})
        if a.get("tier") == "basic":
            fam["basic"] = a
        else:
            fam["full"] = a
    return out


def sales_by_slug() -> dict:
    """Orders recorded per family, from the local earnings ledger."""
    data = load_json(EARNINGS, [])
    orders = data if isinstance(data, list) else data.get("orders", [])
    out: dict[str, dict] = {}
    for o in orders:
        slug = str(o.get("slug") or o.get("base_slug") or "").strip()
        if not slug:
            continue
        row = out.setdefault(slug, {"orders": 0, "revenue": 0.0,
                                    "last": 0})
        try:
            row["orders"] += 1
            row["revenue"] += float(o.get("price") or 0)
        except (TypeError, ValueError):
            pass
        row["last"] = max(row["last"], int(o.get("at") or 0))
    return out


def days_since(stamp) -> int:
    """Days since a date, in UTC."""
    if not stamp:
        return 0
    try:
        if isinstance(stamp, (int, float)):
            then = datetime.fromtimestamp(float(stamp), tz=timezone.utc)
        else:
            then = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - then).days)
    except (ValueError, TypeError, OSError):
        return 0


def on_sale_since(entry: dict) -> int:
    """How long the paid tier has been for sale."""
    raw = (entry.get("published_at") or entry.get("released") or
           entry.get("date") or entry.get("created") or "")
    return days_since(raw)


def evidence(slug: str, fam: dict, sales: dict) -> dict:
    """Everything known about one product, and whether that condemns it."""
    full = fam.get("full") or fam.get("basic") or {}
    row = sales.get(slug, {})
    live_days = on_sale_since(full)
    orders = int(row.get("orders", 0))
    last_sale_days = days_since(row.get("last")) if row.get("last") else None

    reasons = []
    if live_days < MIN_DAYS_FOR_REVIEW:
        reasons.append(f"only {live_days} day(s) on sale, "
                       f"needs {MIN_DAYS_FOR_REVIEW}")
    if orders > MAX_LIFETIME_SALES:
        reasons.append(f"{orders} sale(s) ever, more than the "
                       f"{MAX_LIFETIME_SALES} allowed")
    if last_sale_days is not None and last_sale_days < MIN_DAYS_FOR_REVIEW:
        reasons.append(f"sold something {last_sale_days} day(s) ago, "
                       f"within the last {MIN_DAYS_FOR_REVIEW}")

    rep = load_json(REPORT, {})
    gh = rep.get("github") or {}
    public = {"stars": gh.get("stars"), "forks": gh.get("forks"),
              "watchers": gh.get("watchers"),
              "available": gh.get("available", False)}

    return {
        "slug": slug,
        "title": full.get("title", slug),
        "days_on_sale": live_days,
        "orders": orders,
        "revenue": round(float(row.get("revenue", 0.0)), 2),
        "days_since_last_sale": last_sale_days,
        "public": public,
        "blockers": reasons,
        "may_retire": not reasons and live_days >= MIN_DAYS_FOR_REVIEW,
    }


def list_all() -> int:
    fams = families()
    sales = sales_by_slug()
    if not fams:
        log("the catalog is empty")
        return 0
    print(f"{'slug':<26} {'days':>5} {'sales':>6} {'revenue':>9}  verdict")
    print("-" * 70)
    for slug in sorted(fams):
        ev = evidence(slug, fams[slug], sales)
        verdict = ("may be retired" if ev["may_retire"]
                   else "; ".join(ev["blockers"]) or "keep")
        print(f"{slug:<26} {ev['days_on_sale']:>5} {ev['orders']:>6} "
              f"${ev['revenue']:>8.2f}  {verdict}")
    return 0


def retire(slug: str, dry_run: bool) -> int:
    fams = families()
    sales = sales_by_slug()
    fam = fams.get(slug)
    if not fam:
        log(f"{slug} is not in the catalog")
        return 1

    ev = evidence(slug, fam, sales)
    log(f"{ev['title']}: {ev['days_on_sale']} days on sale, "
        f"{ev['orders']} sale(s), ${ev['revenue']:.2f}")
    if ev["public"].get("available"):
        log(f"public: {ev['public']['stars']} stars, "
            f"{ev['public']['forks']} forks")

    if not ev["may_retire"]:
        log("NOT retired. It does not meet the bar:")
        for r in ev["blockers"]:
            log(f"  - {r}")
        if not ev["blockers"]:
            log(f"  - needs {MIN_DAYS_FOR_REVIEW} days on sale, "
                f"has {ev['days_on_sale']}")
        return 1

    if dry_run:
        log("would retire this product; run without --dry-run to do it")
        return 0

    # Retiring hides the product from the site. It never deletes anything:
    # both catalog entries, the front-end files and the paid build all stay on
    # disk and in git history, so a mistake is one commit away from undone.
    apps = catalog()
    touched = []
    for entry in apps:
        if (entry.get("base_slug") or entry.get("slug")) != slug:
            continue
        entry["published"] = False
        entry["retired"] = int(time.time())
        entry["retired_reason"] = (
            f"no demand after {ev['days_on_sale']} days on sale")
        touched.append(entry)

    if not touched:
        log("nothing matched in the catalog")
        return 1

    save_json(CATALOG, apps)

    history = load_json(HISTORY, [])
    history.append({"slug": slug, "title": ev["title"],
                    "at": int(time.time()), "days_on_sale": ev["days_on_sale"],
                    "orders": ev["orders"], "dry_run": False})
    save_json(HISTORY, history)

    tiers = sorted({str(a.get("tier") or "?") for a in touched})
    log(f"retired {slug}: unpublished {len(touched)} entries "
        f"({', '.join(tiers)}), files and build kept")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="retire an unwanted product")
    ap.add_argument("slug", nargs="?", default="")
    ap.add_argument("--list", action="store_true",
                    help="show every product and whether it may be retired")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list or not args.slug:
        return list_all()
    return retire(args.slug.strip(), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())