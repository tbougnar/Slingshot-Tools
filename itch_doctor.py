"""Report exactly which parts of the itch.io path work, and which do not.

The publishing step failed for several weeks for several different reasons, and
each time the only clue was a line in a CI log. This asks the platform the
questions directly and prints the answers, so the next failure says what is
actually wrong rather than where the code gave up.

    python itch_doctor.py

It is read-only with one deliberate exception, described where it happens.
Nothing here creates, changes or deletes anything on the account.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import auditlog

API = "https://api.itch.io"
TIMEOUT = 30


def _out(line: str = "") -> None:
    print(line, flush=True)


def _get(path: str, key: str) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:300]


def main() -> int:
    key = os.environ.get("ITCH_API_KEY", "").strip()
    user = os.environ.get("ITCH_USER", "").strip()
    cookie = os.environ.get("ITCH_SESSION_COOKIE", "").strip()
    login = os.environ.get("ITCH_LOGIN", "").strip()
    password = os.environ.get("ITCH_PASSWORD", "").strip()

    _out("=" * 68)
    _out("ITCH.IO — WHAT WORKS")
    _out("=" * 68)
    _out()

    _out("1. credentials present")
    for name, present, why in (
            ("ITCH_API_KEY", bool(key), "never expires, used for every upload"),
            ("ITCH_USER", bool(user), "the account name"),
            ("ITCH_SESSION_COOKIE", bool(cookie), "expires, needed only to "
                                                   "create a project"),
            ("ITCH_LOGIN", bool(login), "permanent, for the automated login"),
            ("ITCH_PASSWORD", bool(password), "permanent, for the login")):
        _out(f"   {'yes' if present else 'no '}  {name:22s} {why}")
    _out()

    if not key or not user:
        _out("   the API cannot be checked without a key and an account name")
        return 1

    _out("2. the API key is accepted and can read the account")
    status, body = _get(f"/profile/{user}/games", key)
    projects = []
    if status == 200:
        try:
            projects = json.loads(body) or []
        except json.JSONDecodeError:
            projects = []
        _out(f"   yes  the key works, {len(projects)} project(s) on the "
              f"account")
        for g in projects[:10]:
            _out(f"        {g.get('url')}")
    else:
        _out(f"   NO  HTTP {status}: {body[:160]}")
    _out()

    _out("3. can a project be created through the API")
    # An empty body cannot create anything: it asks the endpoint to validate a
    # project with no name and no slug, which it refuses. 404 or 405 means
    # there is no such endpoint and a browser is genuinely required. Anything
    # else means the endpoint exists.
    req = urllib.request.Request(
        f"{API}/profile/{user}/games", data=b"{}", method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code, detail = r.status, r.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code, detail = e.code, e.read(200).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        code, detail = 0, str(e)[:120]
    _out(f"   POST /profile/{user}/games with an empty body -> HTTP {code}")
    if code in (400, 401, 403, 422):
        _out("   the endpoint exists, so a project can be created with the key")
        _out("   and no browser session is needed, ever")
        can_create = True
    elif code in (404, 405, 501):
        _out("   there is no create endpoint, as this repository assumed")
        _out("   a project has to be created through a browser, once")
        can_create = False
    else:
        _out(f"   unexpected: {detail[:140]}")
        can_create = None
    _out()

    _out("4. the session cookie, if there is one")
    if not cookie:
        _out("   no cookie is stored, so nothing to check")
    else:
        import itch_publish as ip
        tok = ip.session_cookie()
        if not tok:
            _out("   the cookie is set but not in a form that can be read")
        else:
            ok = ip.check_session(tok)
            _out(f"   {'accepted' if ok else 'REFUSED'}")
            if not ok:
                _out("   it has expired, which is expected: the account "
                      "credentials are what refresh it")
    _out()

    _out("5. butler, which does the actual upload")
    butler = ip.butler()
    _out(f"   {'present' if butler else 'NOT FOUND'}  {butler or '(not downloaded yet)'}")
    _out()

    _out("=" * 68)
    _out("WHAT THIS MEANS")
    _out("=" * 68)
    if can_create:
        _out()
        _out("Projects can be created with the API key, so the whole path is")
        _out("automated and no session is ever needed. The publish step should")
        _out("use that instead of a browser.")
    elif can_create is False:
        _out()
        _out("A project has to be created through a browser exactly once, the")
        _out("first time there is a product to sell. After that the pipeline")
        _out("finds the project through the API and uploads with the key, so")
        _out("no session is needed again for as long as the project exists.")
        _out()
        _out("To do it once: create an empty project at")
        _out("  https://itch.io/settings/mine/new/game")
        _out("called, for example, 'Slingshot Tools', and then run")
        _out("  python set_itch_url.py <slug> https://youraccount.itch.io/<project>")
        _out("Every release after that is hands-off.")
    auditlog.not_verified(
        "itch-doctor",
        reason="the itch.io capability report above",
        evidence={"key": bool(key), "user": bool(user),
                  "projects": len(projects), "api_can_create": can_create,
                  "cookie_present": bool(cookie)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())