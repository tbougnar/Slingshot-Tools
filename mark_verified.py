"""Mark every recorded fix as holding after a clean run.

A fix is not proven by the patch applying - it is proven by the pipeline going
on to finish without that failure coming back. That is what this records.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buglog


def main() -> int:
    entries = buglog.load()
    if not entries:
        print("[fixbook] nothing recorded yet")
        return 0
    before = len(buglog.open_entries())
    buglog.verify([e["id"] for e in entries])
    after = len(buglog.open_entries())
    print(f"[fixbook] clean run: {len(entries)} entries, "
          f"{before - after} newly verified, {after} still unproven")
    try:
        import write_fixbook
        write_fixbook.main()
    except Exception as e:  # noqa: BLE001
        print(f"[fixbook] could not refresh the markdown: {str(e)[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())