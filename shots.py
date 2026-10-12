"""Screenshot the real app, so the video shows the app and not a drawing.

The window in the video used to be drawn with Pillow, which meant inventing
what the app looked like: the wrong colours, made up rows, a layout nobody
shipped. Rendering the actual HTML fixes that and takes a screenshot of the
interface that genuinely exists.

Uses a headless browser, because Pillow cannot lay out HTML and approximating
the result is what caused the problem.

    python shots.py            render every app
    python shots.py --slug x   render one
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "shots"
W, H = 900, 1200


def log(m: str) -> None:
    print(f"[shot] {m}", flush=True)


def browser() -> str | None:
    """A headless browser, whichever this machine has."""
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "msedge", "chrome"):
        exe = shutil.which(name)
        if exe:
            return exe
    # the Windows install paths, which are never on PATH
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(p).exists():
            return p
    return None


def apps() -> list[tuple[str, Path]]:
    root = ROOT / "site" / "apps"
    if not root.exists():
        return []
    out: list[tuple[str, Path]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        for rel in ("app/index.html", "index.html"):
            p = d / rel
            if p.exists():
                out.append((d.name, p))
                break
    return out


def shoot(exe: str, page: Path, dest: Path, theme: str = "") -> bool:
    """One headless screenshot. Returns False rather than raising.

    When a theme is given it is forced before the page loads. The apps switch
    with a data-theme attribute on the root element, so setting it up front is
    the difference between the real dark mode and a photo of the light one.
    """
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            exe, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-device-scale-factor=1",
            f"--user-data-dir={profile}",
            f"--window-size={W},{H}",
            "--virtual-time-budget=4000",
            "--default-background-color=00000000",
        ]
        if theme:
            cmd.append("--force-dark-mode")
            cmd.append(f"--blink-settings=preferredColorScheme="
                       f"{1 if theme == 'dark' else 0}")
        cmd += [f"--screenshot={dest}", page.resolve().as_uri()]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            log(f"  {page.parent.name}: the browser timed out")
            return False
        except Exception as e:  # noqa: BLE001
            log(f"  {page.parent.name}: {str(e)[:70]}")
            return False

    if dest.exists() and dest.stat().st_size > 3000:
        return True
    tail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    log(f"  {page.parent.name}: no image; {tail[-1][:70] if tail else '?'}")
    return False


def themed_copy(page: Path, theme: str) -> Path:
    """A temporary copy of the page with the theme forced on the root element.

    Copying rather than injecting afterwards: a screenshot is taken at load, so
    anything applied afterwards never reaches the picture.
    """
    src = page.read_text(encoding="utf-8", errors="replace")
    src = src.replace("<html", f'<html data-theme="{theme}"', 1)
    # the apps pick their own theme from storage on load, so clear that
    src = src.replace('localStorage.getItem("theme")', "null")
    src = src.replace("localStorage.getItem('theme')", "null")
    out = page.parent / f"_shot-{theme}.html"
    out.write_text(src, encoding="utf-8")
    return out


def main() -> int:
    exe = browser()
    if not exe:
        log("no headless browser found, so the app preview cannot be shot")
        log("on a GitHub runner, google-chrome is already installed")
        log("locally, install Chrome or Edge and run this again")
        return 1

    log(f"browser: {Path(exe).name}")
    OUT.mkdir(parents=True, exist_ok=True)

    only = None
    if "--slug" in sys.argv:
        only = sys.argv[sys.argv.index("--slug") + 1]

    made: dict[str, object] = {}
    for name, page in apps():
        if only and not name.startswith(only):
            continue

        entry: dict[str, str] = {}
        for theme in ("", "light", "dark"):
            stem = f"{name}" + (f"-{theme}" if theme else "")
            dest = OUT / f"{stem}.png"
            if dest.exists():
                dest.unlink()
            src = page
            tmp = None
            if theme:
                try:
                    tmp = themed_copy(page, theme)
                    src = tmp
                except OSError as e:
                    log(f"  {stem}: could not prepare the page ({e})")
                    continue
            ok = shoot(exe, src, dest, theme=theme)
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if ok:
                kb = dest.stat().st_size / 1024
                log(f"  {stem:34} {kb:6.0f} KB")
                entry[theme or "base"] = str(dest.relative_to(ROOT))
            else:
                entry[theme or "base"] = ""

        made[name] = entry

    (ROOT / "data" / "shots.json").write_text(
        json.dumps(made, indent=2), encoding="utf-8")
    good = sum(1 for v in made.values()
               if isinstance(v, dict) and v.get("base"))
    log(f"{good} of {len(made)} shot")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())