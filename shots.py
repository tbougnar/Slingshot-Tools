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
import os
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
    """Every app page this checkout can actually show.

    A paid-only checkout has no ``site/apps``. The real interface lives in the
    verifier's private ``paid-build`` artifact, which the Shorts job restores
    into ``paid/`` before this step runs. Looking in both places means the same
    script also works on an older checkout that still has the public demos.
    """
    found: dict[str, Path] = {}
    for root in (ROOT / "paid", ROOT / "site" / "apps"):
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name in found:
                continue
            for rel in ("app/index.html", "index.html"):
                p = d / rel
                if p.exists():
                    found[d.name] = p
                    break
    return sorted(found.items())


def target_slug() -> str:
    """Which product the video is about.

    The Shorts workflow writes ``data/shorts_script.json`` first, so an empty
    dispatch slug still resolves to the product the narration was written
    about. An explicit argument or environment value wins; both are lowercased
    because catalogue slugs are.
    """
    if "--slug" in sys.argv:
        i = sys.argv.index("--slug")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip().lower()
    for var in ("SHORTS_SLUG", "SLUG"):
        value = (os.environ.get(var) or "").strip().lower()
        if value:
            return value
    path = ROOT / "data" / "shorts_script.json"
    if path.exists():
        try:
            return str(json.loads(path.read_text(encoding="utf-8"))
                       .get("slug") or "").strip().lower()
        except (OSError, ValueError):
            pass
    return ""


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

    only = target_slug()
    all_apps = apps()
    if only:
        log(f"the product being advertised is {only}")
        chosen = [(name, page) for name, page in all_apps
                  if name.lower() == only or name.lower().startswith(only)]
    else:
        chosen = all_apps
    if not chosen:
        # A missing screenshot is not a reason to lose the whole video. The
        # renderer draws a labelled stand-in from the product's real features,
        # and says plainly at the end that there was no screenshot.
        log(f"no app page found for {only or 'any product'}; checked paid/ "
            f"and site/apps/; the renderer will use its feature stand-in")
        (ROOT / "data" / "shots.json").write_text("{}", encoding="utf-8")
        return 0

    made: dict[str, object] = {}
    for name, page in chosen:

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