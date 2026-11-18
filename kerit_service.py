"""Always-on service for Kerit Cloud (hybrid with GitHub Actions).

Provides what GitHub Actions cannot do well as a persistent service:
- 24/7 HTTP endpoint serving update/votes/events manifests instantly
- background scheduler for vote sync, learning-day scan/publish, and git pull

Run on Kerit:
    python kerit_service.py

Environment variables:
    PORT=8080                         bind port (Kerit/platform may set PORT)
    HOST=0.0.0.0                      bind host
    SLINGSHOT_REPO_DIR=.              repo directory (default: this file's dir)
    SLINGSHOT_GIT_PULL=1              periodically git pull (default: 1)
    SLINGSHOT_PULL_INTERVAL=300       seconds between git pulls
    SLINGSHOT_SYNC_INTERVAL=60        seconds between votes/site sync
    SLINGSHOT_LEARNING_DAY=0          run learning-day scan on schedule in-service (default: 0)
    SLINGSHOT_LEARNING_CRON_DAY=2     weekday for learning-day scan (Mon=0 .. Sun=6, default Tue=2)
    SLINGSHOT_LEARNING_CRON_HOUR=9    UTC hour for learning-day scan
    SLINGSHOT_LEARNING_CRON_MIN=0     UTC minute for learning-day scan
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ.get("SLINGSHOT_REPO_DIR") or ROOT).resolve()
sys.path.insert(0, str(REPO))


def env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() not in ("0", "false", "no", "off", "")


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[kerit {ts}] {msg}", flush=True)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def git_pull() -> None:
    try:
        r = subprocess.run(["git", "pull", "--ff-only"], cwd=REPO,
                           capture_output=True, text=True, timeout=120)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            if out and "Already up to date" not in out:
                log(f"git pull: {out.splitlines()[-1][:200]}")
        else:
            log(f"git pull failed: {out[:200]}")
    except Exception as e:  # noqa: BLE001
        log(f"git pull error: {str(e)[:120]}")


def sync_votes() -> None:
    try:
        r = subprocess.run([sys.executable, "sync_votes_site.py"], cwd=REPO,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            if out:
                log(f"vote sync issue: {out[:200]}")
    except Exception as e:  # noqa: BLE001
        log(f"vote sync error: {str(e)[:120]}")


def run_learning_day_scan() -> None:
    log("running learning-day scan")
    try:
        r = subprocess.run([sys.executable, "learning_day_scan.py"], cwd=REPO,
                           capture_output=True, text=True, timeout=1800)
        out = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
        tail = out.splitlines()[-1] if out else f"rc={r.returncode}"
        log(f"learning-day scan finished (rc={r.returncode}): {tail[:220]}")
    except Exception as e:  # noqa: BLE001
        log(f"learning-day scan error: {str(e)[:160]}")


class ServiceState:
    def __init__(self):
        self.last_learning_stamp = ""

    def maybe_run_learning_day(self) -> None:
        if not env_bool("SLINGSHOT_LEARNING_DAY", False):
            return
        try:
            day = int(os.environ.get("SLINGSHOT_LEARNING_CRON_DAY", "2"))
            hour = int(os.environ.get("SLINGSHOT_LEARNING_CRON_HOUR", "9"))
            minute = int(os.environ.get("SLINGSHOT_LEARNING_CRON_MIN", "0"))
        except Exception:
            day, hour, minute = 2, 9, 0
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y-%W")
        if now.weekday() == day and now.hour == hour and now.minute == minute:
            if self.last_learning_stamp != stamp:
                self.last_learning_stamp = stamp
                threading.Thread(target=run_learning_day_scan, daemon=True).start()


STATE = ServiceState()


def scheduler_loop():
    pull_interval = max(30, int(os.environ.get("SLINGSHOT_PULL_INTERVAL", "300")))
    sync_interval = max(15, int(os.environ.get("SLINGSHOT_SYNC_INTERVAL", "60")))
    do_pull = env_bool("SLINGSHOT_GIT_PULL", True)
    next_pull = 0.0
    next_sync = 0.0
    log(f"scheduler started (pull={do_pull}/{pull_interval}s, sync={sync_interval}s, "
        f"learning_day={env_bool('SLINGSHOT_LEARNING_DAY', False)})")
    while True:
        now = time.time()
        try:
            if now >= next_sync:
                sync_votes()
                next_sync = now + sync_interval
            if do_pull and now >= next_pull:
                git_pull()
                next_pull = now + pull_interval
            STATE.maybe_run_learning_day()
        except Exception as e:  # noqa: BLE001
            log(f"scheduler error: {str(e)[:160]}")
        time.sleep(15)


class Handler(BaseHTTPRequestHandler):
    server_version = "SlingshotKerit/1.0"

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file_json(self, path: Path):
        data = read_json(path, None)
        if data is None:
            self._send_json({"error": "not found"}, status=404)
            return
        self._send_json(data)

    def do_GET(self):  # noqa: N802
        p = urlparse(self.path).path
        if p in ("/", "/health", "/healthz"):
            self._send_json({
                "ok": True,
                "service": "slingshot-kerit",
                "time": datetime.now(timezone.utc).isoformat(),
                "repo": str(REPO),
            })
            return
        if p == "/update.json":
            self._send_file_json(REPO / "site" / "update.json")
            return
        if p == "/votes.json":
            # serve freshest available view
            sync_votes()
            self._send_file_json(REPO / "site" / "votes.json")
            return
        if p == "/events.json":
            self._send_file_json(REPO / "site" / "events.json")
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        # keep logs quiet; scheduler prints important events
        return


def main() -> int:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    threading.Thread(target=scheduler_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    log(f"serving on http://{host}:{port} (repo={REPO})")
    log("endpoints: /health, /update.json, /votes.json, /events.json")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("stopping")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
