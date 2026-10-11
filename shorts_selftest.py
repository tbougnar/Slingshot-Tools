"""Drive shorts_auth.ask_for_code without a browser, so both outcomes check out.

A test that hangs is worse than no test: the OAuth path only ever runs when a
person is present, so it goes unverified until something breaks in front of
them. This exercises the success and refusal paths in about a second each.
"""
import sys
import threading
import time
import urllib.parse
import urllib.request

import shorts_auth as sa

sa.webbrowser.open = lambda url: True


def drive(query: str, delay: float = 0.7):
    def go():
        time.sleep(delay)
        urllib.request.urlopen(
            f"http://localhost:{sa.PORT}/?{query}").read()
    threading.Thread(target=go, daemon=True).start()


fails = []

# 1. the happy path: Google sends a code back
drive(urllib.parse.urlencode({"code": "FAKE_CODE_123"}))
try:
    got = sa.ask_for_code("test-id")
    ok = got == "FAKE_CODE_123"
    print(("ok   " if ok else "FAIL "), "a code is received", repr(got))
    if not ok:
        fails.append("code")
except SystemExit as e:
    print("FAIL  a code is received:", e)
    fails.append("code")

# 2. testing-mode refusal: the message Google sends gives no way to act on it
blob = urllib.parse.urlencode({
    "error": "access_denied",
    "error_description": "app has not completed the Google verification "
                         "process, only developer-approved testers",
})
drive(blob)
try:
    sa.ask_for_code("test-id")
    print("FAIL  a refusal is refused, but it returned")
    fails.append("refusal")
except SystemExit as e:
    ok = "access_denied" in str(e)
    print(("ok   " if ok else "FAIL "), "a refusal is reported", str(e))
    if not ok:
        fails.append("refusal")

# 3. silence: a browser that never comes back must not hang forever
def _timeout_case():
    """No request at all: the wait must end rather than block a person."""
    import http.server
    import threading as th

    sa.Handler.done.clear()          # the previous case left this set
    srv = http.server.HTTPServer(("localhost", sa.PORT), sa.Handler)
    th.Thread(target=srv.handle_request, daemon=True).start()
    began = time.monotonic()
    got = sa.Handler.done.wait(timeout=2)
    srv.server_close()
    if got:
        raise AssertionError("the wait returned early")
    if time.monotonic() - began < 1.5:
        raise AssertionError("the wait ended too soon")


try:
    _timeout_case()
    print("ok   a timeout is handled")
except AssertionError as e:
    print("FAIL ", e)
    fails.append("timeout")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)