"""Build a standalone Windows exe for a paid Slingshot Tool.

PyInstaller bundles Python + pywebview into one file, so the customer needs
nothing installed. The app HTML is embedded and unpacked to a temp folder at
launch. Windows only has to supply WebView2, which ships with Windows 11 and
current Windows 10.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "native_launcher.py"
DIST = ROOT / "dist"


def build_exe(app_dir: Path, title: str) -> Path | None:
    """app_dir contains app/index.html, app/app.json, app/icon.png."""
    if not LAUNCHER.exists():
        print(f"[pyi] no launcher at {LAUNCHER}", flush=True)
        return None

    out = DIST / (title or app_dir.name)
    tmp = DIST / "_pyi"
    for d in (out, tmp):
        shutil.rmtree(d, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", title or app_dir.name,
        "--distpath", str(out),
        "--workpath", str(tmp),
        "--specpath", str(tmp),
        "--add-data", f"{app_dir / 'app'}{os.pathsep}app",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "webview.platforms.winforms",
        "--hidden-import", "webview.http",
        "--exclude-module", "webview.platforms.gtk",
        "--exclude-module", "webview.platforms.qt",
        "--exclude-module", "webview.platforms.cocoa",
        "--exclude-module", "webview.platforms.wx",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide6",
        str(LAUNCHER),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    exe = out / f"{title or app_dir.name}.exe"
    if not exe.exists():
        print(f"[pyi] FAILED rc={r.returncode}", flush=True)
        tail = (r.stdout or "")[-600:] + (r.stderr or "")[-600:]
        print(tail, flush=True)
        return None
    print(f"[pyi] standalone exe built: {exe.name} "
          f"({exe.stat().st_size // 1024 // 1024} MB)", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return exe


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if target:
        name = target.name
        exe = build_exe(target, name)
        print("OK" if exe else "FAILED")