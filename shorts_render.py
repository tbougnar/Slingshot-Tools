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


def kinetic(d: ImageDraw.ImageDraw, text: str, band: tuple[int, int],
            cx: int, width: int, size: int, appear: float,
            colour=WHITE, blur: bool = True) -> int:
    """Type that slides up out of a blur, per line, staggered.

    The band is (top, bottom) and the block is centred inside it, so a three
    line headline is positioned the same way as a one line one. Shrinking the
    type when the text will not fit beats clipping it, because a cut-off line
    reads as a bug rather than as a style.
    """
    fnt, _ = font(size, bold=True)
    lh = int(size * 1.16)
    lines = wrap(d, text, fnt, width)
    while len(lines) * lh > (band[1] - band[0]) and size > 46:
        size = int(size * 0.9)
        fnt, _ = font(size, bold=True)
        lh = int(size * 1.16)
        lines = wrap(d, text, fnt, width)

    block = len(lines) * lh
    y = band[0] + (band[1] - band[0] - block) // 2

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
    """The words being spoken, in a fixed band near the bottom.

    The band is high enough to clear the URL on the closing card, which used
    to sit underneath it.
    """
    live = [w for w in words if w["start"] <= now <= w["end"]]
    text = " ".join(w["t"] for w in live).strip()
    if not text:
        return
    fnt, _ = font(56, bold=True)
    lines = wrap(d, text, fnt, W - 300)
    lh = 78
    top = BAND_CAPTION[1]
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


def _price_line(parts: list[dict], price: str) -> int:
    """Which spoken line the price card belongs beside.

    The narration no longer says the price, so there is no sentence to hang it
    on. It goes beside the proof, where the viewer has just been told what the
    thing does and is deciding whether they care.
    """
    n = len(parts)
    if n <= 1:
        return 0
    if n <= 3:
        return 1
    return min(2, n - 2)


# The frame is divided into bands and nothing is allowed to leave its own.
# Elements used to be placed at fixed y values, which collided the moment a
# headline ran to three lines: the price badge landed on the text, and the
# third line was cut off at the bottom of its band. Bands make a collision
# impossible by giving each element a slot it cannot grow out of.
BAND_LOGO = (220, 420)
BAND_HEAD = (470, 880)
BAND_PRICE = (900, 1160)
BAND_WINDOW = (1180, 1520)
BAND_URL = (1530, 1650)
BAND_CAPTION = (1660, 1800)


def icon_row(img: Image.Image, y: int, a: float) -> None:
    """A row of channel marks on the closing card.

    Drawn rather than pasted, because there is no asset library here and an
    SVG cannot survive the JPEG frame. Each mark is the same simple shape the
    website uses, so the two read as the same brand.
    """
    if a <= 0:
        return
    d = ImageDraw.Draw(img, "RGBA")
    import links

    marks = [c for c in links.all_links() if c["key"] in
             ("website", "itch", "youtube", "discord", "github")]
    n = len(marks)
    box, gap = 78, 26
    total = n * box + (n - 1) * gap
    x0 = (W - total) // 2

    for i, c in enumerate(marks):
        x = x0 + i * (box + gap)
        col = (*ACCENT, int(230 * a)) if c.get("primary") \
            else (*MUTED, int(210 * a))
        d.rounded_rectangle([x, y, x + box, y + box], radius=22,
                            outline=(*PANEL_EDGE, int(220 * a)), width=2)
        cx, cy = x + box / 2, y + box / 2
        if c["icon"] == "globe":
            d.ellipse([cx - 17, cy - 17, cx + 17, cy + 17], outline=col, width=3)
            d.ellipse([cx - 7, cy - 17, cx + 7, cy + 17], outline=col, width=2)
            d.line([cx - 17, cy, cx + 17, cy], fill=col, width=2)
        elif c["icon"] == "bag":
            d.rounded_rectangle([cx - 15, cy - 8, cx + 15, cy + 17],
                                radius=6, outline=col, width=3)
            d.arc([cx - 9, cy - 19, cx + 9, cy - 3], 180, 360, fill=col, width=3)
        elif c["icon"] == "play":
            d.polygon([(cx - 11, cy - 14), (cx + 14, cy), (cx - 11, cy + 14)],
                      outline=col, width=3)
        elif c["icon"] == "chat":
            d.rounded_rectangle([cx - 17, cy - 14, cx + 17, cy + 9],
                                radius=8, outline=col, width=3)
            d.polygon([(cx - 9, cy + 8), (cx - 1, cy + 8), (cx - 9, cy + 17)],
                      fill=col)
        else:  # code
            d.line([(cx - 14, cy - 12), (cx - 3, cy),
                    (cx - 14, cy + 12)], fill=col, width=3)
            d.line([(cx + 14, cy - 12), (cx + 3, cy),
                    (cx + 14, cy + 12)], fill=col, width=3)


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

    # what the mock window shows: real feature names for this kind of tool, so the
    # window shows a product and not a copy of the narration
    beats = script.get("beats") or {}
    feats: list[str] = []
    for b in (beats.get("beats") or []):
        t = str(b).strip().rstrip(".")
        t = t.split(",")[0].split(" and ")[0]
        t = " ".join(t.split()[:5]).strip()
        if len(t) > 3 and t.lower() not in feats:
            feats.append(t)
    for fb in ("Encrypted on your disk", "One master key",
               "Works fully offline", "Search and filter",
               "Never forgets a login"):
        if len(feats) >= 4:
            break
        if fb.lower() not in [f.lower() for f in feats]:
            feats.append(fb)
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

        last = which == nlines - 1
        # the closing card replaces the headline rather than stacking on it
        closing = last and local > 0.72

        # the brand arrives late, attached to the thing they now want.
        # Direct response research is consistent on this: opening with a logo
        # gives a scroller no reason to stay.
        if t > 1.0:
            ba = int(255 * ease((t - 1.0) / 0.5))
            logo(d, W // 2, BAND_LOGO[0] + 40, 30, ba)
            lf, _ = font(34, bold=True)
            tracked(d, (W // 2, BAND_LOGO[0] + 92), "SLINGSHOT", lf,
                    (*WHITE, ba), 5)
            sf, _ = font(20)
            tracked(d, (W // 2, BAND_LOGO[0] + 136), "TOOLS", sf,
                    (*ACCENT, ba), 7)

        # the price is shown, not spoken: a number the viewer reads stays, a
        # number the voice says is forgotten
        price_line = _price_line(parts, price)
        show_price = (which == price_line and 0.14 < local <= 0.88
                      and bool(price))
        if show_price:
            pf, _ = font(58, bold=True)
            a = ease((local - 0.14) / 0.2)
            plines = wrap(d, price, pf, W - 300)
            lh = 84
            block = len(plines) * lh + 60
            y = BAND_PRICE[0] + (BAND_PRICE[1] - BAND_PRICE[0] - block) // 2
            for ln in plines:
                tw = d.textlength(ln, font=pf)
                x = W / 2 - tw / 2
                d.rounded_rectangle([x - 38, y - 14, x + tw + 38, y + 84],
                                    radius=44, fill=(*ACCENT, int(246 * a)))
                d.text((x, y), ln, font=pf, fill=(*BG, int(255 * a)))
                y += lh
            nf, _ = font(24)
            tracked(d, (W // 2, y + 14), "one off, yours forever",
                    nf, (*MUTED, int(255 * a)), 2)

        if not closing:
            # the headline, staggered, cut to the line being spoken
            appear = ease_in(min(1.0, max(0.0, local / 0.18)))
            kinetic(d, parts[which]["text"], BAND_HEAD, W // 2, W - 200,
                    86, appear, WHITE)

        # the window carries the proof; it steps aside for the price card
        #
        # A long headline and the window cannot both have the middle of the
        # frame, so the window yields. Half a window hidden behind a headline
        # looks broken; a headline alone looks deliberate.
        long_head = len(wrap(d, parts[which]["text"], font(86)[0],
                             W - 200)) >= 2
        # the closing card owns the middle band outright, so the window is
        # gone before the call to action lands on top of it
        if ((which >= 1 and not closing) and not show_price
                and not long_head):
            rev = min(1.0, 0.25 + local * 0.5 + (which - 1) * 0.22)
            img = mock_window(img, rev, which, feats,
                              BAND_WINDOW[0] - 900)

        # the closing card takes the headline's slot, nothing else on screen
        if closing:
            a = ease((local - 0.72) / 0.16)
            kinetic(d, f"Get {name}", BAND_HEAD, W // 2, W - 200, 74, a, WHITE)
            icon_row(img, 1180, a)
            uf, _ = font(26, bold=True)
            tracked(d, (W // 2, BAND_URL[0]), "slingshot-security.itch.io",
                    uf, (*ACCENT, int(255 * a)), 2)
            nf, _ = font(22)
            tracked(d, (W // 2, BAND_URL[0] + 52), "Windows, Mac and Linux",
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