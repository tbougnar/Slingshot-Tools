"""Pterodactyl/Kerit-friendly entrypoint.

Some Python eggs default to `app.py` or expect a simple entry file at the
container/repo root. This delegates to `kerit_service.main()` which handles
SERVER_PORT/PORT detection, .env loading, diagnostics, and serving.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kerit_service import main


if __name__ == "__main__":
    raise SystemExit(main())
