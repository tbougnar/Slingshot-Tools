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

    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Handler.code = (q.get("code") or [None])[0]
        body = (b"<html><body style='font-family:sans-serif;padding:40px'>"
                b"<h2>Done</h2><p>You can close this tab and go back to "
                b"PowerShell.</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a) -> None:   # silence the request spam
        return


def ask_for_code(client_id: str) -> str:
    state = secrets.token_urlsafe(24)
    srv = http.server.HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    url = (f"{AUTH}?client_id={urllib.parse.quote(client_id)}"
           f"&redirect_uri={urllib.parse.quote(REDIRECT)}"
           f"&response_type=code&scope={urllib.parse.quote(SCOPE)}"
           f"&access_type=offline&prompt=consent&state={state}")
    log("a browser tab is opening")
    log("sign in as the YouTube channel you want the videos on")
    log("then press Allow, and come back here")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        log("the browser would not open, so paste this into it instead:")
        log(url)

    srv.server_close()
    code = Handler.code
    if not code:
        raise SystemExit("[auth] no code came back; try again")
    return code


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
    log("That is the token. Store all three now:")
    log("")
    log("  gh secret set YOUTUBE_CLIENT_ID --repo tbougnar/Slingshot-Tools")
    log("  gh secret set YOUTUBE_CLIENT_SECRET --repo tbougnar/Slingshot-Tools")
    log(f"  gh secret set YOUTUBE_REFRESH_TOKEN --repo "
        f"tbougnar/Slingshot-Tools   # then paste {refresh[:12]}...")
    log("")
    log("For the token one, type this and paste when prompted:")
    log("  gh secret set YOUTUBE_REFRESH_TOKEN --repo "
        "tbougnar/Slingshot-Tools")
    log("")
    log("And the privacy level, which is a variable rather than a secret:")
    log("  gh variable set YOUTUBE_PRIVACY --body unlisted "
        "--repo tbougnar/Slingshot-Tools")
    log("")
    log("valid values: private, unlisted, public")
    log("start with unlisted until you have watched a full video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())