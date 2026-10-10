"""Prove the payment worker can create a real order.

Read-only with respect to money: it creates an order and prints the approval
link, but it never approves or captures one. Paying is a deliberate human
step, so this cannot charge anybody by accident.

Usage:
    python verify_live_paypal.py                 # check the deployed worker
    python verify_live_paypal.py --local         # skip the network

Exits non-zero when the worker is unreachable, refuses to create an order, or
is still on sandbox.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # noqa: BLE001
    print("this needs requests: pip install requests")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"
WORKER = "https://slingshot-pay.bougnartaha2.workers.dev"


def load_catalog() -> list:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[paypal] cannot read the catalog: {e}")
        raise SystemExit(1)
    return data if isinstance(data, list) else []


def pick_product(catalog: list) -> dict | None:
    """A paid product that is actually on sale."""
    for a in catalog:
        if a.get("tier") == "full" and a.get("published") is True:
            return a
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="check the payment worker")
    ap.add_argument("--local", action="store_true",
                    help="only check the local catalog")
    args = ap.parse_args()

    catalog = load_catalog()
    paid = [a for a in catalog if a.get("tier") == "full"]
    print(f"[paypal] catalog: {len(catalog)} entries, {len(paid)} full tier")

    if args.local:
        prod = pick_product(catalog)
        if not prod:
            print("[paypal] no full-tier product is published yet")
            return 1
        print(f"[paypal] would test: {prod.get('title')} "
              f"${float(prod.get('price') or 0):.2f}")
        return 0

    prod = pick_product(catalog)
    if not prod:
        print("[paypal] no full-tier product is published yet")
        return 1

    slug = prod.get("base_slug") or prod.get("slug")
    price = float(prod.get("price") or 0)
    print(f"[paypal] testing: {prod.get('title')} ${price:.2f} ({slug})")

    try:
        r = requests.post(f"{WORKER}/api/order",
                          json={"slug": slug, "price": price,
                                "title": prod.get("title"),
                                "email": "verify@example.com"},
                          timeout=40)
    except requests.RequestException as e:
        print(f"[paypal] the worker is unreachable: {e}")
        return 1

    print(f"[paypal] POST /api/order -> {r.status_code}")
    try:
        body = r.json()
    except ValueError:
        print(r.text[:400])
        return 1

    if r.status_code != 200:
        print(f"[paypal] the worker refused the order: {body}")
        return 1

    order = body.get("order")
    approve = body.get("approve") or ""
    if not isinstance(order, str):
        order = order.get("id") if isinstance(order, dict) else ""
    if not order:
        print(f"[paypal] no order id came back: {body}")
        return 1

    charged = body.get("price")
    if isinstance(charged, (int, float)) and not (1.0 <= float(charged) <= 10.0):
        print(f"[paypal] FAIL: the worker will charge ${charged}, "
              f"outside the $1-$10 rule")
        return 1

    host = approve.split("/")[2] if "//" in approve else "(none)"
    print(f"[paypal] order id : {order}")
    print(f"[paypal] price    : ${float(charged):.2f}")
    print(f"[paypal] approval : {host}")

    if "sandbox" in approve:
        print()
        print("[paypal] FAIL: still on sandbox, no real money can move.")
        print("[paypal] see PAYPAL_LIVE.md")
        return 1
    if "paypal.com" not in approve:
        print("[paypal] FAIL: no PayPal approval link came back")
        return 1

    print()
    print("[paypal] OK: the worker is on live PayPal.")
    print(f"[paypal] to finish by hand, open:\n         {approve}")
    print("[paypal] then fetch the build:")
    print(f"  https://{WORKER.split('//')[1]}/api/download?token={order}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())