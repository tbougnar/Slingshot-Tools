"""Render the monthly release trailer: 16:9, landscape, about 30 seconds.

A Short is vertical and about fifteen seconds, which is the wrong shape for
"here is what changed this month" and the wrong orientation for a video people
watch on a desktop. So the trailer is its own renderer rather than a flag on
the Shorts one.

What is reused and why:

- ``shorts_render.font`` / ``wrap`` / ``ease`` / ``_load_logo`` / ``_shot_for``
  are read-only helpers with no opinion about the canvas size, so they are
  imported rather than copied. Copying them would create a second place for a
  font bug to live.
- ``merge`` and ``glow`` are *not* reused: both close over the module-level
  ``W``/``H``, so calling them at 1920x1080 would either blow up or paste a
  vertical gradient into a landscape frame. That is the whole reason this file
  exists rather than a parameter on the other one.
- The audio chain (voice, sfx, mux) is length-agnostic and is used unchanged.

    python update_trailer_render.py
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import shorts_render as sr

ROOT = Path(__file__).resolve().parent

# Landscape, because a release trailer is watched on a desktop.
W, H = 1920, 1080
FPS = 30
# The Shorts renderer is pinned to a phone; scale its type up for a wide frame
# so the headline is not a small strip across the middle of the screen.
SCALE = 1.0

BG = (25, 11, 10)
PANEL = (34, 26, 25)
ACCENT = (228, 94, 95)
WHITE = (255, 252, 248)
MUTED = (186, 168, 164)

FRAMES = ROOT / "data" / "trailer_frames"
VOICE = ROOT / "data" / "trailer_voice.json"
SCRIPT = ROOT / "data" / "trailer_script.json"


def log(m: str) -> None:
    print(f"[trailer] {m}", flush=True)


def bg_layer(t: float) -> Image.Image:
    """The drifting warm background, at this canvas's size."""
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = math.sin(t * 0.8) * 0.5 + 0.5
    b = math.cos(t * 0.6) * 0.5 + 0.5
    d.ellipse([int(-400 + a * 900), int(-300 + b * 700),
               int(700 + a * 900), int(900 + b * 700)], fill=(96, 32, 28))
    d.ellipse([int(1100 + b * 800), int(300 + a * 600),
               int(2300 + b * 800), int(1500 + a * 600)], fill=(46, 22, 34))
    return layer.filter(ImageFilter.GaussianBlur(260))


def merge(img: Image.Image, layer: Image.Image, strength: int) -> Image.Image:
    return Image.composite(layer, img, Image.new("L", (W, H), strength))


def centered(d, text: str, fnt, y: int, fill, width: int = W) -> None:
    x = (width - d.textlength(text, font=fnt)) / 2
    d.text((x, y), text, font=fnt, fill=fill)


def frame(t: float, parts: list[dict], state: dict, script: dict) -> Image.Image:
    img = merge(Image.new("RGB", (W, H), BG), bg_layer(t), 150)
    d = ImageDraw.Draw(img)

    # The frame is two columns and the split is fixed, because the card is on
    # the right for the whole video and the type has to stay clear of it.
    MARGIN = 90
    CARD_W, CARD_H = 760, 560
    CARD_X = W - CARD_W - MARGIN
    CARD_Y = (H - CARD_H) // 2 + 40
    TEXT_W = CARD_X - MARGIN - 70
    TEXT_X = MARGIN

    # which line is being spoken right now, and how far into it we are
    idx, into = 0, 0.0
    for i, p in enumerate(parts):
        start = float(p.get("at") or 0.0)
        dur = float(p.get("duration") or p.get("seconds") or 0.0) or 1.0
        if t >= start:
            idx = i
            into = min(1.0, (t - start) / dur)
        if t < start:
            break

    line = (parts[idx].get("text") if parts else "") or ""
    title = str(script.get("title") or "This month's update")
    notes = list(script.get("notes") or [])

    # --- left column: the headline, then the line being spoken
    fnt = sr.font(96, bold=True)[0]
    tlines = sr.wrap(d, title, fnt, TEXT_W)[:3]
    for i, ln in enumerate(tlines):
        ty = 170 + i * 110
        # the shadow is the same line at the same place, only offset. Drawing
        # it at a different y leaves a second copy showing through the first,
        # which is what the title looked like before this was fixed.
        for dx, dy in ((4, 5), (-4, 5), (4, -5), (-4, -5)):
            d.text((TEXT_X + dx, ty + dy), ln, font=fnt, fill=(18, 8, 7))
        d.text((TEXT_X, ty), ln, font=fnt, fill=WHITE)

    small = sr.font(40)[0]
    base = 170 + len(tlines) * 110 + 70
    if line:
        for i, ln in enumerate(sr.wrap(d, line, small, TEXT_W)[:3]):
            # the newest word-line is brightest, so the eye follows the voice
            age = abs(i - into * 2)
            col = tuple(int(c * (0.5 + 0.5 * max(0.15, 1.0 - age * 0.4)))
                        for c in WHITE)
            d.text((TEXT_X, base + i * 56), ln, font=small, fill=col)

    # --- right: the real app, or the plan's bullets when there is no shot
    shot = sr._shot_for(str(script.get("slug") or ""), "base")
    card = Image.new("RGB", (CARD_W, CARD_H), PANEL)
    if shot is not None:
        card.paste(_fit(shot, CARD_W, CARD_H), (0, 0))
    else:
        cd = ImageDraw.Draw(card)
        bf = sr.font(38, bold=True)[0]
        for i, n in enumerate(notes[:4]):
            cd.text((46, 54 + i * 116), "\u2022 " + str(n)[:30],
                    font=bf, fill=WHITE)

    amt = sr.ease(min(1.0, t / 0.9))
    if amt > 0.02:
        mask = Image.new("L", (CARD_W, CARD_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1],
                                              radius=36, fill=int(255 * amt))
        img.paste(card, (CARD_X, CARD_Y), mask)

    # --- the logo, and the version it is announcing
    sr._load_logo()
    if sr._LOGO is not None:
        side = 104
        mark = sr._LOGO.resize((side, side), Image.LANCZOS)
        img.paste(mark, ((W - side) // 2, 36), mark)

    vf = sr.font(34, bold=True)[0]
    centered(d, f"v{script.get('version', '1.0.0')}", vf, H - 84, MUTED)

    return img


def _fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """Cover-fit, centred. Never upscales past the original by much."""
    ratio = max(w / im.width, h / im.height)
    nw, nh = max(w, int(im.width * ratio)), max(h, int(im.height * ratio))
    big = im.resize((nw, nh), Image.LANCZOS)
    return big.crop(((nw - w) // 2, (nh - h) // 2,
                     (nw - w) // 2 + w, (nh - h) // 2 + h))


def main() -> int:
    if not SCRIPT.exists():
        raise SystemExit("[trailer] run update_trailer_script.py first")
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    if not VOICE.exists():
        raise SystemExit("[trailer] run update_trailer_voice.py first")
    voice = json.loads(VOICE.read_text(encoding="utf-8"))

    parts = voice.get("parts") or []
    if not parts:
        raise SystemExit("[trailer] the voice file has no timed parts")

    total = float(voice.get("seconds") or 30.0)
    total = max(4.0, min(120.0, total))
    n = int(round(total * FPS))

    if FRAMES.exists():
        shutil.rmtree(FRAMES, ignore_errors=True)
    FRAMES.mkdir(parents=True, exist_ok=True)

    state = {"shot": 0}
    for i in range(n):
        img = frame(i / FPS, parts, state, script)
        img.convert("RGB").save(FRAMES / f"{i:05d}.jpg", quality=88)

    (ROOT / "data" / "trailer_frames.json").write_text(
        json.dumps({"count": n, "fps": FPS, "seconds": total,
                    "dir": str(FRAMES)}, indent=2), encoding="utf-8")
    log(f"{n} frames, {total:.1f}s, {W}x{H}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())