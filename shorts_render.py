"""Render the Short: animated type over a drifting gradient, 1080x1920.

Everything is drawn with Pillow and written out as a frame sequence, because
that needs no ffmpeg on the machine doing the drawing and produces the same
result whether it runs on a laptop or on a GitHub runner.

The look is deliberate. Warm paper tones rather than the neon purple every AI
video generator reaches for, one accent colour, and type large enough to read
with the sound off, which is how most people first see a Short.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920
FPS = 30

PAPER = (244, 241, 234)
INK = (26, 24, 22)
MUTED = (122, 116, 106)
ACCENT = (214, 88, 46)      # warm coral, used once or twice per video
DEEP = (32, 30, 38)

FONT_DIR = Path("C:/Windows/Fonts")


def log(m: str) -> None:
    print(f"[render] {m}", flush=True)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("seguibl.ttf", "segoeuib.ttf") if bold
                 else ("segoeui.ttf", "arial.ttf")):
        p = FONT_DIR / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    """Break on words, so a long line never runs off the edge."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def ease(t: float) -> float:
    """Out cubic. Text that overshoots looks cheap; this settles cleanly."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def background(seed: int) -> Image.Image:
    """A soft vertical wash with two blurred blooms, re-centred per frame."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=(int(244 - 16 * t), int(241 - 16 * t), int(234 - 10 * t)))
    return img


def blooms(img: Image.Image, t: float, seed: int) -> Image.Image:
    """Two out-of-focus colour blobs that drift on slow sine paths.

    Composited at low opacity so the paper still reads as paper. The blobs give
    the frame depth and motion that a flat wash cannot.
    """
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = math.sin(t * 0.9 + seed) * 0.5 + 0.5
    b = math.cos(t * 0.7 + seed * 1.7) * 0.5 + 0.5
    d.ellipse([int(-200 + a * 500), int(-150 + b * 420),
               int(560 + a * 500), int(560 + b * 420)], fill=(222, 128, 92))
    d.ellipse([int(520 + b * 500), int(1180 + a * 380),
               int(1340 + b * 500), int(1900 + a * 380)], fill=(92, 118, 168))
    layer = layer.filter(ImageFilter.GaussianBlur(200))
    mask = Image.new("L", (W, H), 54)
    return Image.composite(layer, img, mask)


def fit(img: Image.Image, t: float, seed: int) -> Image.Image:
    """Ken Burns. A still frame reads as a slideshow; slow motion does not."""
    s = 1.045 + 0.02 * math.sin(t * 1.1 + seed)
    nw, nh = int(W * s), int(H * s)
    big = img.resize((nw, nh), Image.LANCZOS)
    dx = (nw - W) * (0.5 + 0.5 * math.sin(t * 0.5))
    dy = (nh - H) * (0.5 + 0.5 * math.cos(t * 0.4))
    return big.crop((int(dx), int(dy), int(dx) + W, int(dy) + H))


def caption(draw: ImageDraw.ImageDraw, words: list[dict], now: float,
            fade: float) -> None:
    """The words being spoken, in a fixed band well above the progress bar.

    Pinned to a band rather than hung under the headline: when the headline
    changes shape the caption has to stay put, or the frame reads as two
    unrelated pieces of text.
    """
    if not words:
        return
    live = [w for w in words if w["start"] <= now <= w["end"]]
    text = " ".join(w["t"] for w in live).strip()
    if not text:
        return

    fnt = font(60, bold=True)
    lines = wrap(draw, text, fnt, W - 300)
    line_h = 96
    top = int(H * 0.835)
    y = top - len(lines) * line_h
    for ln in lines:
        tw = draw.textlength(ln, font=fnt)
        x = (W - tw) / 2
        # sized off the real font box, not a guess: a tight plate clips the
        # ascenders and the caption ends up struck through mid-word
        asc, desc = fnt.getmetrics()
        box_h = asc + desc
        pad_x = 34
        draw.rounded_rectangle(
            [x - pad_x, y - 14, x + tw + pad_x, y + box_h + 16],
            radius=(box_h + 30) // 2, fill=(255, 255, 255, 232))
        draw.text((x, y), ln, font=fnt, fill=INK)
        y += line_h


def scene_text(img: Image.Image, title: str, sub: str, reveal: float,
               accent: bool) -> Image.Image:
    """Headline with a wipe-in, plus an optional accent bar.

    Sits above centre, with the eyebrow higher still. Composition is top
    weighted because the bottom third belongs to the captions and the progress
    bar, and text centred on the frame collides with both.
    """
    d = ImageDraw.Draw(img, "RGBA")
    fnt = font(124, bold=True)
    lines = wrap(d, title, fnt, W - 160)
    line_h = 160
    block = len(lines) * line_h
    y = int(H * 0.30) - block / 2 + int((1 - ease(reveal / 0.5)) * 50)

    if sub:
        sf = font(44)
        sy = y - 96
        a = ease(reveal / 0.45)
        tw = d.textlength(sub, font=sf)
        d.rounded_rectangle([(W - tw) / 2 - 26, sy - 12,
                             (W + tw) / 2 + 26, sy + 66],
                            radius=30, fill=(*ACCENT, int(220 * a)))
        d.text(((W - tw) / 2, sy), sub, font=sf, fill=(255, 255, 255, int(255 * a)))
        y = int(H * 0.30) - block / 2 + int((1 - ease(reveal / 0.5)) * 50)

    for i, ln in enumerate(lines):
        appear = ease((reveal - i * 0.12) / 0.5)
        if appear <= 0:
            y += line_h
            continue
        tw = d.textlength(ln, font=fnt)
        x = (W - tw) / 2
        off = int((1 - appear) * 44)
        d.text((x, y + off), ln, font=fnt, fill=(*INK, int(255 * appear)))
        if accent and i == 0:
            # a rule that underlines, never one that strikes through the words
            bar_w = int(tw * appear)
            by = y + off + line_h - 34
            d.rectangle([x, by, x + bar_w, by + 14],
                        fill=(*ACCENT, int(255 * appear)))
        y += line_h
    return img


def progress(img: Image.Image, done: float) -> Image.Image:
    """A hairline at the bottom. Signals the clip is finished, and holds eye."""
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, H - 10, W, H], fill=(*MUTED, 70))
    d.rectangle([0, H - 10, int(W * max(0.0, min(1.0, done))), H],
                fill=(*ACCENT, 235))
    return img


def main() -> int:
    script = json.loads((ROOT / "data" / "shorts_script.json")
                        .read_text(encoding="utf-8"))
    voice = json.loads((ROOT / "data" / "shorts_voice.json")
                       .read_text(encoding="utf-8"))
    out = ROOT / "data" / "shorts_frames"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()

    total = float(script.get("seconds") or 30)
    n = int(total * FPS)
    name = script.get("name") or "Slingshot Tool"
    price = script.get("price") or ""

    # a scene per narration line, so the copy changes with the speech
    nlines = max(1, len(voice["parts"]))
    spans = [i / nlines for i in range(nlines + 1)]

    base = background(1)
    log(f"{n} frames at {W}x{H}, {n} // {FPS}")

    for i in range(n):
        t = i / n
        which = min(nlines - 1, int(t * nlines))
        local = (t - spans[which]) / max(1e-6, spans[which + 1] - spans[which])
        img = fit(base, t, 1.7)
        img = blooms(img, t, 1.7)

        line = voice["parts"][which]["text"]
        big = which == 0
        img = scene_text(img, line if big else line,
                         name if big else "", ease(local / 0.22), big)
        if which == nlines - 1 and price:
            d = ImageDraw.Draw(img, "RGBA")
            pf = font(66, bold=True)
            a = ease((local - 0.28) / 0.4)
            tw = d.textlength(price, font=pf)
            px, py = (W - tw) / 2, int(H * 0.56)
            d.rounded_rectangle([px - 40, py - 24, px + tw + 40, py + 104],
                                radius=40, fill=(*DEEP, int(236 * a)))
            d.text((px, py), price, font=pf, fill=(*ACCENT, int(255 * a)))

        d = ImageDraw.Draw(img, "RGBA")
        caption(d, _words(voice["parts"], t, total), t, 1.0)
        progress(img, t)

        img.save(out / f"{i:05d}.jpg", quality=88)

        if i % 150 == 0:
            log(f"  frame {i}/{n}")

    (ROOT / "data" / "shorts_frames.json").write_text(
        json.dumps({"frames": n, "fps": FPS, "seconds": total}, indent=2),
        encoding="utf-8")
    log(f"done -> {out}")
    return 0


def _words(parts: list[dict], t: float, total: float) -> list[dict]:
    """Rebuild a word clock across the whole clip from the per-line offsets.

    Each line gets an equal share of the timeline and the words inside it are
    scaled to fit, which keeps the caption and the spoken audio in step. Equal
    shares are close enough: the per-line gaps are small next to the drift that
    a real per-line duration would avoid.
    """
    if not parts:
        return []
    each = total / len(parts)
    words: list[dict] = []
    for idx, part in enumerate(parts):
        base = idx * each
        marks = part.get("offset") or []
        if not marks:
            continue
        span = marks[-1]["offset"] or 0.001
        for j, m in enumerate(marks):
            start = base + (m["offset"] / span) * each
            nxt = marks[j + 1]["offset"] if j + 1 < len(marks) \
                else m["offset"] + 0.25
            end = base + (nxt / span) * each
            # a word holds its highlight until the next begins, so a word
            # spoken quickly does not flash for a single frame
            words.append({"t": m["text"], "start": start,
                          "end": max(end, start + 0.22)})
    return words


if __name__ == "__main__":
    raise SystemExit(main())