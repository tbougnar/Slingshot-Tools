"""Serve the private dashboard on localhost only.

This binds to 127.0.0.1 so only this PC can access it. Requests from
non-loopback addresses are rejected as a defense in depth.
"""
from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import make_dashboard


LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def is_loopback(addr: str) -> bool:
    if not addr:
        return False
    addr = addr.strip().lower()
    if addr in LOOPBACK:
        return True
    if addr.startswith("::ffff:"):
        return addr.split("::ffff:", 1)[1] in LOOPBACK
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "SlingshotDashboard/1.0"

    def _allowed(self) -> bool:
        client = (self.client_address[0] if self.client_address else "") or ""
        return is_loopback(client)

    def do_GET(self):  # noqa: N802
        if not self._allowed():
            self.send_error(403, "Forbidden")
            return
        if self.path not in ("/", "/index.html", "/dashboard", "/dashboard.html"):
            self.send_error(404, "Not Found")
            return
        try:
            body = make_dashboard.build_dashboard_html().encode("utf-8")
        except Exception as e:
            msg = f"Dashboard error: {e}".encode("utf-8", "replace")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter
        client = self.client_address[0] if self.client_address else "?"
        sys.stdout.write(f"[dashboard] {client} - {fmt % args}\n")


class LocalOnlyServer(ThreadingHTTPServer):
    # Bind is controlled by caller; this keeps address reuse convenient.
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve private dashboard on localhost only")
    ap.add_argument("--host", default="127.0.0.1", help="Bind host (keep 127.0.0.1 for local-only)")
    ap.add_argument("--port", type=int, default=8765, help="Port to listen on")
    ap.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    args = ap.parse_args()

    host = args.host
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("[dashboard] refusing to bind to non-localhost address. Use 127.0.0.1 to keep it private.")
        return 2
    if host == "localhost":
        host = "127.0.0.1"

    try:
        httpd = LocalOnlyServer((host, args.port), Handler)
    except OSError as e:
        print(f"[dashboard] could not start server: {e}")
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    print(f"[dashboard] private dashboard running at {url}")
    print("[dashboard] accessible only from this PC (localhost). Press Ctrl+C to stop.")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
