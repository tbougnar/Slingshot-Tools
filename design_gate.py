"""The design gate: an app has to look like something worth paying for.

Everything else in this repository asks whether the app *works*. That is the
wrong question on its own: the shipped password manager opened, saved, and
exported correctly, and still looked like a form someone filled in in ten
minutes - a full-width red slab for a title, bare label/value rows on a plain
card, browser-default buttons. It was sold for $3.00.

Two checks, both required:

  lint()     the measurable half. No model, no cost, always runs: design
             tokens, a responsive breakpoint, hover and focus states, a
             spacing scale, rounded surfaces, a type scale that is not a
             poster. These are the things a premium app always has and a
             throwaway page never does.

  review()   the judgement half. Screenshot the real page in a real browser
             and ask a vision model to score it against a rubric and name what
             is wrong. A model that cannot see, a missing browser or a dead
             key makes this unavailable rather than failing the app: lint is
             the floor, the review is the raise.

Callers use check(), which returns the problems to fix. An empty list means
the app may ship.

    python design_gate.py app/index.html
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Below this the review says "not good enough to charge for". Six, not nine:
# the reviewer is asked to be specific, and a score is only useful if a solid
# but unremarkable app can clear it while an ugly one cannot.
PASS_SCORE = 6.0

# A heading this big is a poster, not an interface. The rejected password
# manager put its title in a slab across the whole window.
MAX_FONT_PX = 60.0

# Below this much CSS there is no design system in the file, only rules that
# were needed to make the controls stop overlapping.
MIN_CSS_CHARS = 900


def log(msg: str) -> None:
    print(f"[design] {msg}", flush=True)


def style_of(html: str) -> str:
    """Every <style> block on the page, lower-cased for matching."""
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", html,
                        re.S | re.I)
    return "\n".join(blocks).lower()


def lint(html: str) -> list[str]:
    """The measurable half of the gate: what a premium app always has."""
    css = style_of(html)
    low = html.lower()
    problems: list[str] = []

    if not css:
        return ["there is no <style> block at all, so the page is unstyled"]

    checks = [
        (r"--[\w-]+\s*:", "no design tokens: CSS custom properties define "
                          "the palette and spacing, without them every value "
                          "is a one-off"),
        (r"@media", "not responsive: no @media breakpoint, so the layout "
                    "cannot adapt to a phone"),
        (r":hover", "no hover state: nothing tells the user what is clickable"),
        (r":focus", "no focus state: keyboard users cannot see where they are"),
        (r"(transition|animation)", "no motion at all: state changes jump "
                                    "instead of moving"),
        (r"box-shadow", "no depth: flat rectangles with no shadow or "
                        "elevation read as unstyled"),
        (r"border-radius", "no rounded corners: every surface is a hard "
                           "rectangle"),
        (r"display\s*:\s*(grid|flex)", "no grid or flex layout: the page is "
                                       "stacked block by block"),
        (r"\bgap\s*:", "no spacing scale: elements are positioned by "
                       "coincidence rather than a rhythm"),
        (r"font-family\s*:", "the browser's default font: no typeface is "
                             "chosen anywhere"),
        (r"max-width\s*:", "content runs the full window width: nothing "
                           "constrains the reading line"),
        (r"data-theme", "no light/dark switch: the theme cannot be changed "
                        "or remembered"),
    ]
    for pattern, why in checks:
        if not re.search(pattern, css):
            problems.append(why)

    for m in re.finditer(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", css):
        if float(m.group(1)) >= MAX_FONT_PX:
            problems.append(
                f"poster-sized text: font-size {m.group(1)}px is display "
                f"lettering, not interface type (limit {MAX_FONT_PX:g}px)")
            break

    if len(css.strip()) < MIN_CSS_CHARS:
        problems.append(
            f"only {len(css.strip())} characters of CSS: a paid app needs a "
            f"real design system, not {MIN_CSS_CHARS} bytes of duct tape")

    # A heading that fills the window is the single most recognisable thing
    # about the app that was rejected, so it is checked directly rather than
    # left to the reviewer's taste.
    if re.search(r"<h1[^>]*>[^<]{0,80}</h1>", low) and \
            re.search(r"(padding\s*:\s*[3-9]\dpx|padding\s*:\s*\d{3,}px)", css):
        problems.append("the title sits in a huge padded block: a heading "
                        "should be a line of type, not a banner")
    return problems


# ------------------------------------------------------------------ the eye

REVIEW_SYSTEM = """You are a strict product designer reviewing a screenshot \
of a single-file desktop tool that is sold for $3.00.

Judge only what you can see. Be specific and practical: every issue you name \
must be something the developer can change in CSS or markup.

Score 0-10 for the whole picture:
 9-10  a paid product: clear hierarchy, confident type, consistent spacing,
       surfaces that look designed, nothing embarrassing
 7-8   solid and shippable, minor rough edges
 5-6   looks like a quick internal prototype
 3-4   bare, default-looking, or visually confused
 0-2   broken layout or unreadable

Reject these specifically: a giant coloured slab as the title, headings that \
are poster-sized, labels with no input styling, browser-default buttons, \
elements crammed together, empty space that is not deliberate, low contrast, \
misaligned columns, a light theme that is just white with no system.

Reply with JSON only, exactly:
{"score": <number 0-10>, "issues": ["<specific, fixable problem>", "..."]}
No prose outside the JSON."""

REVIEW_USER = """Here is a screenshot of the app, photographed in a real \
browser at 900x1200.

Score it and list every concrete thing that makes it look cheap or hard to \
use. Do not praise it. If it is already good, say what still separates it \
from a paid product."""


def _json_object(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return got if isinstance(got, dict) else None


def screenshot(html: str, slug: str = "app") -> bytes | None:
    """Photograph the real page. None means "no picture, no review"."""
    import shots

    exe = shots.browser()
    if not exe:
        log("no headless browser, so the screenshot review is skipped")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "index.html"
        dest = Path(tmp) / "shot.png"
        page.write_text(html, encoding="utf-8")
        if not shots.shoot(exe, page, dest):
            log("the screenshot failed, so the review is skipped")
            return None
        try:
            return dest.read_bytes()
        except OSError as e:
            log(f"the screenshot could not be read: {e}")
            return None


def review(html: str, slug: str = "app") -> tuple[float | None, list[str], str]:
    """Score the screenshot. ``(None, [], why)`` means "could not review"."""
    import providers

    if not providers.configured():
        return None, [], "no model provider configured"
    png = screenshot(html, slug)
    if not png:
        return None, [], "no screenshot"
    last = ""
    for model in providers.model_chain("vision"):
        try:
            raw = providers.vision(model, REVIEW_SYSTEM, REVIEW_USER, png,
                                   role="vision")
        except Exception as e:  # noqa: BLE001
            last = str(e)[:120]
            continue
        got = _json_object(raw)
        if not got:
            last = f"{model} returned no JSON"
            continue
        try:
            score = float(got.get("score"))
        except (TypeError, ValueError):
            last = f"{model} returned no score"
            continue
        issues = [str(x)[:200] for x in (got.get("issues") or [])
                  if isinstance(x, str)][:8]
        score = max(0.0, min(10.0, score))
        log(f"review by {model}: {score:.1f}/10, {len(issues)} issue(s)")
        return score, issues, model
    return None, [], last or "no vision model answered"


def check(html: str, slug: str = "app", want_review: bool = True) -> list[str]:
    """Everything that must be fixed before this app can be sold."""
    problems = lint(html)
    if problems:
        # The measurable half already failed, so the screenshot would only
        # repeat it. One call is enough to know the app is not ready.
        return problems
    if not want_review:
        return []
    score, issues, note = review(html, slug)
    if score is None:
        log(f"design review unavailable ({note}); the static rules passed, "
            "so this is a warning and not a refusal")
        return []
    if score < PASS_SCORE:
        head = [f"the screenshot scores {score:.1f}/10, below the "
                f"{PASS_SCORE:g} needed to charge for it"]
        return head + issues
    return []


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python design_gate.py <index.html>")
        return 2
    path = Path(sys.argv[1])
    html = path.read_text(encoding="utf-8", errors="replace")
    problems = lint(html)
    print(f"\nSTATIC DESIGN RULES ({path.name})")
    for p in problems:
        print(f"  FAIL  {p}")
    if not problems:
        print("  ok    every measurable rule passed")
    score, issues, note = review(html, path.stem)
    if score is None:
        print(f"\nSCREENSHOT REVIEW: unavailable ({note})")
    else:
        print(f"\nSCREENSHOT REVIEW: {score:.1f}/10")
        for i in issues:
            print(f"  - {i}")
    if problems or (score is not None and score < PASS_SCORE):
        print("\nVERDICT: not good enough to publish")
        return 1
    print("\nVERDICT: ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
