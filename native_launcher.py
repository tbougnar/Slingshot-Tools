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
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
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
WINDOW = None

# Make bundled updater modules importable in frozen and dev layouts.
for _p in (str(BASE), str(Path(getattr(sys, "executable", "") or "").resolve().parent), str(HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

# Set to 0 to ship a build that never checks. The manifest is read from the
# installed bundle, not from the repo, so this works once frozen.
UPDATE_CHECK = os.environ.get("SLINGSHOT_UPDATE_CHECK", "1") not in (
    "0", "false", "no")


def _update_notice():
    """Whether to show the update UI, and what it should say.

    Every failure here returns nothing, because the window must open whether or
    not the check works. An app that cannot reach the update file is not a
    broken app, it is an app that opens.
    """
    if not UPDATE_CHECK:
        return None
    try:
        from importlib import import_module
        mod = import_module("app_update")
    except Exception:  # noqa: BLE001
        return None
    try:
        got = mod.check(BASE, slug=_meta_slug())
        if not got.get("update_available"):
            return None
        return got
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


def _download_file(url: str, dest: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "slingshot-tools-updater"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
    return dest


def _app_executable() -> str:
    # Frozen onedir exe path
    if getattr(sys, "frozen", False):
        return sys.executable
    # Dev fallback: relaunch launcher script if possible
    return sys.executable


def _relaunch_target() -> str:
    exe = _app_executable()
    if exe and Path(exe).exists():
        return exe
    return sys.executable


def _spawn_updater(downloaded: Path, download_url: str) -> None:
    pid = os.getpid()
    target = _relaunch_target()
    work = Path(tempfile.gettempdir()) / "slingshot-updates"
    work.mkdir(parents=True, exist_ok=True)
    is_installer = downloaded.suffix.lower() in (".exe", ".msi")

    if os.name == "nt":
        helper = work / f"apply-update-{pid}.cmd"
        lines = [
            "@echo off",
            "setlocal",
            f"set PID={pid}",
            ":waitloop",
            "timeout /t 1 /nobreak >nul",
            "tasklist /FI \"PID eq %PID%\" 2>nul | find \"%PID%\" >nul",
            "if %ERRORLEVEL%==0 goto waitloop",
        ]
        if is_installer:
            # Try silent first for same-day seamless apply; installer may ignore /S.
            lines += [
                f"\"{downloaded}\" /S",
                "if %ERRORLEVEL% NEQ 0 (",
                f"  \"{downloaded}\"",
                ")",
            ]
        else:
            lines += [f"start \"\" \"{downloaded}\""]
        # Best-effort relaunch (installer may also relaunch depending on config)
        if target and Path(target).exists() and getattr(sys, "frozen", False):
            lines += [
                "timeout /t 2 /nobreak >nul",
                f"start \"\" \"{target}\"",
            ]
        lines += ["del \"%~f0\" >nul 2>&1", "endlocal"]
        helper.write_text("\r\n".join(lines), encoding="utf-8")
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", str(helper)], close_fds=True,
                         creationflags=creation)
    else:
        helper = work / f"apply-update-{pid}.sh"
        lines = [
            "#!/bin/sh",
            f"PID={pid}",
            "while kill -0 \"$PID\" 2>/dev/null; do sleep 1; done",
        ]
        if is_installer:
            lines += [f'"{downloaded}" || true']
        else:
            lines += [f'xdg-open "{downloaded}" >/dev/null 2>&1 || open "{downloaded}" >/dev/null 2>&1 || true']
        if target and Path(target).exists() and getattr(sys, "frozen", False):
            lines += ["sleep 2", f'"{target}" >/dev/null 2>&1 &']
        lines += ['rm -f "$0"']
        helper.write_text("\n".join(lines), encoding="utf-8")
        try:
            os.chmod(helper, 0o755)
        except Exception:
            pass
        subprocess.Popen(["/bin/sh", str(helper)], close_fds=True)


class UpdateBridge:
    def apply_update(self, info=None):
        try:
            info = info or {}
            url = str(info.get("download_url") or info.get("url") or "").strip()
            if not url:
                # Fallback: open site/update page
                import webbrowser
                webbrowser.open("https://tbougnar.github.io/Slingshot-Tools/")
                return {"ok": True, "opened": True}

            # If URL is a web page (not a direct binary), open it for manual download.
            lower = url.lower().split("?")[0]
            if not lower.endswith((".exe", ".msi", ".zip")):
                import webbrowser
                webbrowser.open(url)
                return {"ok": True, "opened": True}

            name = Path(lower).name or "Slingshot-Update.exe"
            dest_dir = Path(tempfile.gettempdir()) / "slingshot-updates"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            _download_file(url, dest)
            _spawn_updater(dest, url)

            def _quit():
                time.sleep(0.5)
                try:
                    if WINDOW is not None:
                        WINDOW.destroy()
                except Exception:
                    pass
                os._exit(0)

            threading.Thread(target=_quit, daemon=True).start()
            return {"ok": True, "downloaded": str(dest)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


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
    global WINDOW
    if not APP.exists():
        print(f"missing {APP}", file=sys.stderr)
        return 1

    api = UpdateBridge()
    window = webview.create_window(
        title=_title(),
        url=APP.as_uri(),          # <-- the actual app; without this it is blank
        width=1180,
        height=820,
        min_size=(760, 560),
        js_api=api,
    )
    WINDOW = window

    def on_loaded():
        try:
            native = getattr(window, "native", None)
            handle = getattr(native, "Handle", None)
            if handle is not None:
                _apply_icon(int(handle))
        except Exception:  # noqa: BLE001
            pass
        # the update UI is triggered here, after the app has drawn, so the app
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