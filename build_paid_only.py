"""Build the paid Windows installer and publish it to the store.

Split out from verification so the browser QA runs on Linux, where runners are
plentiful, and only this step waits for a Windows one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import make_app
    import paid_store

    stage_file = make_app.DATA / "published.json"
    if not stage_file.exists():
        print("[installer] nothing was published to build from")
        return 0
    stage = json.loads(stage_file.read_text(encoding="utf-8"))
    paid = make_app.PAID_DIR / stage["slug"]
    if not paid.exists():
        print(f"[installer] no paid build at {paid}")
        return 1
    ok = paid_store.stage(paid, stage["slug"], None)
    print(f"[installer] store upload: {'ok' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
