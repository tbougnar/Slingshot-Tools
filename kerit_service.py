"""Always-on service for Kerit Cloud (hybrid with GitHub Actions).

Provides what GitHub Actions cannot do well as a persistent service:
- 24/7 HTTP endpoint serving update/votes/events manifests instantly
- background scheduler for vote sync, learning-day scan/publish, and git pull

Run (Pterodactyl/Kerit or locally):
    python kerit_service.py

Environment variables (or .env in repo root / SLINGSHOT_REPO_DIR):
    PORT / SERVER_PORT               bind port (default: 8080). Pterodactyl sets SERVER_PORT.
    HOST=0.0.0.0                     bind host
    SLINGSHOT_REPO_DIR=.             repo directory (default: this file's directory)
    SLINGSHOT_GIT_PULL=1             periodically git pull (default: 1)
    SLINGSHOT_PULL_INTERVAL=300      seconds between git pulls
    SLINGSHOT_SYNC_INTERVAL=60       seconds between votes/site sync
    SLINGSHOT_LEARNING_DAY=0         run learning-day scan on schedule in-service (default: 0)
    SLINGSHOT_LEARNING_CRON_DAY=2    weekday for learning-day scan (Mon=0 .. Sun=6, default Tue=2)
    SLINGSHOT_LEARNING_CRON_HOUR=9   UTC hour for learning-day scan
    SLINGSHOT_LEARNING_CRON_MIN=0    UTC minute for learning-day scan
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Resolve paths relative to this file so launch works from any working directory
# (e.g. /home/container, repo root, or a subdirectory).
ROOT = Path(__file__).resolve().parent


def load_dotenv(paths) -> list[str]:
    """Load KEY=VALUE pairs from .env-like files (stdlib only, no overrides)."""
    loaded = []
    for path in paths:
        try:
            p = Path(path)
            if not p.is_file():
                continue
            for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or any(ch.isspace() for ch in key):
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                # Do not override real environment variables (panel/runtime wins).
                if key not in os.environ:
                    os.environ[key] = value
            loaded.append(str(p))
        except Exception:
            # Never fail startup because of a malformed/unreadable .env file.
            pass
    return loaded


# Load .env early so SLINGSHOT_REPO_DIR/PORT/HOST can be provided via file manager.
_DOTENV_PATHS = [ROOT / ".env", Path.cwd() / ".env"]
_repo_hint = (os.environ.get("SLINGSHOT_REPO_DIR") or "").strip()
if _repo_hint:
    _hint = Path(_repo_hint)
    if not _hint.is_absolute():
        _hint = (ROOT / _hint).resolve()
    _DOTENV_PATHS.append(_hint / ".env")
LOADED_DOTENV = load_dotenv(_DOTENV_PATHS)

REPO = Path(os.environ.get("SLINGSHOT_REPO_DIR") or ROOT)
if not REPO.is_absolute():
    REPO = (ROOT / REPO).resolve()
else:
    REPO = REPO.resolve()
sys.path.insert(0, str(REPO))


def env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() not in ("0", "false", "no", "off", "")


def env_int(name: str, default: int) -> int:
    """Read a numeric setting without letting a bad value break startup."""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[kerit {ts}] {msg}", flush=True)


def get_bind_host_port() -> tuple[str, int, str]:
    host = (os.environ.get("HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port_raw = os.environ.get("PORT")
    source = "PORT"
    if port_raw is None or str(port_raw).strip() == "":
        port_raw = os.environ.get("SERVER_PORT")
        source = "SERVER_PORT" if port_raw not in (None, "") else "default"
    if port_raw is None or str(port_raw).strip() == "":
        port_raw = "8080"
    try:
        port = int(str(port_raw).strip())
    except Exception:
        log(f"invalid port value {port_raw!r} from {source}, falling back to 8080")
        port = 8080
        source = "fallback:8080"
    return host, port, source


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


_WEEKLY_CYCLE_LAST: dict[str, str] = {}


def run_weekly_cycle_stage(stage: str) -> None:
    """Run a weekly_cycle.py stage (monday/wednesday/friday/close-ballot)."""
    stage = (stage or "").strip().lower()
    if stage not in {"monday", "wednesday", "friday", "close-ballot"}:
        log(f"weekly cycle: unknown stage {stage!r}")
        return
    log(f"running weekly cycle stage: {stage}")
    try:
        r = subprocess.run([sys.executable, "weekly_cycle.py", stage], cwd=REPO,
                           capture_output=True, text=True, timeout=3600)
        out = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
        tail = out.splitlines()[-1] if out else f"rc={r.returncode}"
        log(f"weekly cycle {stage} finished (rc={r.returncode}): {tail[:220]}")
    except Exception as e:  # noqa: BLE001
        log(f"weekly cycle {stage} error: {str(e)[:160]}")


def maybe_run_weekly_cycle(now: datetime) -> None:
    """Optional Kerit fallback/scheduler for weekly cycle when GHA is unavailable."""
    if not env_bool("SLINGSHOT_KERIT_WEEKLY_CYCLE", False):
        return
    # Defaults: Mon 09:00, Wed 09:00, Fri 07:00 UTC (close-ballot before build)
    schedule = [
        ("monday", 0, env_int("SLINGSHOT_KERIT_MONDAY_HOUR", 9)),
        ("wednesday", 2, env_int("SLINGSHOT_KERIT_WEDNESDAY_HOUR", 9)),
        ("close-ballot", 4, env_int("SLINGSHOT_KERIT_CLOSE_BALLOT_HOUR", 6)),
        ("friday", 4, env_int("SLINGSHOT_KERIT_FRIDAY_HOUR", 7)),
    ]
    day_key = now.strftime("%Y-%m-%d")
    for stage, weekday, hour in schedule:
        if hour < 0:
            continue
        if now.weekday() == weekday and now.hour == hour:
            marker = f"{day_key}:{stage}:{hour}"
            if _WEEKLY_CYCLE_LAST.get(stage) == marker:
                continue
            _WEEKLY_CYCLE_LAST[stage] = marker
            threading.Thread(target=run_weekly_cycle_stage, args=(stage,), daemon=True).start()


def maybe_start_discord_bot() -> subprocess.Popen | None:
    """Optionally run the Discord bot 24/7 inside Kerit (as a child process)."""
    enabled = env_bool("SLINGSHOT_DISCORD_BOT", False) or env_bool("SLINGSHOT_RUN_DISCORD_BOT", False)
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    if not enabled:
        log("discord bot: disabled (set SLINGSHOT_DISCORD_BOT=1 to run 24/7 in Kerit)")
        return None
    if not token:
        log("discord bot: enabled but DISCORD_BOT_TOKEN is missing; not starting")
        return None
    try:
        proc = subprocess.Popen(
            [sys.executable, "discord_bot.py"],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        log(f"discord bot: started (pid={proc.pid})")
        return proc
    except Exception as e:  # noqa: BLE001
        log(f"discord bot: failed to start ({str(e)[:160]})")
        return None


def maybe_start_ai_monitor():
    """Start 24/7 AI monitor in-process (scans errors/glitches/vulns; auto-fixes or hands off to AI dev team)."""
    enabled = env_bool("SLINGSHOT_KERIT_AI_MONITOR", True)
    if not enabled:
        log("ai monitor: disabled (SLINGSHOT_KERIT_AI_MONITOR=0)")
        return None
    try:
        import kerit_ai_monitor
        t = kerit_ai_monitor.start_background()
        log("ai monitor: started (24/7)")
        return t
    except Exception as e:  # noqa: BLE001
        log(f"ai monitor: failed to start ({str(e)[:160]})")
        return None


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
        f"learning_day={env_bool('SLINGSHOT_LEARNING_DAY', False)}, "
        f"weekly_cycle={env_bool('SLINGSHOT_KERIT_WEEKLY_CYCLE', False)})")
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
            maybe_run_weekly_cycle(datetime.now(timezone.utc))
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
            self._send_json({"error": "not found", "path": str(path)}, status=404)
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
                "votes_source": "kerit",
            })
            return
        if p == "/update.json":
            self._send_file_json(REPO / "site" / "update.json")
            return
        if p == "/votes.json":
            # Serve cached votes immediately; scheduler keeps them fresh in background.
            self._send_file_json(REPO / "site" / "votes.json")
            return
        if p == "/events.json":
            self._send_file_json(REPO / "site" / "events.json")
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        # keep logs quiet; scheduler prints important events
        return


def startup_diagnostics(host: str, port: int, port_source: str) -> None:
    log("startup diagnostics")
    log(f"python: {sys.version.split()[0]} ({sys.executable})")
    log(f"cwd: {Path.cwd()}")
    log(f"script root (__file__ dir): {ROOT}")
    log(f"resolved repo dir: {REPO}")
    log(f"bind target: {host}:{port} (port source: {port_source})")
    if LOADED_DOTENV:
        log(f"loaded .env: {', '.join(LOADED_DOTENV)}")
    else:
        log("loaded .env: none (checked script dir, cwd, and SLINGSHOT_REPO_DIR)")
    checks = [
        ("kerit_service.py", ROOT / "kerit_service.py"),
        ("site/update.json", REPO / "site" / "update.json"),
        ("site/votes.json", REPO / "site" / "votes.json"),
        ("site/events.json", REPO / "site" / "events.json"),
        ("sync_votes_site.py", REPO / "sync_votes_site.py"),
        ("learning_day_scan.py", REPO / "learning_day_scan.py"),
        ("kerit_ai_monitor.py", REPO / "kerit_ai_monitor.py"),
        ("weekly_cycle.py", REPO / "weekly_cycle.py"),
        (".git directory", REPO / ".git"),
    ]
    for label, path in checks:
        state = "OK" if path.exists() else "MISSING"
        log(f"check [{state}] {label}: {path}")
    if not (REPO / "site" / "update.json").exists():
        log("warning: site/update.json missing in repo dir; /update.json will 404 until generated or tracked")


def main() -> int:
    try:
        host, port, port_source = get_bind_host_port()
        startup_diagnostics(host, port, port_source)
        threading.Thread(target=scheduler_loop, daemon=True).start()
        bot_proc = maybe_start_discord_bot()
        ai_monitor = maybe_start_ai_monitor()
        httpd = ThreadingHTTPServer((host, port), Handler)
        log(f"serving on http://{host}:{port} (repo={REPO})")
        log("endpoints: /, /health, /healthz, /update.json, /votes.json, /events.json")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log("stopping (KeyboardInterrupt)")
        finally:
            if bot_proc and bot_proc.poll() is None:
                try:
                    bot_proc.terminate()
                except Exception:
                    pass
            httpd.server_close()
        return 0
    except Exception:
        log("fatal startup error:")
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
