"""Clone the Slingshot narration voice from a recording, once.

    python shorts_clone.py "C:/Users/Taha/Videos/HEARME.wav"

Prints the voice id and the command to store it. Nothing is written to disk
and no secret is printed, so running it is safe: the key is read from the
environment, never asked for here.

Instant voice cloning is included on ElevenLabs' free plan. What costs money
is the higher fidelity and the longer samples, not the cloning itself. The
sample should be clean speech, at least ten seconds, with no music or noise.
"""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

import shorts_voice as sv

ROOT = Path(__file__).resolve().parent


def log(m: str) -> None:
    print(f"[clone] {m}", flush=True)


def inspect(path: Path) -> float:
    """Report what the sample actually is, before sending it anywhere.

    The length matters most: too short gives a thin voice, and a sample with
    music in it produces a clone that carries the music.
    """
    try:
        w = wave.open(str(path), "rb")
        rate = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        w.close()
    except wave.Error:
        log("not a plain wav; elevenlabs still accepts mp3 and m4a")
        return path.stat().st_size / 32000.0

    dur = n / rate
    log(f"{dur:.1f}s, {rate} Hz, {ch} channel(s)")
    if dur < 10:
        log("shorter than ten seconds; the clone will sound thin")
    if dur > 300:
        log("longer than five minutes; elevenlabs may reject it")
    return dur


def main() -> int:
    if not sv.key():
        log("ELEVENLABS_API_KEY is not set in this shell")
        log("set it first:")
        log('  $env:ELEVENLABS_API_KEY="sk_..."')
        return 1

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        log("usage: python shorts_clone.py <path to a wav of your voice>")
        return 1

    sample = Path(args[0]).expanduser()
    if not sample.exists():
        log(f"no file at {sample}")
        return 1

    log(f"sample: {sample}")
    inspect(sample)

    log("uploading and cloning, this takes a moment")
    try:
        vid = sv.clone_voice(sample)
    except SystemExit as e:
        log(str(e))
        return 1

    log(f"voice id: {vid}")
    log("")
    log("Store it, then the Shorts pipeline will use your voice:")
    log("")
    log("  gh variable set ELEVENLABS_VOICE_ID "
        f"--body {vid} --repo tbougnar/Slingshot-Tools")
    log("")
    log("To keep working without it, nothing changes: the pipeline falls back")
    log("to Edge TTS on its own.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())