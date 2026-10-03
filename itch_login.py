"""Log in to itch.io over plain HTTP and save the session. No browser, no captcha.

Run this yourself in a terminal:
    python itch_login.py

It asks for your itch.io email and password, logs in, and writes the session
cookie to .sessions/itch_session.json. The password is never stored.
"""
from __future__ import annotations

import getpass
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / ".sessions"
OUT_DIR.mkdir(exist_ok=True)
OUT = OUT_DIR / "itch_session.json"
COOKIE_DUMP = ROOT / ".cookies" / "itch.json"
COOKIE_DUMP.parent.mkdir(exist_ok=True)


def csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    if not m:
        raise SystemExit("Could not find the itch.io login token.")
    return m.group(1)


def main() -> int:
    email = input("itch.io email: ").strip()
    password = getpass.getpass("itch.io password (not saved): ")

    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    r = s.get("https://itch.io/login", timeout=60)
    r.raise_for_status()
    token = csrf(r.text)

    r = s.post(
        "https://itch.io/login",
        data={"csrf_token": token, "email": email, "password": password,
              "remember_me": "1", "tou_agreed": "1"},
        headers={"Referer": "https://itch.io/login",
                 "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True, timeout=60,
    )

    body = r.text.lower()
    if "password is incorrect" in body or "invalid password" in body:
        print("Wrong password.")
        return 1
    if "captcha" in body:
        print("itch.io demanded a captcha for this IP. Run this again later.")
        return 1

    check = s.get("https://itch.io/dashboard", timeout=60, allow_redirects=True)
    if "/login" in check.url:
        print(f"Login failed - redirected to {check.url}")
        return 1

    cookies = [{"name": c.name, "value": c.value, "domain": c.domain,
                "path": c.path or "/", "secure": bool(c.secure),
                "httpOnly": bool(c.has_nonstandard_attr("HttpOnly"))}
               for c in s.cookies]
    OUT.write_text(json.dumps({
        "cookies": {c["name"]: c["value"] for c in cookies},
        "saved": None,
        "user": check.url,
    }, indent=1), encoding="utf-8")
    COOKIE_DUMP.write_text(json.dumps(cookies, indent=1), encoding="utf-8")

    print(f"\nLogged in. {len(cookies)} cookies saved.")
    print(f"  session : {OUT}")
    print(f"  cookies : {COOKIE_DUMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())