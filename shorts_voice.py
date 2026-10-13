"""Speak the narration, and report where each line starts and ends.

Two engines, in order:

- ElevenLabs, using a clone of our own voice, when an API key is set
- Edge TTS, which needs no account and no key

The fallback is not decoration. A pipeline that runs unattended cannot depend
on a paid quota, so if ElevenLabs is out of credits, rate limited, or simply
down, the Short still gets made with a good voice rather than not made at all.

Word timings come from the synthesiser itself, so captions land on the words
rather than on a guess. ElevenLabs reports those in the alignment endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent

API = "https://api.elevenlabs.io/v1"

# en-GB-SoniaNeural is the most natural free voice available. Rate is nudged
# up because a Short that runs long loses people before the price lands.
EDGE_VOICE = "en-GB-SoniaNeural"
EDGE_RATE = "+8%"
EDGE_PITCH = "+2Hz"

# eleven_multilingual_v2 handles the phrasing better than v3 on short lines,
# where v3's expressiveness can sound theatrical.
ELEVEN_MODEL = os.environ.get("ELEVENLABS_MODEL", "").strip() \
    or "eleven_multilingual_v2"
ELEVEN_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()

VOICE_CLONE_NAME = "Slingshot Notes"


def log(m: str) -> None:
    print(f"[voice] {m}", flush=True)


def key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def have_eleven() -> bool:
    return bool(key() and ELEVEN_VOICE_ID)


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


def clone_voice(sample: Path, name: str = VOICE_CLONE_NAME) -> str:
    """One-time clone from a recording, returning the voice id.

    Instant voice cloning is included on the free plan; the paid tiers buy
    higher fidelity and longer samples, not the ability to clone at all.
    """
    if not key():
        raise SystemExit("[voice] no ELEVENLABS_API_KEY")

    if not sample.exists():
        raise SystemExit(f"[voice] no sample at {sample}")

    boundary = "----slingshot" + "0" * 24
    audio = sample.read_bytes()

    parts: list[bytes] = []
    for field, value in (("name", name),
                         ("description",
                          "Slingshot Tools narration voice, cloned from a "
                          "recording of the owner"),
                         ("remove_background_noise", "false")):
        parts.append(
            f"--{boundary}\r\n".encode()
            + f'Content-Disposition: form-data; name="{field}"\r\n\r\n'
            .encode()
            + f"{value}\r\n".encode())

    parts.append(
        f"--{boundary}\r\n".encode()
        + f'Content-Disposition: form-data; name="files"; '
          f'filename="{sample.name}"\r\n'.encode()
        + b"Content-Type: audio/wav\r\n\r\n" + audio + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{API}/voices/add", data=body, method="POST",
        headers={"xi-api-key": key(),
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})

    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise SystemExit(f"[voice] cloning refused: HTTP {e.code} {detail}")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[voice] cloning failed: {str(e)[:100]}")

    vid = d.get("voice_id", "")
    if not vid:
        raise SystemExit(f"[voice] no voice id came back: {str(d)[:160]}")
    if d.get("requires_verification"):
        log("the clone needs verifying on elevenlabs.io before it will speak")
    return vid


def list_voices(search: str = "") -> list[dict]:
    """The account's voices, plus the library, so there is something to pick.

    v2 is the documented endpoint; v1 is tried too because the API has moved
    versions before and a 404 on one of them should not read as no voices.
    """
    q = {"page_size": "100"}
    if search:
        q["search"] = search

    for path in ("/v2/voices", "/v1/voices"):
        req = urllib.request.Request(
            f"{API}{path}?{urllib.parse.urlencode(q)}",
            headers={"xi-api-key": key()})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d.get("voices") or d.get("owned_by_user") or []
        except urllib.error.HTTPError:
            continue
        except Exception:  # noqa: BLE001
            continue
    return []


# ------------------------------------------------------------- elevenlabs

def _eleven_speak(line: str, dest: Path) -> list[dict]:
    """One line through ElevenLabs, with character timings if offered."""
    url = f"{API}/text-to-speech/{ELEVEN_VOICE_ID}"
    q = urllib.parse.urlencode({"output_format": "mp3_44100_128"})
    body = json.dumps({
        "text": line,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": 0.42, "similarity_boost": 0.78,
                           "style": 0.18},
    }).encode()
    req = urllib.request.Request(
        f"{url}?{q}", data=body, method="POST",
        headers={"xi-api-key": key(),
                 "Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    dest.write_bytes(raw)

    # alignment is a separate call and optional; without it the renderer
    # falls back to estimating from the clip length
    marks: list[dict] = []
    try:
        aq = urllib.parse.urlencode({
            "text": line, "model_id": ELEVEN_MODEL,
            "output_format": "mp3_44100_128"})
        areq = urllib.request.Request(
            f"{url}/with-timestamps?{aq}", data=json.dumps({
                "text": line, "model_id": ELEVEN_MODEL}).encode(),
            method="POST",
            headers={"xi-api-key": key(),
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(areq, timeout=180) as r:
            ad = json.loads(r.read().decode("utf-8"))
        for ch in (ad.get("alignment") or {}).get("characters", []):
            marks.append({"offset": float(ch.get("character_start", 0)) / 1e7,
                          "text": ch.get("character", "")})
    except Exception:  # noqa: BLE001
        marks = []
    return marks


# --------------------------------------------------------------- edge tts

async def _edge_one(line: str, dest: Path, index: int) -> dict:
    """Synthesise one line and return where it sits in the timeline.

    The boundary has to be requested explicitly. edge_tts defaults to
    SentenceBoundary, which silently produces a clip with no timings at all,
    and the captions simply never appear.
    """
    marks: list[dict] = []
    comm = edge_tts.Communicate(line, EDGE_VOICE, rate=EDGE_RATE,
                                pitch=EDGE_PITCH, boundary="WordBoundary")
    with dest.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                # edge-tts offsets are in 100-nanosecond ticks
                marks.append({"offset": chunk["offset"] / 1e7,
                              "text": chunk.get("text", "")})

    if not dest.exists() or dest.stat().st_size < 512:
        raise SystemExit(f"[voice] line {index} produced no audio")
    if not marks:
        raise SystemExit(
            f"[voice] line {index} gave no word timings, so the captions "
            f"would be empty")
    return {"file": dest.name, "offset": marks, "text": line,
            "seconds": seconds(dest)}


def _words_from_text(line: str, dur: float) -> list[dict]:
    """Spread words across a clip when the engine gave no timings.

    Better than no captions, and honest about being an estimate.
    """
    ws = line.split()
    if not ws or dur <= 0:
        return []
    step = dur / len(ws)
    return [{"offset": round(i * step, 3), "text": w}
            for i, w in enumerate(ws)]


def speak_line(line: str, dest: Path, index: int) -> dict:
    """One line, on whichever engine is available."""
    if have_eleven():
        try:
            marks = _eleven_speak(line, dest)
            dur = seconds(dest)
            if not dest.exists() or dest.stat().st_size < 512:
                raise RuntimeError("no audio came back")
            if not marks:
                marks = _words_from_text(line, dur)
                # _words_from_text already returns offsets in seconds, the
                # same units as the ElevenLabs alignment path above. They were
                # multiplied by dur a second time here, so a three-second line
                # of six words placed its captions at 0, 1.5, 3, 4.5, 6 and
                # 7.5 seconds: the last caption fired four and a half seconds
                # after the clip had ended. Nothing logged it.
                marks = [{"offset": round(m["offset"], 3), "text": m["text"]}
                         for m in marks]
            return {"file": dest.name, "offset": marks, "text": line,
                    "seconds": dur or (marks[-1]["offset"] + 0.4)}
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"elevenlabs failed on line {index + 1} ({str(e)[:60]}), "
                f"using the fallback voice")
    return asyncio.run(_edge_one(line, dest, index))


def main() -> int:
    script_path = ROOT / "data" / "shorts_script.json"
    if not script_path.exists():
        raise SystemExit("[voice] run shorts_script.py first")
    script = json.loads(script_path.read_text(encoding="utf-8"))

    engine = "elevenlabs" if have_eleven() else "edge tts"
    if not have_eleven() and key():
        log("an API key is set but no ELEVENLABS_VOICE_ID, so the clone has "
            "not been made yet")
        log("run:  python shorts_clone.py <a wav of your voice>")
    log(f"voice engine: {engine}")

    work = ROOT / "data" / "shorts_audio"
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("*.mp3"):
        old.unlink()

    parts = []
    for i, line in enumerate(script["narration"]):
        if not line.strip():
            continue
        parts.append(speak_line(line, work / f"line{i:02d}.mp3", i))
        log(f"line {i + 1}/{len(script['narration'])} ok")
    if not parts:
        raise SystemExit("[voice] nothing to say")

    # a short breath between lines, so the call to action does not run into
    # the previous sentence
    gap = 0.22
    at = 0.0
    for p in parts:
        dur = p.get("seconds") or 0.0
        p["start"] = round(at, 3)
        if dur <= 0:
            marks = p.get("offset") or []
            dur = (marks[-1]["offset"] + 0.4) if marks else 2.0
            p["seconds"] = round(dur, 3)
        at += dur + gap

    total = round(at - gap, 2)
    dest = ROOT / "data" / "shorts_voice.json"
    dest.write_text(json.dumps({"voice": engine, "parts": parts,
                                "seconds": total, "gap": gap},
                               indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log(f"{len(parts)} clips, {total:.1f}s total -> {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())