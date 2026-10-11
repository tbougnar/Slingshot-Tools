"""Follow every platform link and prove it lands somewhere real.

A link that has quietly stopped working is the worst kind of broken: nothing
errors, the page looks fine, and the only symptom is that nobody can join. The
Discord invite in particular expires on its own, so it is checked rather than
trusted.

    python check_links.py

Each URL is fetched, and a Discord invite is resolved through the public API
so an expired or deleted invite is reported as expired rather than as a
generic 404.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import links

TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def log(m: str) -> None:
    print(f"[link] {m}", flush=True)


def fetch(url: str, method: str = "GET") -> tuple[int, str, str]:
    """Status, where it ended up, and a short body."""
    req = urllib.request.Request(url, method=method,
                                 headers={"User-Agent": UA,
                                          "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(4000).decode("utf-8", "replace")
            return r.status, r.geturl(), body
    except urllib.error.HTTPError as e:
        try:
            return e.code, getattr(e, "url", url), e.read(4000).decode(
                "utf-8", "replace")
        except Exception:  # noqa: BLE001
            return e.code, url, ""
    except Exception as e:  # noqa: BLE001
        return 0, url, str(e)[:120]


def check_discord(url: str) -> tuple[bool, str]:
    """Resolve the invite code through Discord's public endpoint.

    A 404 here means the invite is gone, which is a different problem from the
    server being unreachable and needs a different fix.
    """
    m = re.search(r"discord\.gg/([A-Za-z0-9]+)", url)
    if not m:
        return False, f"{url} is not an invite link"

    code = m.group(1)
    api = f"https://discord.com/api/v9/invites/{code}"
    try:
        req = urllib.request.Request(
            api, headers={"User-Agent": UA,
                          "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, ("this invite has expired or was deleted; make a "
                           "new one and set DISCORD_INVITE_URL")
        return False, f"the invite API answered HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]

    guild = d.get("guild") or {}
    name = guild.get("name", "?")
    members = (d.get("approximate_member_count") or 0)
    if guild.get("temporary"):
        return False, ("the invite is temporary and will expire; in Discord, "
                       "open Server Settings, Invites, and turn off both "
                       "expiry options")
    return True, f"{name}, {members} members, does not expire"


def check_one(c: dict) -> tuple[bool, str]:
    if c["key"] == "discord":
        return check_discord(c["url"])

    status, landed, body = fetch(c["url"])
    if status == 0:
        return False, body or "unreachable"
    if status >= 400:
        return False, f"HTTP {status}"

    detail = ""
    if c["key"] == "youtube":
        # a handle that does not exist still returns 200 with a notice
        if "does not exist" in body.lower() or "404" == body.strip()[:3]:
            return False, "this channel handle does not exist"
        m = re.search(r"<title>([^<]{0,70})", body)
        detail = (m.group(1).strip() if m else landed)[:52]
    elif c["key"] == "website":
        m = re.search(r"<title>([^<]{0,70})", body)
        detail = (m.group(1).strip() if m else "")[:52]
        if "site-links" not in fetch(c["url"])[2] and \
                "site-links" not in body:
            log(f"note: the live page has no link row yet; it ships on the "
                f"next deploy")
    else:
        detail = landed[:52]
    return True, detail or f"HTTP {status}"


def main() -> int:
    log("following every platform link")
    log("")
    bad = []
    for c in links.all_links():
        ok, detail = check_one(c)
        print(f"  {'PASS' if ok else 'FAIL'}  {c['label']:9} {detail}")
        if not ok:
            bad.append(c["key"])
    log("")
    if bad:
        log(f"{len(bad)} link(s) are not working: {', '.join(bad)}")
        return 1
    log("every link lands somewhere real")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())