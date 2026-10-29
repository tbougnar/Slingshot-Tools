"""Write the words for the monthly release trailer.

The trailer is the one piece of this feature where the model has genuinely
free rein, because the script is prose rather than code: there is nothing here
that a bad sentence can break.

What it deliberately does not do is promise anything. The notes come from
``update_plan``, which chose them from the fixed menu of things that can
actually be built, so a trailer cannot advertise a feature nobody built. That
coupling is the whole reason the plan is a separate module.

    python update_trailer_script.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import providers
import update_state as us

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "trailer_script.json"

# Enough for a short trailer and short enough that nobody drops off.
TARGET_LINES = (5, 7)
# One line is roughly this many spoken words; used to keep the runtime honest.
WORDS_PER_LINE = 11


def log(m: str) -> None:
    print(f"[trailerscript] {m}", flush=True)


def _slug() -> str:
    """An app to show in the trailer.

    The catalog is asked first so the trailer shows a real app; if the catalog
    is unreadable the trailer still renders, just without a screenshot.
    """
    catalog = ROOT / "site" / "apps.json"
    if catalog.exists():
        try:
            apps = json.loads(catalog.read_text(encoding="utf-8"))
            live = [a for a in apps if a.get("published")
                    and a.get("tier") == "basic"]
            if live:
                return str(live[0].get("slug") or "")
        except (json.JSONDecodeError, OSError, AttributeError):
            pass
    return ""


def local(state: dict) -> dict:
    """A script built from the plan, with no model at all.

    This is the fallback and it is good enough to ship, because the plan
    already contains the three things worth saying.
    """
    title = str(state.get("next_major_title") or "This month's update")
    notes = [str(n) for n in (state.get("next_major_notes") or []) if str(n)]
    version = state.get("version") or "1.0.0"

    lines = [f"{title}. Here's what changed."]
    for n in notes[:3]:
        # the plan writes fragments, and a spoken line needs to be a sentence
        s = str(n).rstrip(".")
        lines.append(s[0].upper() + s[1:] + ".")
    lines.append(f"That's version {version}, free as always. "
                 f"Everything already installed just updates.")
    return {"title": title, "version": version, "slug": _slug(),
            "notes": notes[:4], "narration": lines, "written_by": "plan"}


def ask(state: dict) -> dict | None:
    """Let the model write the lines, from the plan's own notes."""
    if not providers.configured():
        log("no model available, writing it from the plan")
        return None

    title = str(state.get("next_major_title") or "This month's update")
    notes = [str(n) for n in (state.get("next_major_notes") or []) if str(n)]
    listing = "\n".join(f"- {n}" for n in notes)
    try:
        raw = providers.chat(
            providers.best_model("debug"),
            "You write voiceover for a software release trailer. Spoken, "
            "warm, concrete. You never promise a feature that is not in the "
            "notes you are given.",
            f"Write a short trailer voiceover.\n\n"
            f"HEADLINE: {title}\nCHANGES:\n{listing}\n\n"
            "Rules:\n"
            f"- {TARGET_LINES[0]} to {TARGET_LINES[1]} short lines, one "
            f"idea each\n"
            "- written to be spoken out loud: no brackets, no markdown, no "
            "stage directions\n"
            "- no feature that is not in CHANGES\n"
            "- end by saying it is free and already available to install\n"
            'Reply with JSON only: {"lines":["..."]}',
            temperature=0.8, max_tokens=500, role="debug")
    except Exception as e:  # noqa: BLE001
        log(f"the model could not be reached: {str(e)[:80]}")
        return None

    try:
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError, AttributeError):
        log("the model did not return JSON, writing it from the plan")
        return None

    lines = [_tidy(x) for x in (d.get("lines") or [])]
    lines = [x for x in lines if x]
    if len(lines) < 3:
        log(f"only {len(lines)} usable lines came back, using the plan instead")
        return None

    return {"title": title, "version": state.get("version") or "1.0.0",
            "slug": _slug(), "notes": notes[:4],
            "narration": lines[:TARGET_LINES[1]], "written_by": "model"}


def _tidy(text: str) -> str:
    """One clean spoken line.

    Stage directions and markdown come back surprisingly often, and a line
    reading "[upbeat music] Everything got faster" would be spoken aloud by
    the synthesiser.
    """
    s = str(text or "").strip()
    s = re.sub(r"^\s*[\[(][^\])]*[\])]\s*", "", s)      # drop a leading cue
    s = re.sub(r"[*_`#>]+", "", s)                      # drop markdown
    s = " ".join(s.split())
    return s[:220]


def build() -> dict:
    state = us.load()
    script = ask(state) or local(state)

    # the plan's notes must still be reachable even if the model rewrote the
    # lines, because the renderer shows them when there is no screenshot
    if not script.get("notes"):
        script["notes"] = list(state.get("next_major_notes") or [])

    words = sum(len(l.split()) for l in script["narration"])
    script["seconds"] = round(words / 2.4 + 0.4 * len(script["narration"]), 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(script, indent=2), encoding="utf-8")
    log(f"{len(script['narration'])} lines, ~{script['seconds']:.0f}s, "
        f"written by {script['written_by']}")
    return script


def main() -> int:
    script = build()
    print()
    for i, line in enumerate(script["narration"], 1):
        print(f"  {i}. {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())