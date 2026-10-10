"""Gather what an outside observer can see, for the Wednesday review.

Three sources, none of which require an account:

- GitHub stars, forks, issues and commit activity, for the public repository
- itch.io page views and sales, when ITCH_API_KEY is configured
- the Cloudflare KV read counter the payment worker keeps, if it is reachable

Nothing here changes a price or deletes anything. It only reads, so it cannot
break the site and cannot be wrong in a way that costs money.

Every source is optional. A missing key means one line of "unavailable" in the
report, never a crash, because the weekly cycle must never fail over telemetry.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "data" / "reputation.json"
CATALOG = ROOT / "site" / "apps.json"
EARNINGS = ROOT / "data" / "earnings.json"

REPO = os.environ.get("GITHUB_REPO", "tbougnar/Slingshot-Tools")
SITE = "https://tbougnar.github.io/Slingshot-Tools"
TIMEOUT = 25


def log(msg: str) -> None:
    print(f"[reputation] {msg}", flush=True)


def fetch(url: str, headers: dict | None = None, token: str = "") -> dict | None:
    hdr = dict(headers or {})
    hdr.setdefault("User-Agent", "slingshot-tools/1.0")
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log(f"{url.split('/')[2]}: HTTP {e.code}")
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        log(f"{url.split('/')[2]}: {e}")
    return None


def github_signals() -> dict:
    """Stars, forks, watchers, open issues, last push."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    data = fetch(f"https://api.github.com/repos/{REPO}", token=token)
    if not data:
        return {"available": False}

    issues = fetch(f"https://api.github.com/repos/{REPO}/issues"
                   f"?state=open&per_page=100", token=token)
    # the API counts pull requests as issues, so they are taken out
    real_issues = [i for i in (issues or [])
                   if "pull_request" not in i][:100]

    return {
        "available": True,
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "watchers": data.get("subscribers_count", 0),
        "open_issues": len(real_issues),
        "last_push": data.get("pushed_at", ""),
        "created": data.get("created_at", ""),
        "days_old": _days_since(data.get("created_at", "")),
    }


def _days_since(stamp: str) -> int:
    if not stamp:
        return 0
    try:
        import datetime as dt
        then = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        return max(0, (now - then).days)
    except (ValueError, TypeError):
        return 0


def itch_signals() -> dict:
    """Page views and sales from itch.io, when a key is configured."""
    user = os.environ.get("ITCH_USER", "").strip() or "slingshot-tools"
    key = os.environ.get("ITCH_API_KEY", "").strip()
    if not key:
        return {"available": False, "reason": "no ITCH_API_KEY"}

    data = fetch(f"https://itch.io/api/1/x/stats/sales/{user}",
                 {"Authorization": f"Bearer {key}"})
    if not data:
        return {"available": False, "reason": "request failed"}

    views = fetch(f"https://itch.io/api/1/x/stats/visits/{user}",
                  {"Authorization": f"Bearer {key}"}) or {}
    return {
        "available": True,
        "sales": data,
        "visits": views,
    }


def catalog_signals() -> dict:
    """What is on sale, and for how long."""
    try:
        apps = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False}

    live = [a for a in apps if a.get("published") is not False]
    paid = [a for a in live if a.get("tier") == "full"]
    prices = [float(a.get("price") or 0) for a in paid]
    return {
        "available": True,
        "entries": len(apps),
        "live": len(live),
        "paid": len(paid),
        "lowest_price": min(prices) if prices else 0.0,
        "highest_price": max(prices) if prices else 0.0,
        "catalog_mtime": int(CATALOG.stat().st_mtime),
    }


def earnings_signals() -> dict:
    """Recorded revenue, if the payment worker has been reporting it."""
    if not EARNINGS.exists():
        return {"available": False, "reason": "no earnings file"}
    try:
        data = json.loads(EARNINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "reason": "unreadable"}
    orders = data if isinstance(data, list) else data.get("orders", [])
    total = 0.0
    for o in orders:
        try:
            total += float(o.get("price") or 0)
        except (TypeError, ValueError):
            continue
    return {"available": True, "orders": len(orders), "total": float(total),
            "currency": "USD"}


def gather() -> dict:
    report = {
        "at": int(time.time()),
        "site": SITE,
        "repo": REPO,
        "github": github_signals(),
        "itch": itch_signals(),
        "catalog": catalog_signals(),
        "earnings": earnings_signals(),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def summarise(report: dict) -> str:
    gh = report["github"]
    cat = report["catalog"]
    earn = report["earnings"]
    lines = ["REPUTATION", ""]
    if gh.get("available"):
        lines += [
            f"  github stars      : {gh['stars']}",
            f"  forks             : {gh['forks']}",
            f"  watchers          : {gh['watchers']}",
            f"  open issues       : {gh['open_issues']}",
            f"  repo age          : {gh['days_old']} days",
        ]
    else:
        lines.append("  github            : unavailable")
    lines.append("")
    if cat.get("available"):
        lines += [
            f"  products live     : {cat['live']} ({cat['paid']} paid)",
            f"  price range       : ${cat['lowest_price']:.2f} - "
            f"${cat['highest_price']:.2f}",
        ]
    else:
        lines.append("  catalog           : unavailable")
    if earn.get("available"):
        lines.append(f"  recorded revenue  : ${earn['total']:.2f} "
                     f"from {earn['orders']} order(s)")
    else:
        lines.append(f"  revenue           : {earn.get('reason', 'unavailable')}")
    if report["itch"].get("available"):
        lines.append("  itch.io           : reachable")
    else:
        lines.append(f"  itch.io           : "
                     f"{report['itch'].get('reason', 'unavailable')}")
    return "\n".join(lines)


def main() -> int:
    report = gather()
    print(summarise(report))
    print()
    print(f"[reputation] written to {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())