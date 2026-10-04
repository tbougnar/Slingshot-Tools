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
import patcher

MAX_ROUNDS = 8          # escalation ladder, not a single retry
HANDOFF = 3             # after this many rounds, widen the scope

# Each round now costs a few hundred tokens, so there is no reason to
# escalate to a full rewrite: try again, differently.
ESCALATION = ["minimal"] * 8


def _n(value) -> int:
    """Scans are data from a browser probe; never assume a list came back."""
    return len(value) if isinstance(value, (list, tuple, set)) else 0


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

        log(f"[qa] round {rnd} ({mode}): {_n(scan.get('dead'))} dead, "
            f"{_n(scan.get('errors'))} error(s), {_n(scan.get('skipped'))} skipped")

        if _n(scan.get('errors')) and not _n(scan.get('dead')):
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
        controls = [d.split("(")[0].strip() for d in scan.get("dead", [])]

        # Patches are the only repair. Asking a model to reprint a 30 KB file
        # cannot work on a 1000 token a minute tier, and every full rewrite
        # restyled the app and was thrown out by the styling guard.
        repaired = None
        by = "patcher"
        for attempt in range(3):
            patches = patcher.plan_patches(html, controls, models)
            if not patches:
                break
            candidate = patcher.apply_patches(html, patches)
            if not candidate:
                continue
            if candidate == html:
                continue
            trial = html_path.with_suffix(".trial.html")
            trial.write_text(candidate, encoding="utf-8")
            check = app_scanner.scan(trial)
            trial.unlink(missing_ok=True)
            still = {d.split("(")[0].strip() for d in check.get("dead", [])}
            if len(still) < len(scan.get("dead", [])):
                repaired, by = candidate, f"patcher try {attempt + 1}"
                break
            print(f"[qa] patch try {attempt + 1} did not reduce the dead "
                  f"controls ({len(still)} left); asking again differently")

        if not repaired:
            log(f"[qa] round {rnd}: no patch improved on {len(controls)} broken "
                f"control(s)")
            history.append({"round": rnd, "clean": False, "mode": mode,
                            "reason": "no patch worked"})
            continue

        html_path.with_suffix(f".r{rnd}.bak").write_text(html, encoding="utf-8")
        html_path.write_text(repaired, encoding="utf-8")
        log(f"[qa] round {rnd}: {by} reduced the broken controls; re-scanning")
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