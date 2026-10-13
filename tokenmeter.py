"""Token accounting, so the pipeline knows what it has left.

Every provider reports how many tokens a call used. Knowing the running total
lets each stage decide sensibly: repair while there is allowance left,
regenerate when there is not. Guessing at this is what made runs fail
mysteriously after burning the allowance on retries.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "token_usage.json"
_lock = threading.Lock()
WINDOW = 60.0          # the allowance is per minute

# Set when usage could not be recorded or read. A meter that cannot read its
# own state must not be trusted to say there is allowance left: the whole point
# of this file is to stop a run from overrunning the limit, and "assume it is
# fine" is the one assumption that causes the overrun. Callers decide what to
# do; spent() reports what is known.
_broken = ""

# What spent() reports when the state is unreadable. Any value at or above any
# limit makes remaining() 0 and affordable() False, so a broken meter stops
# spending rather than spending without limit.
_UNKNOWN = 10 ** 9


def _warn(msg: str) -> None:
    global _broken
    _broken = msg
    print(f"[tokenmeter] {msg}", file=sys.stderr)


def _load() -> dict:
    """Read the state, and say so when the file is there but unreadable.

    A missing file is a fresh minute and is fine. A file that exists but cannot
    be parsed is a different matter: the old code swallowed that and returned
    {}, which reads as zero tokens spent, so a corrupt file looked like a full
    allowance and the pipeline spent the whole limit before anything noticed.
    """
    global _broken
    if STATE.exists():
        try:
            got = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            _warn(f"cannot read {STATE.name} ({e}); treating usage as unknown "
                  "rather than zero")
            return {}
        if not isinstance(got, dict):
            _warn(f"{STATE.name} is not an object; treating usage as unknown")
            return {}
        _broken = ""
        return got
    _broken = ""
    return {}


def add(prompt: int, completion: int, model: str = "", provider: str = "") -> int:
    """Record usage and return the total for the current minute.

    A write that fails is reported on stderr rather than passing silently. It
    used to be swallowed by a bare except, so a full disk or a read-only data
    directory looked exactly like a normal run while the total silently reset
    on the next read.
    """
    now = time.time()
    with _lock:
        s = _load()
        if now - float(s.get("window_start", 0)) > WINDOW:
            s = {"window_start": now, "total": 0, "calls": 0}
        s["total"] = int(s.get("total", 0)) + int(prompt or 0) + int(completion or 0)
        s["calls"] = int(s.get("calls", 0)) + 1
        s["last_model"] = model or s.get("last_model", "")
        s["last_provider"] = provider or s.get("last_provider", "")
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            # a half-written file is the corrupt case _load() now reports, so
            # write to one side and swap it in
            tmp = STATE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
            tmp.replace(STATE)
        except OSError as e:
            _warn(f"could not record {s['total']} tokens ({e}); this run's "
                  "accounting is unreliable")
        return int(s["total"])


def spent() -> int:
    """Tokens used in the current window, or the full limit if unknowable.

    Returning 0 for an unreadable file was the original bug: callers ask
    remaining() and affordable() to decide whether to make another call, and a
    broken meter answered "yes, plenty left" every time.
    """
    s = _load()
    if _broken:
        return _UNKNOWN
    if time.time() - float(s.get("window_start", 0)) > WINDOW:
        return 0
    return int(s.get("total", 0))


def unknown() -> bool:
    """True when the meter cannot be trusted to answer."""
    spent()
    return bool(_broken)


def remaining(limit: int) -> int:
    return max(0, limit - spent())


def affordable(limit: int, want: int) -> bool:
    return remaining(limit) >= want


def reset() -> None:
    with _lock:
        try:
            STATE.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    print(f"spent this minute: {spent()} tokens")
    print(f"remaining of 8000: {remaining(8000)}")