"""Build the real Windows app for a paid Slingshot Tool.

Produces a one-folder app (no Python or pywebview needed on the customer
machine) with the company logo embedded in the executable, then wraps it in an
NSIS installer whose shortcuts point straight at the exe.

Why one-folder and not one-file: a one-file build unpacks ~28 MB to a temp
folder on every launch, which is the multi-second "nothing is happening" delay
people notice. A folder starts instantly.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "native_launcher.py"
DIST = ROOT / "dist"
ICON_PNG = ROOT / "site" / "icon-512.png"


def make_ico(png: Path, out: Path) -> Path | None:
    """Windows needs a real .ico; a 512px png is not enough for the shell."""
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(png).convert("RGBA")
    img.save(out, format="ICO", sizes=[(256, 256), (128, 128), (64, 64),
                                       (48, 48), (32, 32), (16, 16)])
    return out


def build_app(app_dir: Path, title: str) -> Path | None:
    """app_dir holds app/index.html, app/app.json, app/icon.png."""
    if not LAUNCHER.exists():
        print(f"[pyi] no launcher at {LAUNCHER}", flush=True)
        return None

    (app_dir / "app").mkdir(parents=True, exist_ok=True)
    ico = app_dir / "app" / "icon.ico"
    if not ico.exists():
        ico = make_ico(ICON_PNG, ico) if ICON_PNG.exists() else None

    out = DIST / title
    work = DIST / "_pyi"
    for d in (out, work):
        shutil.rmtree(d, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", title,
        "--distpath", str(out),
        "--workpath", str(work),
        "--specpath", str(work),
        "--add-data", f"{app_dir / 'app'}{__import__('os').pathsep}app",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "webview.platforms.winforms",
        "--exclude-module", "webview.platforms.gtk",
        "--exclude-module", "webview.platforms.qt",
        "--exclude-module", "webview.platforms.cocoa",
        "--exclude-module", "webview.platforms.wx",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide6",
    ]
    if ico:
        cmd += ["--icon", str(ico)]
    cmd.append(str(LAUNCHER))

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400)
    exe = out / title / f"{title}.exe"
    if not exe.exists():
        print(f"[pyi] FAILED rc={r.returncode}", flush=True)
        print(((r.stdout or "")[-500:] + (r.stderr or "")[-500:]), flush=True)
        return None
    print(f"[pyi] app built: {exe} ({exe.stat().st_size//1024//1024} MB, one folder)",
          flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return exe.parent          # the folder to install


if __name__ == "__main__":
    t = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if t:
        print("OK" if build_app(t, t.name) else "FAILED")