"""Speak the trailer, reusing the Shorts voice pipeline unchanged.

There is no reason for a second synthesiser. ``shorts_voice.speak_line``
already does the thing that matters: it tries the configured ElevenLabs voice,
falls back to Edge TTS when the account is out of credits, measures the real
duration of each clip rather than estimating it, and returns word timings for
the captions.

The only thing that has to be different is the paths, because the Shorts and
the trailer are two videos that must be able to exist at the same time. That is
done by pointing the same function at a different folder, not by copying it.

    python update_trailer_voice.py
"""
from __future__ import annotations

import json
from pathlib import Path

import shorts_voice as sv
import update_state as us

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "data" / "trailer_script.json"
VOICE = ROOT / "data" / "trailer_voice.json"
WORK = ROOT / "data" / "trailer_audio"


def log(m: str) -> None:
    print(f"[trailervoice] {m}", flush=True)


def build() -> dict:
    if not SCRIPT.exists():
        raise SystemExit("[trailervoice] run update_trailer_script.py first")
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))

    lines = [str(x) for x in (script.get("narration") or []) if str(x).strip()]
    if not lines:
        raise SystemExit("[trailervoice] the trailer script has no lines")

    engine = "elevenlabs" if sv.have_eleven() else "edge tts"
    log(f"voice engine: {engine}")

    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("*.mp3"):
        old.unlink()

    parts = []
    for i, line in enumerate(lines):
        got = sv.speak_line(line, WORK / f"line{i:02d}.mp3", i)
        parts.append(got)
        log(f"  line {i + 1}/{len(lines)} ok")

    # measured, not estimated: the renderer has to know where each line starts,
    # and a guess that is a second out puts the captions on the wrong words
    total = sum(float(p.get("seconds") or 0.0) for p in parts)
    if total <= 0:
        raise SystemExit("[trailervoice] every clip came back empty")

    out = {"parts": parts, "seconds": round(total, 2),
           "engine": engine, "lines": len(parts),
           "slug": script.get("slug") or ""}
    VOICE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log(f"{len(parts)} clips, {total:.1f}s -> {VOICE.relative_to(ROOT)}")
    return out


def main() -> int:
    build()
    got = json.loads(VOICE.read_text(encoding="utf-8"))
    print()
    print(json.dumps({"seconds": got["seconds"], "engine": got["engine"],
                      "lines": got["lines"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())