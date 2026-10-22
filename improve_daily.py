"""One small improvement a day, or none at all.

This wraps self_upgrade.py, which already knows how to propose a patch and
throw it away if the tests fail. What this adds is restraint and direction:

- **It does nothing most days.** A job that must change something every run
  fills the repository with churn, and churn is how a codebase becomes
  impossible to read and slow to change safely. Not doing anything is a
  success, not a failure, and it says so.
- **It is told what to aim at.** The current goal decides what counts as an
  improvement. Chasing reach and chasing revenue need different changes, and a
  job that ignores this spends its budget on whichever it tries first.
- **It refuses to run while a bigger thing is in flight.** Changing the
  generator in the middle of a release makes the release harder to explain
  when it goes wrong.

    python improve_daily.py            try
    python improve_daily.py --list     what it would consider
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "improve_daily.json"

# Enough gaps between real changes that the repository stays readable.
COOLDOWN_HOURS = 20


def log(m: str) -> None:
    print(f"[improve] {m}", flush=True)


def load() -> dict:
    if not STATE.exists():
        return {"changes": [], "skips": []}
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {"changes": [], "skips": []}
    if not isinstance(d, dict):
        return {"changes": [], "skips": []}
    # The lists inside are read as lists of records. A file holding
    # {"changes": {"a": 1}} or {"changes": [null]} made last_change() raise an
    # AttributeError, so a corrupted state file took the lane down with a
    # traceback instead of skipping the day.
    for key in ("changes", "skips"):
        rows = d.get(key)
        if not isinstance(rows, list):
            d[key] = []
            continue
        d[key] = [r for r in rows if isinstance(r, dict)]
    return d


def save(state: dict) -> None:
    # The write goes to a side file and is swapped in, so a crash halfway
    # through leaves the previous file rather than a truncated one that the
    # next read would take for an empty history.
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def last_change(state: dict) -> datetime | None:
    for row in reversed(state.get("changes") or []):
        try:
            return datetime.fromisoformat(str(row.get("at", "")))
        except ValueError:
            continue
    return None


def on_cooldown(state: dict) -> int:
    """Hours left before another change is allowed. Zero means go ahead."""
    last = last_change(state)
    if last is None:
        return 0
    left = COOLDOWN_HOURS - (now() - last).total_seconds() / 3600
    return max(0, int(left + 0.999))


def busy() -> str:
    """Why today is not the day, or an empty string when it is."""
    try:
        import update_state as us
        state = us.load()
        ph = us.phase(state)
        if ph == "announced":
            return ("a major update is announced this week; the generator is "
                    "left alone so the release can be explained if it goes "
                    "wrong")
    except Exception as e:  # noqa: BLE001
        log(f"could not read the release state: {str(e)[:60]}")
    try:
        import budget
        # budget.check() refuses when the recorded hours cannot be read, and
        # remaining() does not: on a corrupt budget file spent() reads as
        # zero and remaining() says a whole month is left, so the lane
        # believed it had thirty hours when the truth was unknown and
        # started work on it. The refusal is the answer, not a number.
        if budget.check("daily-improve", planned_hours=0.5) != 0:
            return "the compute budget for this month is gone"
    except Exception as e:  # noqa: BLE001
        log(f"could not read the budget: {str(e)[:60]}")
    return ""


def objective() -> str:
    """What today is for, in one line, taken from the current goal."""
    try:
        import goals
        got = goals.check(apply=False)
        if got["phase"] == "earn":
            return ("people can see the work, so make it easier to buy: "
                    "conversion, price, and a paid tier worth paying for")
        return ("there is no audience yet, so make more people find the work: "
                "reach, sharing, and things worth keeping")
    except Exception as e:  # noqa: BLE001
        log(f"could not read the goal: {str(e)[:60]}")
        return "improve the generator, guided by the recorded bugs"


def skip(state: dict, why: str) -> int:
    row = {"at": now().isoformat(), "why": why}
    state.setdefault("skips", [])
    state["skips"] = (state["skips"] or [])[-29:] + [row]
    save(state)
    log(f"not today: {why}")
    log("doing nothing is a valid outcome; the suite has to stay green")
    return 0


def _last_outcome(path) -> tuple:
    """What the improver recorded last, as (fingerprint, at, outcome).

    The lane used to decide whether anything changed by comparing the bytes
    of data/self_upgrade.json before and after. The improver rewrites that
    file on every path, including "the model proposed nothing" and "the patch
    was rejected and rolled back", so the bytes always differed and the lane
    always said a change had been made. It recorded changes that never
    happened, and it started the cooldown on days when nothing was done.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(data, dict):
        return ()
    tried = data.get("tried")
    if not isinstance(tried, list) or not tried:
        return ()
    last = tried[-1]
    if not isinstance(last, dict):
        return ()
    return (str(last.get("fingerprint") or ""), last.get("at"),
            str(last.get("outcome") or ""))


def attempt(state: dict) -> int:
    """Ask self_upgrade for one patch and let it decide whether to keep it."""
    import self_upgrade as su

    before = (ROOT / "data" / "self_upgrade.json")
    was = _last_outcome(before)

    try:
        rc = su.main()
    except SystemExit as e:
        # SystemExit.code is anything the raiser passed, not just an int.
        # providers.active() raises it with the message "no model provider is
        # configured", so int() here raised ValueError and turned a clean
        # "there is no model" into a traceback on every run without a key.
        code = e.code
        if isinstance(code, int):
            rc = code
        else:
            why = str(code or "").strip() or "it stopped early"
            log(f"self_upgrade stopped: {why[:70]}")
            return skip(state, f"the improver stopped: {why[:60]}")
    except Exception as e:  # noqa: BLE001
        log(f"self_upgrade could not run: {str(e)[:70]}")
        return skip(state, f"the improver failed: {str(e)[:50]}")

    now_state = _last_outcome(before)
    # a change means a patch was kept, not that a file was rewritten
    changed = bool(now_state) and now_state != was and now_state[2] == "kept"

    if rc == 0 and changed:
        row = {"at": now().isoformat(), "objective": objective()}
        state["changes"] = (state.get("changes") or [])[-29:] + [row]
        save(state)
        log("a change was made and the suite passed")
        return 0

    log("no change worth keeping, so nothing was committed")
    return skip(state, "the improver found nothing that survived the suite")


def main() -> int:
    if "--list" in sys.argv:
        print("DAILY IMPROVEMENT")
        print(f"  current objective : {objective()}")
        state = load()
        print(f"  cooldown          : {COOLDOWN_HOURS}h between changes")
        print(f"  changes so far    : {len(state.get('changes') or [])}")
        for row in (state.get("changes") or [])[-5:]:
            print(f"    {row.get('at', '')[:16]}  "
                  f"{row.get('objective', '')[:60]}")
        print()
        print("  may edit          : only the generator and its QA stack")
        print("  must keep green   : the full suite, every run")
        return 0

    if os.environ.get("FORCE", "").lower() in ("1", "true", "yes"):
        log("FORCE is set, so the cooldown is ignored")
    else:
        left = on_cooldown(load())
        if left:
            return skip(load(), f"{left}h since the last change, and the "
                                f"cooldown is {COOLDOWN_HOURS}h")

    why_not = busy()
    if why_not:
        return skip(load(), why_not)

    return attempt(load())


if __name__ == "__main__":
    raise SystemExit(main())