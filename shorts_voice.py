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
import shutil
import subprocess
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


def seconds(path: Path) -> float:
    """Real length of a clip, so the timeline is measured rather than guessed.

    An estimate that runs a second long leaves the last scene talking over
    silence; one that runs short cuts the call to action off.
    """
    probe = shutil.which("ffprobe")
    if probe:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, errors="replace")
        try:
            return float((out.stdout or "").strip())
        except ValueError:
            pass
    return 0.0


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
    return {"file": dest.name, "offset": marks, "text": line,
            "seconds": seconds(dest)}


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

    # a short breath between lines, so the call to action does not run into
    # the previous sentence
    gap = 0.22
    start = 0.0
    for p in parts:
        dur = p.get("seconds") or 0.0
        p["start"] = round(start, 3)
        if dur <= 0:
            # no ffprobe: fall back to the marker span plus a tail
            marks = p.get("offset") or []
            dur = (marks[-1]["offset"] + 0.4) if marks else 2.0
            p["seconds"] = round(dur, 3)
        start += dur + gap

    total = round(start - gap, 2)
    dest = ROOT / "data" / "shorts_voice.json"
    dest.write_text(json.dumps({"voice": VOICE, "parts": parts,
                                "seconds": total, "gap": gap},
                               indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log(f"{len(parts)} clips, {total:.1f}s total -> {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())