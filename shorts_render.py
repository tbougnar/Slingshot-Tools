"""Render the Short: your prototype's theme, built for a phone.

The palette and the feel come from the Slingshot Notes prototype: a near
black with a warm cast, one coral accent, heavy centred type, and a lot of
air. What is new here is the motion, because the prototype was static.

- type arrives per line, staggered, sliding up out of a blur
- the headline holds only while it is being spoken
- a mock app window assembles on screen and its contents fill in as the
  voice describes them, so the claim and the proof land together
- the clip is cut to the voice, measured, never estimated

Every transition is driven by the narration's own timings, so nothing
outruns the speech and nothing lags behind it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920
FPS = 30

BG = (25, 11, 10)          # near black, warm
BG_LIFT = (34, 15, 12)
ACCENT = (228, 94, 95)     # the prototype's coral
WHITE = (255, 255, 255)
MUTED = (150, 138, 136)
PANEL = (38, 18, 16)
PANEL_EDGE = (66, 30, 27)

FONT_DIR = Path("C:/Windows/Fonts")


def log(m: str) -> None:
    print(f"[render] {m}", flush=True)


def font(size: int, bold: bool = False, spacing: int = 0):
    """A heavy grotesque, with letter spacing for the small caps lines."""
    names = (("seguibl.ttf", "arialbd.ttf") if bold
             else ("segoeui.ttf", "arial.ttf"))
    for name in names:
        p = FONT_DIR / name
        if p.exists():
            try:
                f = ImageFont.truetype(str(p), size)
                return f, spacing
            except OSError:
                pass
    try:
        return ImageFont.load_default(size), spacing
    except TypeError:
        return ImageFont.load_default(), spacing


def wrap(d: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=fnt) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def stage(t: float) -> Image.Image:
    """Background: near black, with two slow warm blooms behind the content."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)],
               fill=(int(BG[0] + 10 * k), int(BG[1] + 5 * k),
                     int(BG[2] + 4 * k)))
    return img


def glow(t: float) -> Image.Image:
    """Two out of focus warm blobs, drifting slowly."""
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = math.sin(t * 0.8) * 0.5 + 0.5
    b = math.cos(t * 0.6) * 0.5 + 0.5
    d.ellipse([int(-300 + a * 620), int(-200 + b * 460),
               int(520 + a * 620), int(560 + b * 460)], fill=(96, 32, 28))
    d.ellipse([int(500 + b * 560), int(1240 + a * 420),
               int(1380 + b * 560), int(2020 + a * 420)], fill=(46, 22, 34))
    layer = layer.filter(ImageFilter.GaussianBlur(230))
    return layer


def merge(img: Image.Image, layer: Image.Image, strength: int) -> Image.Image:
    return Image.composite(layer, img, Image.new("L", (W, H), strength))


def logo(d: ImageDraw.ImageDraw, cx: int, cy: int, s: int,
         a: float = 255) -> None:
    """The prototype's rounded red square, drawn rather than pasted."""
    pad = int(s * 0.16)
    d.rounded_rectangle([cx - s, cy - s, cx + s, cy + s + pad * 2],
                        radius=int(s * 0.42), fill=(*ACCENT, a))
    # the little notch inside the mark
    d.rounded_rectangle([cx - s * 0.32, cy - s * 0.24,
                         cx + s * 0.32, cy + s * 0.46],
                        radius=int(s * 0.12), fill=(*BG, a))


def kinetic(d: ImageDraw.ImageDraw, text: str, y: int, cx: int,
            width: int, size: int, appear: float, colour=WHITE,
            blur: bool = True) -> int:
    """Type that slides up out of a blur, per line, staggered.

    The stagger is what makes it read as motion design rather than a fade: by
    the time the third line lands the first is already readable, so the eye
    travels down instead of waiting.
    """
    fnt, _ = font(size, bold=True)
    lines = wrap(d, text, fnt, width)
    lh = int(size * 1.16)
    for i, ln in enumerate(lines):
        p = ease((appear - i * 0.13) / 0.5)
        if p <= 0:
            y += lh
            continue
        tw = d.textlength(ln, font=fnt)
        x = cx - tw / 2
        off = int((1 - p) * 46)

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((x, y + off), ln, font=fnt, fill=(*colour, int(255 * p)))
        if blur and p < 0.995:
            layer = layer.filter(ImageFilter.GaussianBlur((1 - p) * 9))
        d._image.alpha_composite(layer)
        y += lh
    return y


def tracked(d: ImageDraw.ImageDraw, xy, text: str, fnt, fill, track: int,
            anchor_center: bool = True):
    """Letter-spaced small caps, the way the prototype sets its labels."""
    widths = [d.textlength(c, font=fnt) for c in text]
    total = sum(widths) + track * max(0, len(text) - 1)
    x, y = xy
    if anchor_center:
        x = xy[0] - total / 2
    for c, w in zip(text, widths):
        d.text((x, y), c, font=fnt, fill=fill)
        x += w + track


def mock_window(img: Image.Image, reveal: float, lines_seen: int,
                features: list[str], shift: float = 0.0) -> Image.Image:
    """An app window that assembles, then fills in as the voice describes it.

    This is the argument the words cannot make on their own: a name and a
    feature list is a claim, a window with those features in it is proof.
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    cw, ch = int(W * 0.80), 560
    cx = (W - cw) // 2
    cy = 900 - int(shift)

    a = ease(reveal / 0.5)
    if a > 0:
        sc = 0.94 + 0.06 * a
        nw, nh = int(cw * sc), int(ch * sc)
        nx = (W - nw) // 2
        d.rounded_rectangle([nx, cy + (ch - nh) // 2, nx + nw,
                             cy + (ch - nh) // 2 + nh],
                            radius=34, fill=(*PANEL, int(246 * a)),
                            outline=(*PANEL_EDGE, int(255 * a)), width=2)

        # title bar
        bar_h = 74
        bar_y = cy + (ch - nh) // 2
        d.rounded_rectangle([nx, bar_y, nx + nw, bar_y + bar_h],
                            radius=34, fill=(*BG_LIFT, int(255 * a)))
        d.rectangle([nx, bar_y + bar_h - 34, nx + nw, bar_y + bar_h],
                    fill=(*BG_LIFT, int(255 * a)))
        for i, c in enumerate(((228, 94, 95), (196, 150, 70), (110, 170, 120))):
            r = 9
            cxp = nx + 34 + i * 30
            d.ellipse([cxp - r, bar_y + bar_h / 2 - r,
                       cxp + r, bar_y + bar_h / 2 + r],
                      fill=(*c, int(255 * a)))

        # a title and a search field, the shape of a real window
        tf, _ = font(30, bold=True)
        d.text((nx + 42, bar_y + bar_h + 34), "Library",
               font=tf, fill=(*WHITE, int(255 * a)))
        sf, _ = font(22)
        sby = bar_y + bar_h + 92
        d.rounded_rectangle([nx + 42, sby, nx + nw - 42, sby + 56],
                            radius=28, fill=(*BG, int(230 * a)),
                            outline=(*PANEL_EDGE, int(255 * a)), width=2)
        d.text((nx + 68, sby + 15), "Search your vault", font=sf,
               fill=(*MUTED, int(230 * a)))

        # rows appear one at a time, in step with the voice
        ry = sby + 92
        rf, _ = font(26, bold=True)
        for i, feat in enumerate(features):
            p = ease((reveal - 0.3 - i * 0.17) / 0.4)
            if p <= 0:
                ry += 78
                continue
            off = int((1 - p) * 30)
            d.rounded_rectangle([nx + 42, ry + off, nx + nw - 42,
                                 ry + 62 + off],
                                radius=22, fill=(*BG, int(236 * p)))
            d.rounded_rectangle([nx + 62, ry + 18 + off, nx + 78,
                                 ry + 44 + off],
                                radius=6, fill=(*ACCENT, int(255 * p)))
            d.text((nx + 98, ry + 18 + off), feat, font=rf,
                   fill=(*WHITE, int(255 * p)))
            ry += 78

    img.alpha_composite(layer) if img.mode == "RGBA" else None
    return img


def caption(d: ImageDraw.ImageDraw, words: list[dict], now: float) -> None:
    """The words being spoken, in a fixed band near the bottom."""
    live = [w for w in words if w["start"] <= now <= w["end"]]
    text = " ".join(w["t"] for w in live).strip()
    if not text:
        return
    fnt, _ = font(58, bold=True)
    lines = wrap(d, text, fnt, W - 300)
    lh = 82
    top = int(H * 0.855)
    y = top - len(lines) * lh
    for ln in lines:
        tw = d.textlength(ln, font=fnt)
        x = (W - tw) / 2
        asc, desc = fnt.getmetrics()
        d.rounded_rectangle([x - 32, y - 12, x + tw + 32, y + asc + desc + 8],
                            radius=(asc + desc + 20) // 2,
                            fill=(255, 255, 255, 236))
        d.text((x, y), ln, font=fnt, fill=BG)
        y += lh


def progress(img: Image.Image, done: float) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, H - 8, W, H], fill=(*MUTED, 60))
    d.rectangle([0, H - 8, int(W * max(0.0, min(1.0, done))), H],
                fill=(*ACCENT, 235))


def main() -> int:
    script = json.loads((ROOT / "data" / "shorts_script.json")
                        .read_text(encoding="utf-8"))
    voice = json.loads((ROOT / "data" / "shorts_voice.json")
                       .read_text(encoding="utf-8"))

    out = ROOT / "data" / "shorts_frames"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()

    parts = voice["parts"]
    gap = float(voice.get("gap") or 0.22)

    # measured narration, never the word-count estimate
    total = float(voice.get("seconds") or script.get("seconds") or 30)
    if not (3 < total < 180):
        total = 30.0
    n = int(round(total * FPS))

    name = str(script.get("name") or "Slingshot Tool")
    price = str(script.get("price") or "")

    # what the mock window shows: real labels for what the product does, so the
    # window shows product and not a copy of the narration
    beats = script.get("beats") or {}
    feats: list[str] = []
    for b in (beats.get("beats") or []):
        t = str(b).strip().rstrip(".")
        t = t.split(",")[0].split(" and ")[0]
        t = " ".join(t.split()[:5]).strip()
        if len(t) > 3 and t.lower() not in feats:
            feats.append(t)
    for fallback in ("Encrypted storage", "One master key",
                     "Works fully offline", "Search and filter"):
        if len(feats) >= 4:
            break
        feats.append(fallback)
    feats = feats[:4]

    words = []
    for p in parts:
        base = float(p.get("start") or 0.0)
        dur = float(p.get("seconds") or 0.0)
        marks = p.get("offset") or []
        if not marks:
            continue
        span = marks[-1]["offset"] or 0.001
        for j, m in enumerate(marks):
            s = base + (m["offset"] / span) * dur
            e = base + ((marks[j + 1]["offset"] / span) * dur
                        if j + 1 < len(marks) else dur)
            words.append({"t": m["text"], "start": s,
                          "end": max(e, s + 0.24)})
    if not words:
        raise SystemExit("[render] no caption timings")

    log(f"{n} frames at {W}x{H}, {total:.1f}s, {len(words)} captioned words")

    # scene bounds from the measured clips
    bounds, at = [], 0.0
    for p in parts:
        d = float(p.get("seconds") or 0.0)
        bounds.append((at, at + max(d, 0.4)))
        at += max(d, 0.4) + gap
    nlines = len(parts)

    for i in range(n):
        t = i / FPS
        which, local = 0, 0.0
        for idx, (b0, b1) in enumerate(bounds):
            if t >= b0:
                which, local = idx, (t - b0) / max(1e-6, b1 - b0)

        k = t / max(total, 1e-6)
        img = stage(k)
        img = merge(img, glow(k), 92)

        img = img.convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")

        # the mark sits above everything, as in the prototype
        logo(d, W // 2, 250, 34, int(255 * min(1.0, t / 0.4)))
        lf, _ = font(40, bold=True)
        tracked(d, (W // 2, 310), "SLINGSHOT", lf, (*WHITE, 236), 5)
        sf, _ = font(22)
        tracked(d, (W // 2, 358), "TOOLS", sf, (*ACCENT, 236), 7)

        last = which == nlines - 1
        # the closing card replaces the headline rather than stacking on it
        closing = last and local > 0.74
        # price: only in the last line's scene, and always below wherever
        # the headline actually ended, so three lines never run into it
        show_price = last and 0.18 < local <= 0.74 and bool(price)

        if not closing:
            # the headline, staggered, cut to the line being spoken
            appear = ease_in(min(1.0, max(0.0, local / 0.18)))
            end_y = kinetic(d, parts[which]["text"], 500, W // 2,
                            W - 200, 84, appear, WHITE)
        else:
            end_y = 760

        if show_price:
            pf, _ = font(60, bold=True)
            a = ease((local - 0.18) / 0.22)
            lines = wrap(d, price, pf, W - 320)
            lh = 96
            y = max(end_y + 36, 900)
            for ln in lines:
                tw = d.textlength(ln, font=pf)
                x = W / 2 - tw / 2
                d.rounded_rectangle([x - 36, y - 14, x + tw + 36, y + 90],
                                    radius=42, fill=(*ACCENT, int(244 * a)))
                d.text((x, y), ln, font=pf, fill=(*BG, int(255 * a)))
                y += lh

        # the window carries the middle of the video; it steps aside for the
        # price rather than fighting it for the same space
        if (which >= 1 or closing) and not show_price:
            rev = min(1.0, 0.25 + local * 0.5 + (which - 1) * 0.22)
            img = mock_window(img, rev, which, feats, 0)

        # the closing card takes the headline's slot, nothing else on screen
        if closing:
            a = ease((local - 0.74) / 0.16)
            kinetic(d, f"Get {name}", 470, W // 2, W - 200, 76, a, WHITE)
            uf, _ = font(30, bold=True)
            tracked(d, (W // 2, 1520), "slingshot-security.itch.io",
                    uf, (*ACCENT, int(255 * a)), 2)
            nf, _ = font(24)
            tracked(d, (W // 2, 1580), "Windows, Mac and Linux",
                    nf, (*MUTED, int(255 * a)), 3)

        caption(d, words, t)
        progress(img, k)

        img.convert("RGB").save(out / f"{i:05d}.jpg", quality=90)

        if i % 150 == 0:
            log(f"  frame {i}/{n}")

    (ROOT / "data" / "shorts_frames.json").write_text(
        json.dumps({"frames": n, "fps": FPS, "seconds": total}, indent=2),
        encoding="utf-8")
    log(f"done -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())