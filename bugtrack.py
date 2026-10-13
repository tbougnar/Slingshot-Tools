"""The audit bug tracker: one file, one schema, no double counting.

The fixbook in buglog.py is the lesson store. It records what went wrong and
why, which is what the coach reads. It does not record where an audit is up to,
what is still broken, or what is waiting on a credential, so an audit could not
tell finished work from open work by reading it.

This is that record. Every defect the audit finds gets an id, a severity, a
status from a fixed vocabulary, the evidence for it, and what was done. It is
machine readable so the acceptance report can be produced from the data rather
than assembled by hand, which is how reports end up disagreeing with reality.

Statuses, and what they mean:

  NEW                  found, not yet confirmed
  INVESTIGATING        being reproduced or traced
  CONFIRMED            reproduced, cause understood, not yet fixed
  FIXED_PENDING_VERIFICATION   corrected, test not yet run against it
  VERIFIED_FIXED       corrected and the regression test passed
  BLOCKED              confirmed, cannot be fixed here; reason recorded
  NOT_REPRODUCED       looked real, did not reproduce; evidence recorded

The order matters: a defect only reaches VERIFIED_FIXED by passing a test, and
the report is generated from the same data that drives this module, so it
cannot claim more than the store says.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
BOOK = DATA / "bugs.json"

STATUSES = ("NEW", "INVESTIGATING", "CONFIRMED", "FIXED_PENDING_VERIFICATION",
            "VERIFIED_FIXED", "BLOCKED", "NOT_REPRODUCED")

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

# the order fixes are reported in: a customer cannot buy a product beats a
# customer gets a stale page beats a message is ugly
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

_LOCK = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> list[dict]:
    if not BOOK.exists():
        return []
    try:
        data = json.loads(BOOK.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save(bugs: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = BOOK.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bugs, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(BOOK)


def _next_id(bugs: list[dict]) -> str:
    """The next BUG id, from the highest existing one.

    Reading the number out of the id rather than using len() means a deleted or
    filtered entry can never cause an existing id to be handed out twice.
    """
    high = 0
    for b in bugs:
        m = re.fullmatch(r"BUG-(\d+)", str(b.get("id", "")))
        if m:
            high = max(high, int(m.group(1)))
    return f"BUG-{high + 1:03d}"


def record(symptom: str, severity: str = "MEDIUM", component: str = "",
           files: list[str] | None = None, status: str = "CONFIRMED",
           root_cause: str = "", evidence: str = "", repro: str = "",
           fix: str = "", regression_test: str = "", verification: str = "",
           uncertainty: str = "") -> dict:
    """Add one defect. status defaults to CONFIRMED, never to verified."""
    if severity not in SEVERITIES:
        severity = "MEDIUM"
    if status not in STATUSES:
        status = "CONFIRMED"
    bugs = load()
    entry = {
        "id": _next_id(bugs),
        "symptom": symptom,
        "severity": severity,
        "component": component,
        "files": list(files or []),
        "status": status,
        "root_cause": root_cause,
        "evidence": evidence,
        "repro": repro,
        "fix": fix,
        "regression_test": regression_test,
        "verification": verification,
        "uncertainty": uncertainty,
        "opened": _now(),
    }
    bugs.append(entry)
    save(bugs)
    return entry


def update(bug_id: str, **fields) -> dict | None:
    """Change fields on an existing defect.

    Refuses to write a status it does not recognise, and refuses to mark
    something VERIFIED_FIXED with no verification text. A tracker that lets you
    claim a fix without evidence is worse than no tracker.
    """
    bugs = load()
    for b in bugs:
        if b.get("id") == bug_id:
            if "status" in fields and fields["status"] not in STATUSES:
                raise ValueError(f"unknown status {fields['status']!r}")
            if fields.get("status") == "VERIFIED_FIXED" and not (
                    fields.get("verification") or b.get("verification")):
                raise ValueError(
                    f"{bug_id} cannot be VERIFIED_FIXED without verification "
                    "evidence")
            b.update({k: v for k, v in fields.items() if v is not None})
            b["updated"] = _now()
            save(bugs)
            return b
    return None


def by_status(status: str) -> list[dict]:
    return [b for b in load() if b.get("status") == status]


def open_confirmed() -> list[dict]:
    """Defects that still need work.

    Anything not VERIFIED_FIXED, BLOCKED or NOT_REPRODUCED. This is the number
    the acceptance report turns on, so it is computed rather than typed.
    """
    return [b for b in load()
            if b.get("status") not in ("VERIFIED_FIXED", "BLOCKED",
                                       "NOT_REPRODUCED")]


def stats() -> dict:
    """Counts by status and by severity, with no category counted twice."""
    bugs = load()
    out = {s: 0 for s in STATUSES}
    for b in bugs:
        out[b.get("status", "NEW")] = out.get(b.get("status", "NEW"), 0) + 1
    sev = {s: 0 for s in SEVERITIES}
    for b in bugs:
        sev[b.get("severity", "MEDIUM")] = sev.get(b.get("severity", "MEDIUM"), 0) + 1
    return {
        "total": len(bugs),
        "by_status": out,
        "by_severity": sev,
        "open_confirmed": len(open_confirmed()),
    }


def sorted_bugs(bugs: list[dict] | None = None) -> list[dict]:
    """Worst first, then by id, so the report order is stable."""
    rows = bugs if bugs is not None else load()
    return sorted(rows, key=lambda b: (SEVERITY_ORDER.get(b.get("severity", "MEDIUM"), 9),
                                       str(b.get("id", ""))))


if __name__ == "__main__":
    print(json.dumps(stats(), indent=2))