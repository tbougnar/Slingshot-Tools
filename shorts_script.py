"""Write the narration for a Short, from what the product actually is.

The script is generated from the published product record rather than written by
hand, so the price and the claim in the video can never drift from what is
sold. A Short that quotes a price that has changed is worse than no Short.

Groq writes it because it is already a dependency and it is free.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import providers

ROOT = Path(__file__).resolve().parent

# Shorts are vertical and autoplayed muted, so the first words carry the whole
# video and everything after that has to earn the next second.
RULES = """Write narration for a 30 second vertical YouTube Short advertising a \
desktop tool.

Hard rules:
- Open with a hook in the first five words. No "introducing", no "in this \
video".
- Say what it does in one plain sentence, then the price, then one call to \
action.
- Short sentences. It is spoken aloud, so no parentheses, no bullet points, no \
em dashes, no markdown.
- Do not use the words "revolutionary", "game-changing", "seamless", \
"game changer", "unlock", "supercharge", or "elevate".
- Never claim the tool does something it does not do.
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
Price: {price}

Produce a JSON object with exactly these keys:
  "hook"    - under 8 words, the opening line
  "beats"   - a list of 3 to 4 strings, each under 16 words, the middle of \
the video
  "price"   - one short sentence that says the price exactly as written above
  "cta"     - under 8 words, what to do now

The price sentence must contain the price exactly as given. Do not turn it \
into words, do not round it, do not invent a discount.

{RULES}"""
    raw = providers.groq_chat(model, f"You are a direct response copywriter. "
                                    f"{RULES}", prompt, 0.8, 700)
    return _clean(raw, p, name, price)


def _clean(raw: str, p: dict, name: str, price: str) -> dict:
    """Pull the JSON out of whatever the model wrapped it in."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit(f"[shorts] no JSON in the model's reply: {raw[:120]}")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise SystemExit(f"[shorts] malformed JSON: {m.group(0)[:120]}")

    beats = [str(b).strip() for b in d.get("beats", []) if str(b).strip()]
    out = {
        "hook": str(d.get("hook", "")).strip(),
        "beats": beats[:4],
        "price": str(d.get("price", "")).strip(),
        "cta": str(d.get("cta", "")).strip(),
    }
    # fall back to the product's own words rather than shipping a hole
    out["hook"] = out["hook"] or f"Stop doing {name} by hand."
    out["price"] = out["price"] or f"It is {price}, one off."
    out["cta"] = out["cta"] or "Link in the bio."

    # the number shown has to be the number sold, whatever the model wrote
    digits = re.findall(r"\$?\d+(?:\.\d+)?", out["price"])
    want = re.findall(r"\$?\d+(?:\.\d+)?", price)
    if want and (not digits or digits[0] != want[0]):
        out["price"] = f"It is {price}. One off, yours forever."

    return out


def lines(d: dict) -> list[str]:
    """The narration in the order it is spoken."""
    seq = [d["hook"]] + list(d["beats"]) + [d["price"], d["cta"]]
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