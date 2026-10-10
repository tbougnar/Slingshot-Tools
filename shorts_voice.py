"""Speak the narration, and report where each line starts and ends.

Voice is Edge TTS: Microsoft's neural voices, no API key, no signup, no
per-character charge. It is the most natural speech available for nothing.

Word timings come from the synthesiser itself, which marks each boundary, so
the captions land on the words rather than on a guess. That is what keeps the
video from looking like a slideshow with audio over it.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent

# en-GB-SoniaNeural is the most natural of the free voices and still has the
# pace for a thirty second ad. Rate is nudged up a little because a Short that
# runs long loses people before the price lands.
VOICE = "en-GB-SoniaNeural"
RATE = "+8%"
PITCH = "+2Hz"


def log(m: str) -> None:
    print(f"[voice] {m}", flush=True)


async def _one(line: str, dest: Path, index: int) -> dict:
    """Synthesise one line and return where it sits in the timeline."""
    marks: list[dict] = []
    comm = edge_tts.Communicate(line, VOICE, rate=RATE, pitch=PITCH)
    with dest.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                marks.append({"offset": chunk["offset"] / 1e7,
                              "text": chunk.get("text", "")})

    if not dest.exists() or dest.stat().st_size < 512:
        raise SystemExit(f"[voice] line {index} produced no audio")
    return {"file": dest.name, "offset": marks, "text": line}


async def _all(lines: list[str], work: Path) -> list[dict]:
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        out.append(await _one(line, work / f"line{i:02d}.mp3", i))
        log(f"line {i + 1}/{len(lines)} ok")
    return out


def main() -> int:
    script_path = ROOT / "data" / "shorts_script.json"
    if not script_path.exists():
        raise SystemExit("[voice] run shorts_script.py first")
    script = json.loads(script_path.read_text(encoding="utf-8"))

    work = ROOT / "data" / "shorts_audio"
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("*.mp3"):
        old.unlink()

    parts = asyncio.run(_all(script["narration"], work))
    if not parts:
        raise SystemExit("[voice] nothing to say")

    dest = ROOT / "data" / "shorts_voice.json"
    dest.write_text(json.dumps({"voice": VOICE, "parts": parts},
                               indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log(f"{len(parts)} clips -> {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())