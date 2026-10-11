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
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

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

    # the app, tilted very slightly and cropped to fill the lower half
    if shot is not None:
        target_h = int(H * 0.52)
        ratio = max(W / shot.width, target_h / shot.height)
        tw, th = int(shot.width * ratio) + 1, int(shot.height * ratio) + 1
        t = shot.resize((tw, th), Image.LANCZOS)
        left = max(0, (tw - W) // 2)
        topc = max(0, int((th - target_h) * 0.08))
        t = t.crop((left, topc, left + W, topc + target_h))

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [70, int(H * 0.44), W - 70, int(H * 0.44) + target_h],
            radius=40, fill=255)
        img.paste(t, (0, int(H * 0.44)), mask)

        # a line of the brand across the seam, so the card reads as ours
        sr._LOGO and None
        p = ROOT / "site" / "icon-512.png"
        if p.exists():
            try:
                mark = Image.open(p).convert("RGBA")
                side = int(W * 0.11)
                mark = mark.resize((side, side), Image.LANCZOS)
                img.paste(mark, (70, int(H * 0.44) - side // 2), mark)
            except Exception:  # noqa: BLE001
                pass

    # the hook, large, at the top where the eye lands first
    d = ImageDraw.Draw(img)
    fnt = font(112)
    lines = wrap(d, hook, fnt, W - 160)
    y = 300
    for ln in lines[:3]:
        tw = d.textlength(ln, font=fnt)
        x = (W - tw) / 2
        # a shadow rather than a box: thick type needs separation, not a panel
        for dx, dy in ((5, 6), (-5, 6), (5, -6), (-5, -6)):
            d.text((x + dx, y + dy), ln, font=fnt, fill=(18, 8, 7))
        d.text((x, y), ln, font=fnt, fill=(255, 252, 248))
        y += 128

    # the price as a badge, because that is the reason to watch
    if price:
        pf = font(76)
        lines = wrap(d, price, pf, W - 300)
        py = int(H * 0.30)
        for ln in lines[:2]:
            tw = d.textlength(ln, font=pf)
            x = (W - tw) / 2
            d.rounded_rectangle([x - 44, py - 20, x + tw + 44, py + 104],
                                radius=52, fill=sr.ACCENT)
            d.text((x, py), ln, font=pf, fill=sr.BG)
            py += 104

    nf = font(40)
    tw = d.textlength(name, font=nf)
    d.text(((W - tw) / 2, H - 150), name, font=nf, fill=(230, 226, 220))

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