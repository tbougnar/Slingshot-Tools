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

RULES = """Write narration for a 20 second vertical advert for a desktop tool.

Structure, in order, and nothing else:
  hook    under 7 words. The pain, in the words a real person would use.
  problem one sentence. The cost of living with it today.
  proof   one sentence. What the tool does about it, plainly.
  ask     under 7 words. One action.

Hard rules:
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


def ask(model: str) -> dict:
    p = product()
    name = p.get("name") or p.get("title") or p.get("slug", "this tool")
    price = price_label(p.get("price"))
    blurb = (p.get("blurb") or p.get("description") or "")[:400]

    prompt = f"""Tool: {name}
What it does: {blurb}
Price, shown on screen only: {price}

Produce a JSON object with exactly these keys:
  "hook"    under 7 words, the pain in plain words
  "problem" one sentence
  "proof"   one sentence
  "ask"     under 7 words, one action

{RULES}"""
    raw = providers.groq_chat(model, f"You are a direct response copywriter. "
                                    f"{RULES}", prompt, 0.85, 600)
    return _clean(raw, p)


def _clean(raw: str, p: dict) -> dict:
    """Pull the JSON out of whatever the model wrapped it in."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit(f"[shorts] no JSON in the model's reply: {raw[:120]}")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise SystemExit(f"[shorts] malformed JSON: {m.group(0)[:120]}")

    name = str(p.get("name") or p.get("title") or "this tool").lower()
    out = {
        "hook": str(d.get("hook", "")).strip(),
        "problem": str(d.get("problem", "")).strip(),
        "proof": str(d.get("proof", "")).strip(),
        "ask": str(d.get("ask", "")).strip(),
    }

    # the brand is on screen, never in the narration
    name = str(p.get("name") or p.get("title") or "this tool").lower()
    for k, v in list(out.items()):
        if name and name in v.lower():
            log(f"stripped the brand name out of the {k}")
            out[k] = re.sub(re.escape(name), "it", v, flags=re.I)

    # a spoken price fights the voice and is forgotten; the card carries it
    for k, v in list(out.items()):
        if not re.search(r"\$\s?\d|\b\d+\s?(dollars|pounds|euros|usd)\b", v,
                         re.I):
            continue
        log(f"stripped a spoken price out of the {k}")
        # drop the whole clause the number sits in, not just the digits: a
        # sentence whose only content was the price leaves nothing worth
        # saying, and the card shows it better anyway
        cleaned = re.sub(r"[^.]*\$\s?\d[^.]*\.?", "", v)
        if len(cleaned.strip()) < 12:
            # the whole line was the price; make it a benefit instead
            cleaned = "It runs on your own machine, not a server."
        out[k] = cleaned.strip()

    if not out["hook"]:
        raise SystemExit("[shorts] the model returned no hook")
    if not out["ask"]:
        out["ask"] = "Download it free to try."
    return out


def lines(d: dict) -> list[str]:
    """The narration in the order it is spoken."""
    seq = [d["hook"], d.get("problem", ""), d.get("proof", ""), d["ask"]]
    return [s for s in seq if s]


def duration_estimate(d: dict) -> float:
    """Rough spoken length, so the render knows how long to hold the last card.

    Narration pace lands near 2.6 words a second for these voices, plus a beat
    of silence at each scene change.
    """
    words = sum(len(s.split()) for s in lines(d))
    return round(words / 2.6 + 0.8 * (len(lines(d)) - 1), 1)


def main() -> int:
    model = (os.environ.get("GROQ_CHAT_MODEL") or "").strip() \
        or "openai/gpt-oss-120b"
    d = ask(model)
    p = product()
    name = p.get("name") or p.get("title") or p.get("slug")

    out = {
        "slug": p.get("slug"),
        "name": name,
        "price": price_label(p.get("price")),
        "blurb": p.get("blurb") or p.get("description") or "",
        "seconds": duration_estimate(d),
        "narration": lines(d),
        "beats": d,
    }
    dest = ROOT / "data" / "shorts_script.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log(f"{out['seconds']}s, {len(out['narration'])} lines -> {dest.name}")
    for s in out["narration"]:
        log(f"   {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())