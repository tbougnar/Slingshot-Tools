"""Write the narration for a Short, from what the product actually is.

The script is generated from the published product record rather than written
by hand, so the claim in the video can never drift from what is sold. A Short
that quotes a price that has changed is worse than no Short.

The structure follows direct response practice for feed video, which is
stricter than it first looks:

  hook    the pain, in the viewer's own words, under three seconds
  problem the cost of living with it, one line
  proof   what the product actually does, shown rather than praised
  ask     one action

Three things the research is explicit about, and this script obeys:

- Do not open with the brand. Nobody scrolling knows or cares who you are, so
  the name comes late, attached to the thing they now want.
- Agitation gets cut. Targeting already selected people who feel the problem,
  and dwelling on misery reads as manipulative in a short slot.
- The price belongs on screen, not in the narration. Spoken numbers fight the
  voice for attention and are forgotten; a number the viewer reads stays.

Groq writes it because it is already a dependency and it is free.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import providers

ROOT = Path(__file__).resolve().parent

RULES = """Write narration for a vertical video advert for a desktop tool.

Pick a length mode and follow that structure exactly.

SHORT (about 20 seconds):
  hook    under 7 words. The pain, in the words a real person would use.
  problem one sentence. The cost of living with it today.
  proof   one sentence. What the tool does about it, plainly.
  ask     under 7 words. One action.

TOUR (about 60 seconds, a fuller walkthrough):
  hook     under 7 words. The pain, immediately.
  problem  one sentence. The cost of living with it.
  tour     a list of 6 to 8 strings, each under 12 words. One real capability
           per line. These must be things the tool actually does.
  proof    one sentence. The strongest thing it does, plainly.
  ask      under 8 words. One action.

Hard rules for both:
- Never say the brand or the product name in the narration. It appears on
  screen instead.
- Never say a price or a number aloud. Prices are shown, not spoken.
- Start mid thought. No greeting, no introducing, no build up.
- No marketing words: no revolutionary, seamless, game-changing, unlock,
  supercharge, effortless, robust, powerful, elevate.
- Short sentences, spoken aloud. No parentheses, no dashes, no markdown.
- Do not describe features the record does not support.
- Return JSON only, no prose around it."""


def log(m: str) -> None:
    print(f"[shorts] {m}", flush=True)


def price_label(raw) -> str:
    """A price a person would say, not the raw number from the product record.

    The record holds 3.0 because it is used for arithmetic. Spoken aloud that
    becomes "three point oh", which is exactly the sort of detail that makes a
    video feel machine made, so it is formatted once and used everywhere.
    """
    if raw is None or raw == "":
        return "free"
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v <= 0:
            return "free"
        dollars = f"${v:.0f}" if abs(v - round(v)) < 0.005 else f"${v:.2f}"
        return f"{dollars} for the lifetime licence" \
            if v < 100 else f"{dollars}"
    return str(raw)


def product() -> dict:
    """The product as published, so the video cannot invent features."""
    stage = ROOT / "data" / "published.json"
    if not stage.exists():
        raise SystemExit("[shorts] no product record; nothing to advertise")
    return json.loads(stage.read_text(encoding="utf-8"))


def real_features(slug: str, limit: int = 10) -> list[str]:
    """What the app actually does, read from the app itself.

    A tour mode needs a minute of material and the product record holds three
    fields, so asking the model to fill 60 seconds from a blurb makes it
    invent features. The app's own interface is the one place the real
    capabilities are written down, so that is what gets read.

    Three sources, in order of how much they can be trusted: the catalog's
    difference list, the app's feature markup, then anything the page labels.
    """
    root = ROOT / "site" / "apps"
    if not root.exists():
        return []

    dirs = [d for d in sorted(root.iterdir())
            if d.is_dir() and slug.startswith(d.name[:len(slug)])] \
        or [d for d in sorted(root.iterdir()) if d.is_dir()]
    if not dirs:
        return []

    app = dirs[0]
    out: list[str] = []

    # control names that describe chrome rather than capability. Kept out because
    # "Delete" and "Toggle Theme" are not things to advertise.
    CHROME = {"delete", "cancel", "close", "menu", "toggle theme",
              "toggle dark mode", "theme", "close dialog", "open",
              "edit", "save", "back", "next", "settings", "help", "about"}

    def add(text: str) -> None:
        t = " ".join(str(text).split()).strip(" .—-*")
        if len(t) < 4 or len(t) > 68:
            return
        if t.lower() in CHROME:
            return
        if t.lower() not in [x.lower() for x in out]:
            out.append(t)

    # the catalog's own difference list, which is curated
    try:
        cat = json.loads((ROOT / "site" / "apps.json").read_text(
            encoding="utf-8"))
        for a in (cat if isinstance(cat, list) else cat.get("apps", [])):
            if a.get("base_slug") == slug or a.get("slug") == slug:
                for d in (a.get("differences") or []):
                    add(d if isinstance(d, str) else d.get("text", ""))
    except (json.JSONDecodeError, OSError):
        pass

    page = app / "index.html"
    if page.exists() and len(out) < limit:
        html = page.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.S | re.I):
            add(re.sub(r"<[^>]+>", " ", m.group(1)))
            if len(out) >= limit:
                break

    # the app's own controls are the one place its capabilities are written
    if len(out) < limit:
        for sub in ("app/index.html", "index.html"):
            ui = app / sub
            if not ui.exists():
                continue
            try:
                html = ui.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            labels = (re.findall(r'aria-label="([^"]+)"', html)
                      + re.findall(r'placeholder="([^"]+)"', html)
                      + re.findall(r"<button[^>]*>([^<]{2,40})</button>",
                                   html))
            for raw in labels:
                add(re.sub(r"\s+", " ", raw))
                if len(out) >= limit:
                    break
            if out:
                break

    return out[:limit]


def ask(model: str, mode: str = "short") -> dict:
    p = product()
    name = p.get("name") or p.get("title") or p.get("slug", "this tool")
    price = price_label(p.get("price"))
    blurb = (p.get("blurb") or p.get("description") or "")[:400]

    tour = mode == "tour"
    known = real_features(str(p.get("slug", ""))) if tour else []
    if tour:
        log(f"{len(known)} real features found to write the tour from")

    # Asking for more lines than there is material for gets nothing back at
    # all: the model declines rather than inventing. The count is derived from
    # what was actually found, so the request is always answerable.
    want = min(8, max(3, len(known))) if tour else 0
    if tour:
        log(f"asking for {want} tour line(s), which is what the material "
            f"supports")

    shape = (f"""  "tour"    a list of {want} strings, each under 16 words
  "proof"   one sentence
  "ask"     under 8 words
""" if tour else """  "proof"   one sentence
  "ask"     under 7 words
""")

    facts = ("\n".join(f"- {f}" for f in known) if known
             else "(none available, write only what the blurb supports)")

    prompt = f"""Tool: {name}
What it does: {blurb}
Price, shown on screen only: {price}

These are the features it genuinely has. Use them and nothing else:
{facts}

Produce a JSON object with exactly these keys:
  "hook"    under 7 words, the pain in plain words
  "problem" one sentence
{shape}
{"Write one tour line for each feature listed above, and no others. "
  "Use the whole of each line: say what the feature does for the person, "
  "not just its name." if known
 else "Keep it short; do not invent capabilities."}

{RULES}"""
    raw = providers.groq_chat(model, f"You are a direct response copywriter. "
                                    f"{RULES}", prompt, 0.85,
                              1100 if tour else 600)
    return _clean(raw, p, mode, want)


def _clean(raw: str, p: dict, mode: str = "short",
           want: int = 0) -> dict:
    """Pull the JSON out of whatever the model wrapped it in."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit(f"[shorts] no JSON in the model's reply: {raw[:120]}")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise SystemExit(f"[shorts] malformed JSON: {m.group(0)[:120]}")

    name = str(p.get("name") or p.get("title") or "this tool").lower()
    tour = [str(b).strip().rstrip(".")
            for b in (d.get("tour") or []) if str(b).strip()]
    out = {
        "hook": str(d.get("hook", "")).strip(),
        "problem": str(d.get("problem", "")).strip(),
        "proof": str(d.get("proof", "")).strip(),
        "ask": str(d.get("ask", "")).strip(),
        "tour": tour[:9] if mode == "tour" else [],
    }
    if mode == "tour" and not out["tour"]:
        # saying "tour" while shipping a four line short is how an 11 second
        # clip gets called a 60 second one, so the fallback says what it is
        log(f"no tour lines came back (asked for {want}), so this is a short")
        out["mode"] = "short"
    else:
        out["mode"] = mode

    fields = [k for k, v in out.items() if k != "tour" and v]
    for k in fields:
        # the brand is on screen, never in the narration
        if name and name in out[k].lower():
            log(f"stripped the brand name out of the {k}")
            out[k] = re.sub(re.escape(name), "it", out[k], flags=re.I)
        # a spoken price fights the voice and is forgotten; the card carries it
        if re.search(r"\$\s?\d|\b\d+\s?(dollars|pounds|euros|usd)\b",
                     out[k], re.I):
            log(f"stripped a spoken price out of the {k}")
            cleaned = re.sub(r"[^.]*\$\s?\d[^.]*\.?", "", out[k])
            if len(cleaned.strip()) < 12:
                cleaned = "It runs on your own machine, not a server."
            out[k] = cleaned.strip()
    for i, t in enumerate(out["tour"]):
        if name and name in t.lower():
            out["tour"][i] = re.sub(re.escape(name), "it", t, flags=re.I)
        if re.search(r"\$\s?\d|\b\d+\s?(dollars|pounds|euros|usd)\b",
                     t, re.I):
            out["tour"].pop(i)
            break

    if not out["hook"]:
        raise SystemExit("[shorts] the model returned no hook")
    if not out["ask"]:
        out["ask"] = "Download it free to try."
    return out


def lines(d: dict) -> list[str]:
    """The narration in the order it is spoken."""
    seq = [d["hook"], d.get("problem", "")]
    seq += list(d.get("tour") or [])
    seq += [d.get("proof", ""), d["ask"]]
    return [s for s in seq if s]


def duration_estimate(d: dict) -> float:
    """Rough spoken length, so the render knows how long to hold the last card.

    Narration pace lands near 2.4 words a second for these voices, plus a beat
    of silence at each scene change. A tour that reports 60 seconds and comes
    back at 12 is worse than a short number, so this is reported honestly and
    the runtime is measured later anyway.
    """
    words = sum(len(s.split()) for s in lines(d))
    return round(words / 2.4 + 0.55 * max(1, len(lines(d)) - 1), 1)


def runtime_note(secs: float, mode: str) -> str:
    """What the caller wanted, against what is actually there."""
    want = 60 if mode == "tour" else 20
    return f"{secs:.0f}s of about {want}s"


def main() -> int:
    model = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() \
        or "openai/gpt-oss-120b"
    mode = (os.environ.get("SHORTS_MODE") or "short").strip().lower()
    if mode not in ("short", "tour"):
        mode = "short"

    d = ask(model, mode)
    p = product()
    name = p.get("name") or p.get("title") or p.get("slug")
    got = d.get("mode", mode)

    out = {
        "slug": p.get("slug"),
        "name": name,
        "price": price_label(p.get("price")),
        "blurb": p.get("blurb") or p.get("description") or "",
        "mode": got,
        "requested_mode": mode,
        "seconds": duration_estimate(d),
        "narration": lines(d),
        "beats": d,
        "name": name,
    }
    dest = ROOT / "data" / "shorts_script.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log(f"{runtime_note(out['seconds'], got)}, "
        f"{len(out['narration'])} lines -> {dest.name}")
    if got != mode:
        log(f"asked for {mode}, produced {got}")
    for s in out["narration"]:
        log(f"   {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())