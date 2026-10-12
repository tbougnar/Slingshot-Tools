"""Native Windows shell for a Slingshot Tool.

Real native window (WebView2 via pywebview) showing the same single-file HTML:
no browser chrome, product name as the window title, and the company logo as the
window + taskbar icon instead of Python's.

The update check lives here rather than in the app, because the app is
forbidden from making network calls and that promise is worth more than a
convenience feature. See app_update.py.
"""
import ctypes
import json
import os
import sys
from pathlib import Path

import webview

HERE = Path(__file__).resolve().parent
# When frozen with PyInstaller the app files live in the bundle's temp folder,
# so the customer does not need Python, pywebview, or the app folder installed.
BUNDLE = getattr(sys, "_MEIPASS", None)
BASE = Path(BUNDLE) if BUNDLE else HERE
APP = BASE / "app" / "index.html"
ICON_PNG = BASE / "app" / "icon.png"
ICON_ICO = BASE / "app" / "icon.ico"

# Set to 0 to ship a build that never checks. The manifest is read from the
# installed bundle, not from the repo, so this works once frozen.
UPDATE_CHECK = os.environ.get("SLINGSHOT_UPDATE_CHECK", "1") not in (
    "0", "false", "no")


def _update_notice():
    """Whether to show the banner, and what it should say.

    Every failure here returns nothing, because the window must open whether or
    not the check works. An app that cannot reach the update file is not a
    broken app, it is an app that opens.
    """
    if not UPDATE_CHECK:
        return None
    try:
        # importlib so the frozen build still works when the module is absent
        from importlib import import_module
        mod = import_module("app_update")
    except Exception:  # noqa: BLE001
        return None
    try:
        got = mod.check(BASE, slug=_meta_slug())
        if not got.get("update_available"):
            return None
        msg = f"{got.get('installed')} is installed, {got.get('latest')} is out"
        if got.get("coming_title"):
            msg += f" — {got['coming_title']} lands {got.get('coming')}"
        return msg
    except Exception:  # noqa: BLE001
        return None


def _meta_slug() -> str:
    meta = BASE / "app" / "app.json"
    if not meta.exists():
        return ""
    try:
        return str(json.loads(
            meta.read_text(encoding="utf-8-sig")).get("slug") or "")
    except Exception:  # noqa: BLE001
        return ""


def _title():
    meta = BASE / "app" / "app.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8-sig")).get("title") or "Slingshot Tool"
        except Exception:  # noqa: BLE001
            pass
    return "Slingshot Tool"


def _apply_icon(hwnd):
    """Windows draws the taskbar/titlebar icon from the process image, which is
    pythonw.exe. Override it with our own logo."""
    ico = None
    if ICON_ICO.exists():
        ico = str(ICON_ICO)
    elif ICON_PNG.exists():
        try:
            from PIL import Image
            tmp = BASE / "app" / "_icon.ico"
            Image.open(ICON_PNG).convert("RGBA").save(
                tmp, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            ico = str(tmp)
        except Exception:  # noqa: BLE001
            ico = None
    if not ico or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        hicon = user32.LoadImageW(None, ico, 1, 0, 0, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if hicon:
            user32.SendMessageW(hwnd, 0x0080, 0, hicon)   # WM_SETICON, ICON_SMALL
            user32.SendMessageW(hwnd, 0x0081, 0, hicon)   # WM_SETICON, ICON_BIG
            user32.SendMessageW(hwnd, 0x0082, 0, hicon)   # WM_SETICON, ICON_SMALL2
    except Exception:  # noqa: BLE001
        pass


def main():
    if not APP.exists():
        print(f"missing {APP}", file=sys.stderr)
        return 1

    window = webview.create_window(
        title=_title(),
        url=APP.as_uri(),          # <-- the actual app; without this it is blank
        width=1180,
        height=820,
        min_size=(760, 560),
    )

    def on_loaded():
        try:
            native = getattr(window, "native", None)
            handle = getattr(native, "Handle", None)
            if handle is not None:
                _apply_icon(int(handle))
        except Exception:  # noqa: BLE001
            pass
        # the banner is injected here, after the app has drawn, so the app
        # never has to know the network exists
        notice = _update_notice()
        if notice:
            try:
                window.evaluate_js(
                    f"window.__slingshotUpdate && "
                    f"window.__slingshotUpdate({json.dumps(notice)})")
            except Exception:  # noqa: BLE001
                pass

    try:
        window.events.loaded += on_loaded
    except Exception:  # noqa: BLE001
        pass

    try:
        webview.start()
    except Exception as e:  # noqa: BLE001
        print(f"native window unavailable ({e}); falling back to the browser",
              file=sys.stderr)
        import webbrowser
        webbrowser.open(APP.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())