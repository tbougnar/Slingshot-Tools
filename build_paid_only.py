"""Build the paid Windows installer and say where it has to go.

Split out from verification so the browser QA runs on Linux, where runners are
plentiful, and only this step waits for a Windows one.

itch.io is the store now, so nothing is uploaded automatically. The installer
is built, checked, and its path is printed. You then create the itch.io
project, upload that file, and set the URL with::

    python set_itch_url.py <slug> <https://yourslug.itch.io/the-tool>

The paid tier is not flipped to published here. That is deliberate: it only
happens once an itch_url exists, because a buy button that leads nowhere is
worse than no button. Use ``python publish_paid.py <slug>`` after the upload.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import make_app

    stage_file = make_app.DATA / "published.json"
    if not stage_file.exists():
        print("[installer] nothing was published to build from")
        return 0
    stage = json.loads(stage_file.read_text(encoding="utf-8"))
    paid = make_app.PAID_DIR / stage["slug"]
    if not paid.exists():
        print(f"[installer] no paid build at {paid}")
        return 1

    # the installer itself is what gets uploaded to itch.io
    installers = sorted(Path(paid).rglob("*Setup.exe"))
    if not installers:
        print(f"[installer] no installer was produced in {paid}")
        return 1

    print()
    print("[installer] built and ready for itch.io:")
    for exe in installers:
        size = exe.stat().st_size / 1024 / 1024
        print(f"  {exe}  ({size:.1f} MB)")
    print()
    print("[installer] next steps, by hand:")
    print(f"  1. create the project at https://itch.io/settings/mine/new/game")
    print(f"     title: {stage.get('title') or stage['slug']}")
    print(f"  2. set it to Downloadable, price ${float(stage.get('price') or 0):.2f}")
    print(f"  3. upload the .exe above as the primary download")
    print(f"  4. then run:  python set_itch_url.py {stage['slug']} <the itch.io url>")
    print(f"  5. then run:  python publish_paid.py {stage['slug']}")
    print()
    print("[installer] the paid tier stays hidden until step 5, so nobody can "
          "pay for something that is not there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())