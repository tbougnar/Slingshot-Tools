"""Get a fresh YouTube refresh token, then hand it to the secret setter.

The refresh token is the only value in this whole pipeline that cannot be
generated or derived. Google issues it once, in a browser, after a person
presses Allow. This script drives that flow over the loopback address so the
only manual step is clicking Allow.

    python shorts_auth.py --save-env
    python set_youtube_secrets.py

The first command writes the client id, client secret and token into the
gitignored .env; the second proves they work together and stores them as
GitHub Actions secrets. Without --save-env the token is only printed, as it
was before.

If the browser cannot reach the local helper (Windows firewall, proxy, IPv6,
redirect-URI mismatch), the script asks you to paste the URL from the address
bar instead. The one-time code in that URL works just as well.
"""
from __future__ import annotations

import http.server
import json
import os
import pathlib
import secrets
import socket
import sys
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
TIMEOUT = int(os.environ.get("SHORTS_AUTH_TIMEOUT", "300"))


def log(m: str) -> None:
    print(f"[auth] {m}", flush=True)


def save_env(values: dict[str, str]) -> pathlib.Path:
    """Keep the fresh pair in the gitignored .env for the secret setter."""
    path = pathlib.Path(__file__).resolve().parent / ".env"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() \
        if path.exists() else []
    keys = set(values)
    kept = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in keys:
            kept.append(f"{name}={values[name]}")
            keys.discard(name)
        else:
            kept.append(line)
    for name in sorted(keys):
        kept.append(f"{name}={values[name]}")
    path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    return path


class Handler(http.server.BaseHTTPRequestHandler):
    """Catches the redirect once, with whatever Google sends back."""

    code: str | None = None
    error: str | None = None
    detail: str | None = None
    done = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (q.get("code") or [None])[0]
        error = (q.get("error") or [None])[0]
        detail = (q.get("error_description") or [None])[0]

        # A browser asks for /favicon.ico and may prefetch other URLs after
        # the OAuth redirect. Those requests carry no code and must never
        # overwrite the real reply we already caught.
        if not (code or error):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if Handler.done.is_set():
            # Keep the first real reply. Later probes are harmless.
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        Handler.code = code
        Handler.error = error
        Handler.detail = detail
        log("the browser reached the local helper")
        log(f"callback contained: {', '.join(sorted(q))}")
        reason = {
            "access_denied": "you said no, which is fine",
            "invalid_scope": "the scope was rejected",
        }.get(error or "", "Google did not send a code")

        body = (f"<html><body style='font-family:sans-serif;padding:40px'>"
                f"<h2>Done</h2><p>{'Authorised.' if code else reason}"
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


class DualStackHTTPServer(http.server.ThreadingHTTPServer):
    """`localhost` can resolve to ::1 or 127.0.0.1. Listen on both."""

    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


def make_server() -> http.server.ThreadingHTTPServer:
    try:
        return DualStackHTTPServer(("::", PORT), Handler)
    except OSError:
        return http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)


def explain_error(error: str, detail: str) -> None:
    blob = (detail or "").lower()
    if "verification" in blob or "developer-approved" in blob \
            or "testers" in blob:
        log("")
        log("This is the consent screen, not a code problem.")
        log("The app is in Testing mode, so only test users may allow it.")
        log("Add the account you are signing in with:")
        log("")
        log("  1. console.cloud.google.com/apis/credentials")
        log("  2. Google Auth Platform, then Test users, Add")
        log("  3. add the Gmail address that owns the YouTube channel")
        log("  4. wait a minute, then run this again")
    elif error == "access_denied":
        log("")
        log("You pressed Cancel, or the wrong account was signed in.")
        log("Run it again and choose Allow.")
    elif "redirect_uri" in blob or "redirect" in blob:
        log("")
        log("The redirect URI does not match the Google OAuth client.")
        log("In console.cloud.google.com/apis/credentials add this exact")
        log(f"Authorized redirect URI: {REDIRECT}")
    else:
        log("")
        log("Run it again; the consent screen must reach Allow.")


def finish_reply() -> str:
    if Handler.error:
        log("")
        log(f"Google said: {Handler.error}")
        explain_error(Handler.error, Handler.detail or "")
        raise SystemExit(f"[auth] {Handler.error}")
    if not Handler.code:
        log(f"nothing usable came back within {TIMEOUT} seconds.")
        raise SystemExit("[auth] no code received")
    return Handler.code


def manual_code() -> str:
    """Finish from the browser address bar when loopback cannot be reached."""
    log("")
    log(f"{TIMEOUT} seconds passed without the browser reaching this helper.")
    log("That is usually a firewall/proxy, an IPv6 problem, or a")
    log("redirect-URI mismatch. We can finish by hand instead.")
    log("")
    log("After pressing Allow, the browser address bar should read like:")
    log(f"  {REDIRECT}/?code=4%2F0...&scope=...")
    log("Paste that whole URL, or just the code, then press Enter.")
    try:
        text = input("[auth] URL or code: ").strip()
    except EOFError:
        text = ""
    if not text:
        raise SystemExit("[auth] no code received")

    q: dict[str, list[str]] = {}
    if "://" in text:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
    elif "code=" in text or "error=" in text:
        q = urllib.parse.parse_qs(text)

    Handler.code = (q.get("code") or [None])[0]
    Handler.error = (q.get("error") or [None])[0]
    Handler.detail = (q.get("error_description") or [None])[0]
    if not Handler.code and not Handler.error and "=" not in text \
            and " " not in text:
        Handler.code = text
    return finish_reply()


def ask_for_code(client_id: str) -> str:
    Handler.code = None
    Handler.error = None
    Handler.detail = None
    Handler.done.clear()

    srv = make_server()
    threading.Thread(target=srv.serve_forever,
                     kwargs={"poll_interval": 0.2}, daemon=True).start()

    state = secrets.token_urlsafe(24)
    url = (f"{AUTH}?client_id={urllib.parse.quote(client_id)}"
           f"&redirect_uri={urllib.parse.quote(REDIRECT)}"
           f"&response_type=code&scope={urllib.parse.quote(SCOPE)}"
           f"&access_type=offline&prompt=consent&state={state}")

    log("if the browser did not open, paste this into it yourself:")
    log("")
    log(url)
    log("")
    log("Sign in as the YouTube channel account, press Allow, then wait.")
    log("If it times out, paste the address-bar URL when asked.")
    log("")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    got = Handler.done.wait(timeout=TIMEOUT)
    srv.shutdown()
    srv.server_close()
    if not got:
        return manual_code()
    return finish_reply()


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
    except urllib.error.HTTPError as e:
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

    if "--save-env" in sys.argv:
        path = save_env({"YOUTUBE_CLIENT_ID": cid,
                         "YOUTUBE_CLIENT_SECRET": csec,
                         "YOUTUBE_REFRESH_TOKEN": refresh})
        log(f"saved the working pair to {path.name} (gitignored)")
        log("now run: python set_youtube_secrets.py")
    else:
        log("")
        log("Put the token in GitHub. The gh CLI is not installed here, so")
        log("use the website (and do not paste the token into a chat):")
        log("")
        log("  1. github.com/tbougnar/Slingshot-Tools/settings/secrets/actions")
        log("  2. Repository secrets -> New repository secret")
        log("  3. Name: YOUTUBE_REFRESH_TOKEN")
        log(f"  4. Value: {refresh}")
        log("")
        log("If the client id or secret changed, update those two secrets on")
        log("the same page. YOUTUBE_PRIVACY is a Variable, not a secret; keep")
        log("it unlisted until you have watched a full Short.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
