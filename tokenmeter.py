"""Token accounting, so the pipeline knows what it has left.

Every provider reports how many tokens a call used. Knowing the running total
lets each stage decide sensibly: repair while there is allowance left,
regenerate when there is not. Guessing at this is what made runs fail
mysteriously after burning the allowance on retries.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "token_usage.json"
_lock = threading.Lock()
WINDOW = 60.0          # the allowance is per minute


def _load() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def add(prompt: int, completion: int, model: str = "", provider: str = "") -> int:
    """Record usage and return the total for the current minute."""
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
            STATE.write_text(json.dumps(s, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return int(s["total"])


def spent() -> int:
    s = _load()
    if time.time() - float(s.get("window_start", 0)) > WINDOW:
        return 0
    return int(s.get("total", 0))


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