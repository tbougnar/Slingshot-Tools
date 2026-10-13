"""Keep the automated jobs inside their time budget.

The company may use 30 hours of compute a month for the weekly cycle, plus 3
hours of emergency budget that only a failing run may touch. This records what
has been spent and says plainly when to stop.

Every job calls ``budget.check`` first and ``budget.spend`` afterwards, so a run
that would blow the budget refuses to start rather than being killed halfway
through and leaving a half-written commit.

State lives in data/budget.json, which is committed, so the hours are visible
in the repository and cannot quietly reset.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "budget.json"

MONTHLY_HOURS = float(os.environ.get("SLINGSHOT_MONTHLY_HOURS") or 30.0)
EMERGENCY_HOURS = float(os.environ.get("SLINGSHOT_EMERGENCY_HOURS") or 3.0)

# A single job may not burn more than this, whatever the monthly total says.
JOB_CAP_HOURS = float(os.environ.get("SLINGSHOT_JOB_CAP_HOURS") or 1.5)

# Emergency budget is only for a run that is repairing something already broken.
EMERGENCY = os.environ.get("SLINGSHOT_EMERGENCY", "").strip() in ("1", "true", "yes")

# Set when the recorded hours cannot be read. The module docstring promises the
# hours "cannot quietly reset"; they did, because a parse error was swallowed
# and an empty budget reads as a month that has spent nothing.
_broken = ""


def log(msg: str) -> None:
    print(f"[budget] {msg}", flush=True)


def warn(msg: str) -> None:
    global _broken
    if _broken == msg:
        # spent() and broken() both read the file; say it once, not twice
        return
    _broken = msg
    print(f"[budget] PROBLEM: {msg}", file=sys.stderr, flush=True)


def month_key(when: float | None = None) -> str:
    t = datetime.fromtimestamp(when or time.time(), tz=timezone.utc)
    return f"{t.year:04d}-{t.month:02d}"


def broken() -> bool:
    """True when the recorded hours cannot be trusted."""
    load()
    return bool(_broken)


def load() -> dict:
    global _broken
    if STATE.exists():
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warn(f"cannot read {STATE.name} ({e}). Treating this month's hours "
                 "as unknown rather than as zero, so jobs will not start on a "
                 "budget that may already be spent.")
            return {"months": {}, "runs": []}
        if not isinstance(data, dict):
            warn(f"{STATE.name} is not an object. Same treatment: the hours "
                 "are unknown, not zero.")
            return {"months": {}, "runs": []}
        data.setdefault("months", {})
        data.setdefault("runs", [])
        _broken = ""
        return data
    # no file at all is a first run, which is legitimately zero
    _broken = ""
    return {"months": {}, "runs": []}


def save(data: dict) -> bool:
    """Write the hours, and report whether it worked.

    The write goes to a side file and is swapped in, so a job that dies halfway
    leaves the previous good total rather than a truncated file that the next
    read would take for "no hours used".
    """
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(STATE)
    except OSError as e:
        warn(f"could not record the hours ({e}). This run's cost was NOT "
             "saved, so the budget is understated until someone repairs it.")
        return False
    return True


def spent(month: str | None = None) -> dict:
    """Hours used so far, split into normal and emergency."""
    month = month or month_key()
    entry = load()["months"].get(month, {})
    normal = float(entry.get("normal", 0.0))
    emergency = float(entry.get("emergency", 0.0))
    return {"month": month, "normal": normal, "emergency": emergency,
            "total": normal + emergency}


def record(label: str, seconds: float, emergency: bool = False) -> bool:
    hours = max(0.0, seconds) / 3600.0
    data = load()
    month = month_key()
    entry = data["months"].setdefault(month, {"normal": 0.0, "emergency": 0.0})
    bucket = "emergency" if emergency else "normal"
    entry[bucket] = round(float(entry.get(bucket, 0.0)) + hours, 4)
    data["runs"] = (data.get("runs") or [])[-49:] + [{
        "label": label,
        "month": month,
        "hours": round(hours, 4),
        "emergency": emergency,
        "at": int(time.time()),
    }]
    return save(data)


def remaining() -> float:
    s = spent()
    left = MONTHLY_HOURS - s["normal"]
    if EMERGENCY:
        left += max(0.0, EMERGENCY_HOURS - s["emergency"])
    return round(left, 3)


def check(label: str = "", planned_hours: float = 0.0) -> int:
    """Refuse to start when there is not enough budget left.

    Returns 0 to go ahead, 1 to stop. A job must not start something it cannot
    finish, so this also checks the planned cost.

    An unreadable budget refuses outright. The old behaviour was to read a
    corrupt or missing total as zero hours used, which approved a job on a
    month that may already have spent all thirty hours.
    """
    tag = f" ({label})" if label else ""
    s = spent()
    if broken():
        log(f"REFUSING{tag or ' (budget)'}: the recorded hours cannot be read, "
            "so there is no way to know what is left. Repair data/budget.json "
            "or set SLINGSHOT_MONTHLY_HOURS deliberately.")
        return 1
    need = planned_hours or JOB_CAP_HOURS

    log(f"{s['month']}: {s['normal']:.2f}h of {MONTHLY_HOURS:.2f}h used, "
        f"{s['emergency']:.2f}h of {EMERGENCY_HOURS:.2f}h emergency")

    if EMERGENCY:
        left = MONTHLY_HOURS - s["normal"] + max(
            0.0, EMERGENCY_HOURS - s["emergency"])
        log(f"running as an emergency job{tag}")
    else:
        left = MONTHLY_HOURS - s["normal"]

    if left <= 0:
        log(f"NO BUDGET LEFT{tag}. Nothing scheduled will run this month.")
        if not EMERGENCY:
            log(f"emergency repair jobs may still use "
                f"{max(0.0, EMERGENCY_HOURS - s['emergency']):.2f}h "
                f"with SLINGSHOT_EMERGENCY=1")
        return 1

    if need > left:
        log(f"REFUSING{tag}: this job needs about {need:.2f}h but only "
            f"{left:.2f}h is left this month")
        return 1

    log(f"approved{tag}: about {need:.2f}h against {left:.2f}h remaining")
    return 0


class Timer:
    """Time a job and write the cost back when it finishes."""

    def __init__(self, label: str, emergency: bool = EMERGENCY):
        self.label = label
        self.emergency = emergency
        self.start = 0.0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *exc):
        used = time.time() - self.start
        wrote = record(self.label, used, self.emergency)
        log(f"{self.label} used {used / 3600.0:.3f}h "
            f"({self.label} total this month: {spent()['total']:.2f}h)")
        if not wrote:
            # the job's own result is unaffected, but the budget is now wrong
            log(f"WARNING: {self.label} cost was not saved, so the monthly "
                "total is understated")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="the monthly compute budget")
    ap.add_argument("action", choices=["check", "status", "record"])
    ap.add_argument("--label", default="manual")
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--need", type=float, default=0.0)
    ap.add_argument("--emergency", action="store_true")
    args = ap.parse_args()

    if args.action == "status":
        s = spent()
        print(json.dumps({
            "month": s["month"],
            "normal_used": s["normal"],
            "normal_limit": MONTHLY_HOURS,
            "emergency_used": s["emergency"],
            "emergency_limit": EMERGENCY_HOURS,
            "total_used": s["total"],
            "remaining": remaining(),
            "emergency_mode": EMERGENCY,
        }, indent=2))
        return 0

    if args.action == "record":
        wrote = record(args.label, args.hours * 3600.0, args.emergency)
        log(f"recorded {args.hours:.3f}h for {args.label}")
        return 0 if wrote else 1

    if args.need > JOB_CAP_HOURS:
        log(f"WARNING: asked for {args.need:.2f}h but a job is capped at "
            f"{JOB_CAP_HOURS:.2f}h")
    return check(args.label, args.need)


if __name__ == "__main__":
    raise SystemExit(main())