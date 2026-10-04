"""Scan an app, and if it is broken, have the model team repair it and re-scan.

Runs before anything is published, so a broken app is never advertised.
"""
from __future__ import annotations

import json
from pathlib import Path

import app_scanner
import debug_team


def repair_until_clean(html_path: Path, max_rounds: int = debug_team.MAX_ROUNDS,
                       log=print) -> tuple[bool, dict]:
    """Return (ok, history). ok is True only when a scan comes back clean."""
    models = [m for m in debug_team.CANDIDATES]
    history: list[dict] = []

    for rnd in range(1, max_rounds + 1):
        scan = app_scanner.scan(html_path)
        if app_scanner.verdict(scan):
            log(f"[qa] round {rnd}: clean "
                f"({scan.get('controls', 0)} controls checked)")
            history.append({"round": rnd, "clean": True})
            return True, history

        log(f"[qa] round {rnd}: {len(scan['dead'])} dead control(s), "
            f"{len(scan['errors'])} error(s)")

        # JS errors are fixed by the same repair step, but do not go to a vote.
        if scan["errors"] and not scan["dead"]:
            log("[qa] only JS errors present, repairing directly")
            confirmed = []
        else:
            audit = debug_team.audit(models, scan)
            confirmed = audit["confirmed"]
            log(f"[qa] majority confirmed: {confirmed or 'none'}")
            if not confirmed:
                # nobody could agree, so do not let a model invent a repair
                log("[qa] no majority - stopping rather than guessing")
                history.append({"round": rnd, "clean": False,
                                "unconfirmed": scan["dead"][:10]})
                return False, history

        html = html_path.read_text(encoding="utf-8", errors="replace")
        leaders = models[:debug_team.LEADERS]
        got = debug_team.fix(leaders, scan, confirmed, html)
        if not got:
            log("[qa] no model produced a usable repair")
            history.append({"round": rnd, "clean": False, "reason": "no repair"})
            return False, history

        new_html, by = got
        backup = html_path.with_suffix(".qa.bak")
        backup.write_text(html, encoding="utf-8")
        html_path.write_text(new_html, encoding="utf-8")
        log(f"[qa] patched by {by}; re-scanning")
        history.append({"round": rnd, "clean": False, "patched_by": by,
                        "confirmed": confirmed})

    scan = app_scanner.scan(html_path)
    ok = app_scanner.verdict(scan)
    history.append({"round": max_rounds, "clean": ok})
    return ok, history


if __name__ == "__main__":
    p = Path(__import__("sys").argv[1])
    good, hist = repair_until_clean(p)
    print(json.dumps(hist, indent=1))
    print("RESULT:", "clean" if good else "still broken after repairs")