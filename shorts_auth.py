"""Get the YouTube refresh token, then show the three commands to store it.

The refresh token is the only value in this whole pipeline that cannot be
generated or derived. Google issues it once, in a browser, after a person
presses Allow. This script drives that flow over the loopback address so the
only manual step is clicking Allow.

    python shorts_auth.py

It prints the exact commands to run afterwards. It never stores anything
itself: the token goes straight to a GitHub secret, not to a file on disk.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}"


def log(m: str) -> None:
    print(f"[auth] {m}", flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    """Catches the redirect once, with whatever Google sends back."""

    code: str | None = None
    error: str | None = None
    detail: str | None = None
    done = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Handler.code = (q.get("code") or [None])[0]
        Handler.error = (q.get("error") or [None])[0]
        Handler.detail = (q.get("error_description") or [None])[0]
        reason = {
            "access_denied": "you said no, which is fine",
            "invalid_scope": "the scope was rejected",
        }.get(Handler.error or "", "Google did not send a code")

        body = (f"<html><body style='font-family:sans-serif;padding:40px'>"
                f"<h2>Done</h2><p>{'Authorised.' if Handler.code else reason}"
                f"</p><p>Close this tab and go back to PowerShell.</p>"
                f"</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        Handler.done.set()

    def log_message(self, *a) -> None:   # silence the request spam
        return


def ask_for_code(client_id: str) -> str:
    Handler.code = None
    Handler.error = None
    Handler.detail = None
    Handler.done.clear()

    state = secrets.token_urlsafe(24)
    srv = http.server.HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    url = (f"{AUTH}?client_id={urllib.parse.quote(client_id)}"
           f"&redirect_uri={urllib.parse.quote(REDIRECT)}"
           f"&response_type=code&scope={urllib.parse.quote(SCOPE)}"
           f"&access_type=offline&prompt=consent&state={state}")

    log("if the browser did not open, paste this into it yourself:")
    log("")
    log(url)
    log("")
    log("Sign in as the YouTube channel account, press Allow, then wait.")
    log("")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    # wait for the redirect before closing, or the callback has nowhere to
    # land and the run always fails even though consent succeeded
    got = Handler.done.wait(timeout=300)
    srv.server_close()

    if Handler.error:
        log("")
        log(f"Google said: {Handler.error}")
        blob = f"{Handler.detail or ''}".lower()

        if "verification" in blob or "developer-approved" in blob \
                or "testers" in blob:
            # by far the most common cause, and the message Google sends
            # does not say what to do about it
            log("")
            log("This is the consent screen, not a code problem.")
            log("The app is in Testing mode, so only test users may allow")
            log("it. Add the account you are signing in with:")
            log("")
            log("  1. console.cloud.google.com/apis/credentials")
            log("  2. Google Auth Platform, then Test users, Add")
            log("  3. add the Gmail address that owns the YouTube channel")
            log("  4. wait a minute, then run this again")
        elif Handler.error == "access_denied":
            log("")
            log("You pressed Cancel, or the wrong account was signed in.")
            log("Run it again and choose Allow.")
        else:
            log("")
            log("Run it again; the consent screen must reach Allow.")
        raise SystemExit(f"[auth] {Handler.error}")
    if not got or not Handler.code:
        log("nothing came back within five minutes.")
        log("the tab has to stay open until it says Done.")
        log("if you pressed Allow but this said no code, run it once more:")
        log("Google only issues a refresh token on a fresh consent.")
        raise SystemExit("[auth] no code received")
    return Handler.code


def trade(client_id: str, client_secret: str, code: str) -> dict:
    """Exchange the one-time code for a refresh token."""
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
    }).encode()
    req = urllib.request.Request(
        TOKEN, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # noqa: F405
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"[auth] Google refused the code: {detail}")


def main() -> int:
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

    if not cid or not csec:
        log("paste these two from the Google Cloud console first:")
        log("  $env:YOUTUBE_CLIENT_ID='1234567890-abc.apps.googleusercontent.com'")
        log("  $env:YOUTUBE_CLIENT_SECRET='GOCSPX-xxxxxxxxxxxx'")
        log("then run this again")
        return 1

    code = ask_for_code(cid)
    log("got the code, trading it for a refresh token")

    d = trade(cid, csec, code)
    refresh = d.get("refresh_token")
    if not refresh:
        log("Google returned no refresh token.")
        log("that happens when the account already granted access before.")
        log("run this again; the consent screen will appear fresh.")
        return 1

    log("")
    log("Now store all three. Each asks you to paste, then press Enter:")
    log("")
    log("  gh secret set YOUTUBE_CLIENT_ID --repo tbougnar/Slingshot-Tools")
    log("  gh secret set YOUTUBE_CLIENT_SECRET --repo tbougnar/Slingshot-Tools")
    log("  gh secret set YOUTUBE_REFRESH_TOKEN --repo tbougnar/Slingshot-Tools")
    log("")
    log("When it prompts, paste this for the last one:")
    log("")
    log(f"  {refresh}")
    log("")
    log("Paste it after the prompt appears, not on the command line.")
    log("A value typed onto the command itself stays in your history.")
    log("")
    log("Then the privacy level, which is a variable, not a secret:")
    log("  gh variable set YOUTUBE_PRIVACY --body unlisted "
        "--repo tbougnar/Slingshot-Tools")
    log("")
    log("valid: private, unlisted, public")
    log("start with unlisted until you have watched a full video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())