"""PayPal orders, payment capture, and license keys.

Sandbox by default; set PAYPAL_ENV=live (plus PAYPAL_CLIENT_ID/PAYPAL_SECRET)
once PayPal approves the business account.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LICENSE_DIR = ROOT / "site" / "licenses"
LICENSE_DIR.mkdir(parents=True, exist_ok=True)
ADDRESS = {
    "address_line_1": "1 Rue des Oasis",
    "admin_area_2": "Casablanca",
    "postal_code": "20000",
    "country_code": "MA",
}


def live() -> bool:
    return (os.environ.get("PAYPAL_ENV") or "").lower() == "live"


def base() -> str:
    return "https://api-m.paypal.com" if live() else "https://api-m.sandbox.paypal.com"


def creds() -> tuple[str, str]:
    if live():
        cid = os.environ.get("PAYPAL_CLIENT_ID", "")
        sec = os.environ.get("PAYPAL_SECRET", "")
    else:
        cid = os.environ.get("PAYPAL_SANDBOX_CLIENT_ID") or os.environ.get("PAYPAL_CLIENT_ID", "")
        sec = os.environ.get("PAYPAL_SANDBOX_SECRET") or os.environ.get("PAYPAL_SECRET", "")
    if not cid or not sec:
        raise SystemExit("PayPal credentials are not configured.")
    return cid, sec


def _call(url: str, method: str = "GET", body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    is_token_req = url.endswith("token?grant_type=client_credentials")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    elif method == "POST" and not is_token_req:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    elif method == "POST" and is_token_req:
        cid, sec = creds()
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise RuntimeError(f"PayPal {method} {url} -> {e.code}: {detail}") from None


def token() -> str:
    url = f"{base()}/v1/oauth2/token?grant_type=client_credentials"
    return _call(url, "POST")["access_token"]


# ---------------------------------------------------------------- orders
def create_order(slug: str, title: str, price: float, description: str = "") -> dict:
    """Create a PayPal order and return it (contains the approve URL)."""
    price = round(max(float(price), 0.5), 2)
    intent = "CAPTURE"
    body = {
        "intent": intent,
        "purchase_units": [{
            "reference_id": slug,
            "custom_id": slug,
            "description": (description or title)[:127],
            "amount": {
                "currency_code": "USD",
                "value": f"{price:.2f}",
                "breakdown": {
                    "item_total": {"currency_code": "USD", "value": f"{price:.2f}"},
                },
            },
        }],
        "application_context": {
            "brand_name": "Slingshot Tools",
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
            "return_url": (os.environ.get("SITE_URL") or "").rstrip("/")
            + "/full.html",
            "cancel_url": (os.environ.get("SITE_URL") or "").rstrip("/")
            + "/checkout.html?cancelled=1",
        },
    }
    order = _call(f"{base()}/v2/checkout/orders", "POST", body, token=token())
    approve = ""
    for link in order.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            approve = link.get("href", "")
            break
    order["_approve_url"] = approve
    return order


def capture(order_id: str) -> dict:
    return _call(f"{base()}/v2/checkout/orders/{order_id}/capture", "POST", {}, token=token())


def order_paid(order_id: str) -> bool:
    o = _call(f"{base()}/v2/checkout/orders/{order_id}", "GET", token=token())
    return o.get("status") == "COMPLETED"


# ---------------------------------------------------------------- keys
def _sign(slug: str, raw: str) -> str:
    body = f"slingshot|{slug}|{raw}"
    return hmac.new((os.environ.get("LICENSE_SECRET") or "slingshot-dev").encode(),
                    body.encode(), hashlib.sha256).hexdigest()[:8]


def new_key(slug: str) -> str:
    raw = secrets.token_urlsafe(24)
    return f"SS-{raw[:16]}-{raw[16:]}-{_sign(slug, raw)}"


def verify_key(key: str, slug: str) -> bool:
    parts = key.split("-")
    if len(parts) != 4 or parts[0] != "SS":
        return False
    raw = parts[1] + parts[2]
    return hmac.compare_digest(_sign(slug, raw), parts[3])


def save_key(slug: str, key: str, order_id: str, email: str = "") -> None:
    f = LICENSE_DIR / "issued.json"
    data = json.loads(f.read_text()) if f.exists() else {}
    data[slug] = {"key": key, "order_id": order_id, "email": email,
                  "issued": int(time.time())}
    f.write_text(json.dumps(data, indent=1), encoding="utf-8")


def public_key(slug: str) -> str | None:
    """The key already issued for this product, if any."""
    f = LICENSE_DIR / "issued.json"
    if not f.exists():
        return None
    return (json.loads(f.read_text()).get(slug) or {}).get("key")


if __name__ == "__main__":
    print("env:", "live" if live() else "sandbox")
    tok = token()
    print("auth: OK, token acquired")
    k = new_key("demo")
    print("key format:", k)
    print("verify ok:", verify_key(k, "demo"), "| wrong slug rejected:",
          not verify_key(k, "other"))