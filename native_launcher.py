"""Native Windows shell for a Slingshot Tool.

Renders the same single-file HTML in a REAL native window (WebView2 via
pywebview) instead of a browser tab: no address bar, no tabs, own taskbar
entry, company icon, sane window size.
"""
import os
import sys
from pathlib import Path

import webview

HERE = Path(__file__).resolve().parent
APP = HERE / "app" / "index.html"
ICON = HERE / "app" / "icon.png"

TITLE = (os.environ.get("SLINGSHOT_APP_TITLE")
         or "Slingshot Tool")  # replaced by app.json at runtime
SUBTITLE = "Slingshot Tools"


def main():
    if not APP.exists():
        print(f"missing {APP}", file=sys.stderr)
        return 1
    title = TITLE
    try:
        import json
        meta = HERE / "app" / "app.json"
        if meta.exists():
            title = json.loads(meta.read_text(encoding="utf-8-sig")).get("title", TITLE)
    except Exception:  # noqa: BLE001
        pass

    kwargs = dict(title=title, width=1180, height=820,
                  min_size=(760, 560))
    try:
        webview.create_window(**kwargs)
        webview.start()
    except Exception as e:  # noqa: BLE001
        print(f"native window unavailable ({e}); opening in the default browser",
              file=sys.stderr)
        import webbrowser
        webbrowser.open(APP.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())