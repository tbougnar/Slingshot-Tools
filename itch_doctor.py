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
import itch_publish as ip

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


def _raw(url: str) -> tuple[int, str]:
    """A plain GET with no credentials, to tell a wrong path from a refused key."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.status, r.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(600).decode("utf-8", "replace")
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

    _out("2. is the API host even answering, and is the key accepted")
    # 404 with "invalid api endpoint" from every path, including ones that must
    # exist, is not a path problem. Asking without a key separates the two: a
    # real endpoint answers 401 when unauthenticated and 404 when the path is
    # invented, so one unauthenticated request says which this is.
    code, body = _raw(f"{API}/profile/whoami")
    _out(f"   no key   GET /profile/whoami -> HTTP {code}  {body[:80]}")
    code_k, body_k = _get("/profile/whoami", key)
    _out(f"   with key GET /profile/whoami -> HTTP {code_k}  {body_k[:80]}")
    if code == 404:
        _out("   the host answers 404 to an unauthenticated request, so the")
        _out("   path is wrong, not the key")
    elif code in (401, 403):
        _out(f"   the endpoint exists (it refuses without a key), so the key is "
             f"the problem: it answered {code_k}")
    _out()
    # Several shapes have been tried. Whichever answers 200 is the real one,
    # because "invalid api endpoint" means the path is wrong, not that the key
    # is refused, and a wrong path here means the pipeline can never find a
    # project that already exists.
    candidates = [
        f"/profile/{user}/games",
        f"/profile/{user}/games?limit=100",
        f"/users/{user}/games",
        f"/profile/{user}",
        f"/profile/{user}/stats/sales",
        "/profile/whoami",
    ]
    works = []
    for path in candidates:
        code, body = _get(path, key)
        n = ""
        if code == 200:
            try:
                got = json.loads(body)
                n = f" ({len(got)} item(s))" if isinstance(got, list) else ""
            except json.JSONDecodeError:
                n = " (not json)"
            works.append(path)
        _out(f"   HTTP {code:<4} GET {path}{n}")
    projects = []
    if works:
        code, body = _get(works[0], key)
        try:
            projects = json.loads(body) or []
        except json.JSONDecodeError:
            projects = []
        _out(f"   the working path is {works[0]}: {len(projects)} project(s)")
        for g in projects[:10]:
            _out(f"        {g.get('url')}")
    else:
        _out("   no listing path answered 200, so the account cannot be read")
    _out()

    _out("3. butler, which is itch.io's own client and the authority")
    # butler is the tool that actually uploads, and the only thing here that
    # speaks itch.io's real protocol. If it accepts the key, the 404s above are
    # this repository's paths being wrong rather than a credential problem.
    import subprocess
    import tempfile

    butler = ip.butler()
    if butler:
        stub = Path(tempfile.gettempdir()) / "slingshot-doctor-stub.zip"
        try:
            stub.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            ident = ip._identity_file(key)
            r = subprocess.run(
                [butler, "push", str(stub),
                 f"{user}/doctor-probe-does-not-exist:windows-64",
                 f"--identity={ident}"],
                capture_output=True, text=True, timeout=240)
            Path(ident).unlink(missing_ok=True)
            said = ((r.stdout or "") + (r.stderr or "")).strip()
            _out(f"   butler push to a project that does not exist exited "
                 f"{r.returncode}")
            for ln in said.splitlines()[-6:]:
                _out(f"     {ln}")
            low = said.lower()
            if "unauthor" in low or "forbidden" in low \
                    or "api key" in low or "invalid" in low:
                _out("   -> the key is REFUSED by itch.io")
                key_ok = False
            elif "not found" in low or "does not exist" in low \
                    or "no such" in low:
                _out("   -> the key is ACCEPTED. The project name is simply"
                     " not one that exists, which is the answer we wanted.")
                key_ok = True
            else:
                _out("   -> butler's answer was not one of the expected"
                     " shapes; read it above")
                key_ok = None
            _out("   nothing was uploaded: the project does not exist")
        finally:
            stub.unlink(missing_ok=True)
    else:
        key_ok = None
        _out("   butler is not on this machine, so the key cannot be tested")
    _out()

    _out("4. the session cookie, if there is one")
    if not cookie:
        _out("   no cookie is stored, so nothing to check")
    else:
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
    if key_ok is True:
        _out()
        _out("The API key works. Upload is therefore fully automated and needs")
        _out("no session at all. The only thing that cannot be automated is")
        _out("creating the very first project, because itch.io has no endpoint")
        _out("for that and its web login is behind a bot challenge.")
        _out()
        _out("Do this once, by hand, in your own browser:")
        _out("  create an empty project at")
        _out("    https://itch.io/settings/mine/new/game")
        _out("  then point the catalog at it:")
        _out("    python set_itch_url.py <slug> https://slingshot-tools.itch.io/<project>")
        _out()
        _out("After that every release is hands-off, forever, because the")
        _out("pipeline finds the project through the key and uploads with it.")
    elif key_ok is False:
        _out()
        _out("The API key is refused by itch.io, so nothing can be uploaded")
        _out("at all. Generate a new one at")
        _out("  https://itch.io/settings/mine/api-keys")
        _out("and set it with")
        _out("  gh secret set ITCH_API_KEY --repo tbougnar/Slingshot-Tools")
    else:
        _out()
        _out("The key could not be tested here. Read the butler output above.")
    auditlog.not_verified(
        "itch-doctor",
        reason="the itch.io capability report above",
        evidence={"key": bool(key), "user": bool(user),
                  "projects": len(projects),
                  "key_accepted_by_butler": key_ok,
                  "cookie_present": bool(cookie)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())