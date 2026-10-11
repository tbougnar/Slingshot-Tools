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
    """The brand mark, taken from the file rather than drawn.

    It was drawn by hand from a description and came out a red square with a
    notch, which is not the logo. Reading icon.png keeps the video honest
    about what the brand looks like, and costs one cached image.
    """
    cached = _LOGO
    if cached is not None:
        size = s * 2
        if cached.size != (size, size):
            cached = cached.resize((size, size), Image.LANCZOS)
        if a >= 255:
            img = d._image
            img.alpha_composite(cached, (int(cx - s), int(cy - s)))
            return
        faded = cached.copy()
        faded.putalpha(faded.getchannel("A").point(
            lambda v: int(v * a / 255)))
        d._image.alpha_composite(faded, (int(cx - s), int(cy - s)))
        return

    # no logo file, so draw something rather than nothing
    d.rounded_rectangle([cx - s, cy - s, cx + s, cy + s + s * 0.2],
                        radius=int(s * 0.4), fill=(*ACCENT, int(a)))


_LOGO: Image.Image | None = None


def _load_logo() -> None:
    """Read the brand mark once, if the repo has one."""
    global _LOGO
    if _LOGO is not None:
        return
    for rel in ("site/icon-512.png", "site/logo.png"):
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            im = Image.open(p).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        # the file is a rounded square on transparent, so a wide crop keeps
        # only the mark itself
        side = min(im.size)
        im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                      (im.width - side) // 2 + side,
                      (im.height - side) // 2 + side))
        _LOGO = im
        return


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


def _shot_for(slug: str, theme: str = "base") -> Image.Image | None:
    """A screenshot of the real app, if shots.py managed to take one."""
    key = f"{slug}|{theme}"
    if key in _SHOT_CACHE:
        return _SHOT_CACHE[key]

    img = None
    index = ROOT / "data" / "shots.json"
    if index.exists():
        try:
            made = json.loads(index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            made = {}

        entry = made.get(slug)
        if not isinstance(entry, dict):
            entry = None
            for k, v in made.items():
                if k.startswith(slug[:12]):
                    entry = v
                    break

        rel = ""
        if isinstance(entry, dict):
            # fall back through the themes, then to whatever exists
            for want in (theme, "base", "light", "dark"):
                if entry.get(want):
                    rel = entry[want]
                    break
        elif isinstance(entry, str):
            rel = entry

        if rel:
            p = ROOT / rel
            if p.exists():
                try:
                    img = Image.open(p).convert("RGB")
                except Exception:  # noqa: BLE001
                    img = None
    _SHOT_CACHE[key] = img
    return img


_SHOT_CACHE: dict = {}

THEME_WORDS = ("theme", "light", "dark", "colour", "color")


def wants_theme(text: str) -> bool:
    """Is this the line about light and dark?

    When it is, the preview switches to match what is being said. A video that
    says it and then shows the other one is worse than not saying it at all.
    """
    low = text.lower()
    return any(w in low for w in THEME_WORDS)


def app_window(img: Image.Image, slug: str, reveal: float,
               features: list[str], top: int, small: bool = False,
               theme: str = "base") -> Image.Image:
    """The real interface, inside a window frame.

    The screenshot is what the app genuinely looks like: its own colours, its
    own layout, its own controls. Only the window chrome around it is ours,
    and that is there to say "this is a desktop app" rather than a web page.

    Falls back to a drawn stand-in when there is no screenshot, so a missing
    browser never stops a video.
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    a = ease(reveal / 0.45)
    if a <= 0:
        return img

    # the frame is taller than the content now that the caption band is gone,
    # so the window is given the room it would have shared with captions
    # as large as the frame allows, so the app is the subject rather than a
    # detail. At the old width it read as a thumbnail on a phone.
    cw = int(W * 0.92)
    bottom = H - 70 if small else BAND_WINDOW[1]
    ch = max(420, min(bottom - top, int((bottom - top)
                                        * (0.72 if small else 1.0))))
    cx = (W - cw) // 2

    sc = 0.95 + 0.05 * a
    nw, nh = int(cw * sc), int(ch * sc)
    nx, ny = (W - nw) // 2, top + (ch - nh) // 2

    # the window itself, with a soft drop shadow beneath
    d.rounded_rectangle([nx + 6, ny + 12, nx + nw + 6, ny + nh + 12],
                        radius=34, fill=(0, 0, 0, 120))
    d.rounded_rectangle([nx, ny, nx + nw, ny + nh], radius=34,
                        fill=(20, 20, 22, int(255 * a)),
                        outline=(*PANEL_EDGE, int(255 * a)), width=2)

    bar = 66
    d.rounded_rectangle([nx, ny, nx + nw, ny + bar], radius=34,
                        fill=(30, 30, 33, int(255 * a)))
    d.rectangle([nx, ny + bar - 34, nx + nw, ny + bar],
                fill=(30, 30, 33, int(255 * a)))
    for i, c in enumerate(((228, 94, 95), (196, 160, 80), (110, 175, 125))):
        r = 9
        cxp = nx + 30 + i * 28
        d.ellipse([cxp - r, ny + bar / 2 - r, cxp + r, ny + bar / 2 + r],
                  fill=(*c, int(255 * a)))

    inner_x, inner_y = nx + 14, ny + bar + 10
    inner_w, inner_h = nw - 28, nh - bar - 24

    shot = _shot_for(slug, theme)
    if shot is not None:
        # cover the content area rather than letterboxing it: a screenshot
        # shrunk to fit leaves grey bars, and a screenshot cropped to fill
        # shows the app at full size, which is the whole point
        ratio = max(inner_w / shot.width, inner_h / shot.height)
        tw, th = int(shot.width * ratio) + 1, int(shot.height * ratio) + 1
        thumb = shot.resize((tw, th), Image.LANCZOS)
        # crop the overflow from the top, keeping the header and the form,
        # which is the part worth showing
        left = max(0, (tw - inner_w) // 2)
        topc = max(0, int((th - inner_h) * 0.06))
        thumb = thumb.crop((left, topc, left + inner_w, topc + inner_h))
        if a < 0.995:
            thumb = thumb.convert("RGBA")
            thumb.putalpha(thumb.getchannel("A").point(
                lambda v: int(v * a)))
        mask = Image.new("L", thumb.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, thumb.width,
                                               thumb.height], radius=14,
                                               fill=int(255 * a))
        layer.paste(thumb, (inner_x, inner_y), mask)
    else:
        # no screenshot: a stand-in that at least names the real controls
        d.rounded_rectangle([inner_x, inner_y, inner_x + inner_w,
                             inner_y + inner_h], radius=18,
                            fill=(24, 24, 26, int(255 * a)))
        sf, _ = font(26, bold=True)
        d.text((inner_x + 30, inner_y + 24), features[0] if features
               else "App", font=sf, fill=(*WHITE, int(230 * a)))

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
BAND_LOGO = (180, 360)
BAND_HEAD = (400, 820)
BAND_PRICE = (850, 1080)
BAND_WINDOW = (1110, 1860)
BAND_URL = (1130, 1300)


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

    log(f"{n} frames at {W}x{H}, {total:.1f}s, {len(words)} spoken lines")

    # the brand mark is read from the repo once, not drawn from memory
    _load_logo()
    if _LOGO is None:
        log("no logo file found, so a plain mark will be drawn instead")

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
        # A long headline and the window cannot both have the middle of the
        # frame, so the window yields. Half a window hidden behind a headline
        # looks broken; a headline alone looks deliberate. Two lines still fit
        # above the window, three do not.
        long_head = len(wrap(d, parts[which]["text"], font(86)[0],
                             W - 200)) >= 3
        has_shot = bool(_shot_for(str(script.get("slug") or "")))
        # the theme follows the words: when the line is the one about light and
        # dark, the preview switches to show it, then goes back afterwards so
        # the rest of the video is consistent
        theme = "base"
        if wants_theme(parts[which]["text"]):
            theme = "light"
        if not closing and not show_price and has_shot and which >= 1:
            rev = min(1.0, 0.25 + local * 0.55)
            # a three line headline fills its band, so the window drops below
            # it rather than leaving the bottom half of the frame empty
            img = app_window(img, str(script.get("slug") or ""), rev,
                             feats,
                             BAND_HEAD[1] + 60 if long_head
                             else BAND_WINDOW[0],
                             small=long_head, theme=theme)

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