"""Scan, hand failures to the builder team, and keep going until it is clean.

The pipeline does not stop at the first failed repair. Each round escalates:
small targeted fixes first, then wider repairs, then a full rewrite by the
strongest model. Only when every escalation has been tried does the app get
flagged for a human - and even then the evidence is attached.
"""
from __future__ import annotations

import json
from pathlib import Path

import app_scanner
import debug_team

MAX_ROUNDS = 6          # escalation ladder, not a single retry
HANDOFF = 3             # after this many rounds, widen the scope

ESCALATION = ["minimal", "minimal", "targeted", "targeted", "rewrite", "rewrite"]


def repair_until_clean(html_path: Path, max_rounds: int = MAX_ROUNDS,
                       log=print) -> tuple[bool, dict]:
    """Return (clean, history). A false first value means 'needs a human'."""
    models = list(debug_team.CANDIDATES)
    leaders = models[:max(debug_team.LEADERS, 3)]
    history: list[dict] = []
    last_scan: dict = {}

    for rnd in range(1, max_rounds + 1):
        mode = ESCALATION[min(rnd - 1, len(ESCALATION) - 1)]
        scan = app_scanner.scan(html_path)
        last_scan = scan

        if app_scanner.verdict(scan):
            log(f"[qa] round {rnd}: CLEAN - {scan.get('controls', 0)} controls "
                f"all respond")
            history.append({"round": rnd, "clean": True})
            log("[qa] handing this build to you for testing")
            return True, history

        log(f"[qa] round {rnd} ({mode}): {len(scan['dead'])} dead, "
            f"{len(scan['errors'])} error(s), {len(scan.get('skipped', []))} skipped")

        if scan["errors"] and not scan["dead"]:
            confirmed = []
            log("[qa] only JS errors present - repairing without a vote")
        else:
            audit = debug_team.audit(models, scan)
            confirmed = audit["confirmed"]
            if not confirmed:
                # the team disagrees; at this point widen rather than stop,
                # because no patch at all is the worst outcome
                confirmed = [d.split("(")[0].strip() for d in scan["dead"][:12]]
                log(f"[qa] no majority; escalating anyway with "
                    f"{len(confirmed)} unconfirmed control(s)")
            else:
                log(f"[qa] team confirmed {len(confirmed)} broken control(s)")

        html = html_path.read_text(encoding="utf-8", errors="replace")
        got = debug_team.fix(leaders, scan, confirmed, html, mode=mode)
        if not got:
            log(f"[qa] round {rnd}: no model produced a usable repair")
            history.append({"round": rnd, "clean": False, "mode": mode,
                            "reason": "no repair"})
            continue

        new_html, by = got
        html_path.with_suffix(f".r{rnd}.bak").write_text(html, encoding="utf-8")
        html_path.write_text(new_html, encoding="utf-8")
        log(f"[qa] round {rnd}: {by} applied a {mode} repair; re-scanning")
        history.append({"round": rnd, "clean": False, "mode": mode,
                        "patched_by": by, "confirmed": confirmed})

    final = app_scanner.scan(html_path)
    ok = app_scanner.verdict(final)
    history.append({"round": max_rounds, "clean": ok,
                    "remaining_dead": final.get("dead", [])[:15],
                    "remaining_errors": final.get("errors", [])[:8]})
    if ok:
        log("[qa] clean after full escalation - handing to you for testing")
    else:
        log("[qa] escalated through every round and it is still broken; "
            "NOT publishing, evidence recorded")
    return ok, history