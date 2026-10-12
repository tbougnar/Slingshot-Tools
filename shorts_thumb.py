"""Make a thumbnail for the Short.

A Short's first frame is what a viewer sees in the feed before deciding to
watch, so it cannot be a random moment from the middle of the narration. It is
composed instead: the app's real interface, the hook in large type, and the
price, with nothing competing for attention.

    python shorts_thumb.py            build it
    python shorts_thumb.py --show     print where it went
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

import shorts_render as sr

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920


def log(m: str) -> None:
    print(f"[thumb] {m}", flush=True)


def font(size: int, bold: bool = True):
    for name in (("seguibl.ttf", "arialbd.ttf") if bold
                 else ("segoeui.ttf", "arial.ttf")):
        p = sr.FONT_DIR / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                pass
    return ImageFont.load_default(size)


def wrap(d, text, fnt, width):
    out, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=fnt) <= width or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def build(script: dict, shot: Image.Image | None) -> Image.Image:
    img = Image.new("RGB", (W, H), sr.BG)
    d = ImageDraw.Draw(img)

    # warm wash, so it is not a flat black rectangle in a grid of thumbnails
    wash = sr.merge(img, sr.glow(0.4), 150).convert("RGB")
    img = wash

    hook = script.get("beats", {}).get("hook") or "Never lose a password again"
    price = str(script.get("price") or "")
    name = str(script.get("name") or "Slingshot Tool")

    # the app, cropped to fill the lower half of the card. Both numbers are
    # derived once so the hook, the price and the card cannot disagree.
    card_top = int(H * 0.46)
    footer_h = 130
    card_h = H - card_top - footer_h

    if shot is not None:
        target_h = card_h
        ratio = max(W / shot.width, target_h / shot.height)
        tw, th = int(shot.width * ratio) + 1, int(shot.height * ratio) + 1
        t = shot.resize((tw, th), Image.LANCZOS)
        left = max(0, (tw - W) // 2)
        topc = max(0, int((th - target_h) * 0.08))
        t = t.crop((left, topc, left + W, topc + target_h))
        if t.size != (W, target_h):
            t = t.resize((W, target_h), Image.LANCZOS)

        # the mask must be the size of the thing being pasted, not the frame;
        # a mismatch here is a ValueError at the worst possible moment
        mask = Image.new("L", (W, target_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, W - 1, target_h - 1], radius=40, fill=255)

        card = Image.new("RGB", (W, target_h), sr.PANEL)
        card.paste(t, (0, 0), mask)
        img.paste(card, (0, card_top))

        # the brand mark across the seam, so the card reads as ours
        p = ROOT / "site" / "icon-512.png"
        if p.exists():
            try:
                mark = Image.open(p).convert("RGBA")
                side = int(W * 0.10)
                mark = mark.resize((side, side), Image.LANCZOS)
                img.paste(mark, (64, card_top - side // 2), mark)
            except Exception:  # noqa: BLE001
                pass

    # the hook first, so the price can be placed clear of however many lines
    # it takes. Measuring before drawing is the only way to stop the badge
    # landing on the last line of the headline.
    d = ImageDraw.Draw(img)
    fnt = font(112)
    lines = wrap(d, hook, fnt, W - 160)[:3]
    lh = 132
    y = 250
    for ln in lines:
        tw = d.textlength(ln, font=fnt)
        x = (W - tw) / 2
        for dx, dy in ((5, 6), (-5, 6), (5, -6), (-5, -6)):
            d.text((x + dx, y + dy), ln, font=fnt, fill=(18, 8, 7))
        d.text((x, y), ln, font=fnt, fill=(255, 252, 248))
        y += lh
    hook_end = y

    # the price, below the headline with a real gap. Measuring before
    # drawing is the only way to stop the badge landing on the type, and the
    # badge height follows the font so stacked lines cannot overlap.
    if price:
        def badge(font_size: int) -> tuple[list[str], int]:
            pf = font(font_size)
            step = int(font_size * 1.34)
            return wrap(d, price, pf, W - 340)[:2], step

        plines, step = badge(68)
        py = hook_end + 44
        if py + len(plines) * step > card_top - 30:
            # shrink rather than overlap; a clipped badge is unreadable
            plines, step = badge(56)
            py = min(py, card_top - len(plines) * step - 30)
        for ln in plines:
            pf = font(56 if step < 92 else 68)
            tw = d.textlength(ln, font=pf)
            x = (W - tw) / 2
            d.rounded_rectangle([x - 42, py, x + tw + 42, py + step],
                                radius=step // 2, fill=sr.ACCENT)
            d.text((x, py + (step - pf.size) // 2 - pf.size // 10),
                   ln, font=pf, fill=sr.BG)
            py += step

    nf = font(44)
    tw = d.textlength(name, font=nf)
    d.text(((W - tw) / 2, H - footer_h + 34), name, font=nf,
           fill=(230, 226, 220))

    # a touch more contrast, because a thumbnail is judged at postage size
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.1)
    return img


def main() -> int:
    spath = ROOT / "data" / "shorts_script.json"
    if not spath.exists():
        raise SystemExit("[thumb] run shorts_script.py first")
    script = json.loads(spath.read_text(encoding="utf-8"))

    shot = sr._shot_for(str(script.get("slug") or ""), "light") \
        or sr._shot_for(str(script.get("slug") or ""))

    img = build(script, shot)
    out_dir = ROOT / "dist" / "shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{script.get('slug', 'short')}-thumb.jpg"
    img.save(dest, quality=94)
    log(f"{dest.name}  {dest.stat().st_size / 1024:.0f} KB")
    (ROOT / "data" / "shorts_thumb.json").write_text(
        json.dumps({"file": str(dest), "slug": script.get("slug")}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())