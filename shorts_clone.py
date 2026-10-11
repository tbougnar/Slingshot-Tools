"""Create the Slingshot narration voice, once, and say how to store it.

Two ways in, because ElevenLabs gates them differently:

    python shorts_clone.py design "warm confident British narrator, mid twenties"
    python shorts_clone.py clone  "C:/path/to/your.wav"

design works on the free plan and produces a synthetic voice that belongs to
this project. clone reproduces a recording of a specific person and needs the
$6 Starter plan, because instant voice cloning is not in the free tier.

Prints the voice id and the command to store it. Nothing is written to disk and
no secret is printed, so running it is safe: the key is read from the
environment, never asked for here.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import shorts_voice as sv

ROOT = Path(__file__).resolve().parent

# Free-tier defaults that suit a product ad: mid range, unhurried, British,
# with a little lift at the end of a sentence rather than a flat read.
DESCRIBE = ("warm confident British narrator, mid twenties, clear and "
            "friendly, unhurried delivery, slight lift at the end of a "
            "sentence, no background noise")
NAME = "Slingshot Notes"


def log(m: str) -> None:
    print(f"[clone] {m}", flush=True)


def _post(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{sv.API}{path}", data=body, method="POST",
        headers={"xi-api-key": sv.key(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:220]
        try:
            d = json.loads(detail).get("detail", {})
            msg = d.get("message") or detail
            code = d.get("code") or ""
        except Exception:  # noqa: BLE001
            msg, code = detail, ""
        if "paid_plan_required" in detail or code == "paid_plan_required":
            log("instant voice cloning is not in the free plan")
            log("it needs Starter at $6 a month:")
            log("  https://elevenlabs.io/app/subscription")
            log("")
            log("meanwhile, design a voice instead, which is free:")
            log("  python shorts_clone.py design")
        raise SystemExit(f"[clone] refused: {msg}")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[clone] failed: {str(e)[:120]}")


def design(text: str = DESCRIBE, name: str = NAME) -> str:
    """A voice built from a description, which the free plan does allow."""
    d = _post("/voice-design", {
        "voice_design": {
            "description": text,
            "preview_generate": False,
        },
        "model_id": sv.ELEVEN_MODEL,
        "name": name,
    })
    # the shape has changed before; accept either the wrapper or the flat form
    return str(d.get("voice_id") or (d.get("voice") or {}).get("voice_id") or "")


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
    if "--list" in sys.argv:
        if not sv.key():
            log("ELEVENLABS_API_KEY is not set in this shell")
            return 1
        try:
            for v in sv.list_voices():
                log(f"  {v.get('voice_id', '?'):24} {v.get('name', '?')}")
        except Exception as e:  # noqa: BLE001
            log(f"could not list voices: {str(e)[:90]}")
            return 1
        return 0

    mode = args[0].lower() if args else "design"

    if mode in ("design", "d", "--design"):
        brief = " ".join(args[1:]) if len(args) > 1 else DESCRIBE
        log("designing a voice; this is free on any plan")
        log(f"brief: {brief}")
        try:
            vid = design(brief)
        except SystemExit as e:
            log(str(e))
            return 1
        if not vid:
            log("no voice id came back, so nothing was created")
            return 1
        report(vid)
        return 0

    if mode in ("clone", "c", "--clone"):
        if len(args) < 2:
            log("usage: python shorts_clone.py clone <path to a wav>")
            return 1
        sample = Path(args[1]).expanduser()
        if not sample.exists():
            log(f"no file at {sample}")
            return 1
        log(f"sample: {sample}")
        inspect(sample)
        log("uploading and cloning, this takes a moment")
        try:
            vid = sv.clone_voice(sample, NAME)
        except SystemExit as e:
            log(str(e))
            return 1
        report(vid)
        return 0

    log("usage:")
    log("  python shorts_clone.py design <description>")
    log("  python shorts_clone.py clone  <path to a wav>")
    return 1


def report(vid: str) -> None:
    log(f"voice id: {vid}")
    log("")
    log("Store it and the Shorts pipeline will use this voice:")
    log("")
    log("  gh variable set ELEVENLABS_VOICE_ID "
        f"--body {vid} --repo tbougnar/Slingshot-Tools")
    log("")
    log("To hear it before wiring it up:")
    log(f"  python shorts_clone.py --list")
    log("")
    log("If ElevenLabs is unreachable the pipeline falls back to Edge TTS on")
    log("its own, so nothing is blocked either way.")
    return None


if __name__ == "__main__":
    raise SystemExit(main())