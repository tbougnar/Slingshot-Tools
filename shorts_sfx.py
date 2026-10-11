"""Sound design: a music bed and effects cut to the narration.

A silent Short reads as a slideshow with a voice over it. Sound does three
things the picture cannot: it carries pace, it marks the beat a cut lands on,
and it is the first thing people notice is missing when it is absent.

Every cue is generated from text, so there is no library to license and
nothing to go stale. Each one is placed by timestamp from the voice's own
timings, which is what keeps a whoosh on the transition instead of near it.

If ElevenLabs is unavailable the pipeline still produces a video, just a
quieter one, because a missing sound bed must never stop a launch.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.elevenlabs.io/v1"

# A licensed bed checked into the repo. Generating one costs credits that come
# and go, and an exhausted account silently ships the Short with no music at
# all, so the dependable source is the one that is always there. CC0, and the
# licence is written down next to the file.
LOCAL_BED = ROOT / "assets" / "music" / "dark_place_bed.mp3"

# Each cue says what it is for. The effect text is what the model is asked to
# produce, and the kind decides which lane it lands in.
CUES = [
    # (name, text, kind, when it fires)
    ("hit", "single cinematic bass hit with a short reverb tail, deep, "
            "clean, no music", "hit", 0.0),
    ("whoosh", "fast airy whoosh sweeping left to right, soft, modern",
     "transition", 0.02),
    ("click", "small crisp digital click, subtle, UI-like", "ui",
     0.10),
    ("type", "quiet keyboard typing, two short keystrokes", "ui", 0.18),
    ("reveal", "soft warm synth swell rising, gentle, optimistic, short",
     "transition", 0.30),
    ("confirm", "gentle positive confirmation chime, single tone, warm",
     "ui", 0.46),
    ("impact", "deep confident impact hit, punchy but not harsh, short decay",
     "hit", 0.62),
]

# a bed that sits under a voice without fighting it: low tempo, no lead
MUSIC_PROMPT = ("minimal dark ambient electronic bed, slow tempo around 80 bpm, "
                "soft sub bass pulse, sparse warm pads, no melody, no drums, "
                "no vocals, cinematic underscore for a product advert, "
                "leaves space for a voiceover")


def log(m: str) -> None:
    print(f"[sfx] {m}", flush=True)


def key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def _post(path: str, payload: dict, timeout: int = 180) -> bytes | None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}", data=body, method="POST",
        headers={"xi-api-key": key(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
            d = json.loads(raw).get("detail", {})
            code = d.get("code", "")
            msg = d.get("message", raw)[:130]
        except Exception:  # noqa: BLE001
            raw, code, msg = "", "", ""

        if "quota" in (code + msg).lower():
            # worth saying once, loudly: the account is out of credits and
            # every cue will be skipped, which looks like a broken pipeline
            if not OUT_OF_CREDITS:
                OUT_OF_CREDITS.append(True)
                log("")
                log("ElevenLabs has run out of credits on this account, so "
                    "no")
                log("sound design can be generated. The Short will still be "
                    "made,")
                log("with the voice only.")
                log("")
                log("Credits reset monthly, or Starter at $6 adds 30k:")
                log("  https://elevenlabs.io/app/subscription")
                log("")
        else:
            log(f"{path} refused: HTTP {e.code} {msg}")
    except Exception as e:  # noqa: BLE001
        log(f"{path} failed: {str(e)[:80]}")
    return None


OUT_OF_CREDITS: list[bool] = []


def sound_effect(text: str, dest: Path) -> bool:
    raw = _post("/sound-generation", {
        "text": text,
        "duration_seconds": None,
        "prompt_influence": 0.45,
    })
    if not raw or len(raw) < 1024:
        return False
    dest.write_bytes(raw)
    return True


def local_music(dest: Path, seconds: int) -> bool:
    """Cut the checked-in bed to length, looping it if it is too short.

    The bed is already faded at both ends, so looping it never clicks and
    cutting it early never lands on a hard stop.
    """
    if not LOCAL_BED.exists():
        return False
    want = max(6, int(seconds) + 2)
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001
            exe = None
    if not exe:
        log("no ffmpeg, so the local bed cannot be cut")
        return False

    cmd = [exe, "-y", "-stream_loop", "-1", "-i", str(LOCAL_BED),
           "-t", str(want), "-c:a", "libmp3lame", "-q:a", "4", str(dest)]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except Exception as e:  # noqa: BLE001
        log(f"could not cut the local bed: {str(e)[:70]}")
        return False
    return dest.exists() and dest.stat().st_size > 4096


def music(dest: Path, seconds: int) -> bool:
    """A bed long enough to cover the clip, with room to spare.

    The checked-in CC0 track is preferred, because it costs nothing and never
    runs out. ElevenLabs is the fallback for when the file is missing or the
    local cut fails.
    """
    if local_music(dest, seconds):
        log(f"local bed {LOCAL_BED.name}")
        return True
    want = max(6, int(seconds) + 6)
    raw = _post("/music", {
        "prompt": MUSIC_PROMPT,
        "music_length_ms": min(want * 1000, 300_000),
    }, timeout=240)
    if not raw or len(raw) < 4096:
        return False

    # loop the stem until it covers the clip
    cmd = [shutil.which("ffmpeg") or "", "-y", "-stream_loop", "-1",
           "-i", str(dest.with_suffix(".raw.mp3")), "-t", str(want + 2),
           "-c:a", "libmp3lame", "-q:a", "4", str(dest)]
    tmp = dest.with_suffix(".raw.mp3")
    tmp.write_bytes(raw)
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return dest.exists() and dest.stat().st_size > 4096
    except Exception as e:  # noqa: BLE001
        log(f"could not loop the bed: {str(e)[:70]}, using it as is")
        tmp.replace(dest)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    voice_path = ROOT / "data" / "shorts_voice.json"
    if not voice_path.exists():
        raise SystemExit("[sfx] run shorts_voice.py first")
    voice = json.loads(voice_path.read_text(encoding="utf-8"))
    parts = voice["parts"]
    total = float(voice.get("seconds") or 20.0)

    out = ROOT / "data" / "shorts_sfx"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.mp3"):
        old.unlink()

    if not key():
        log("no ELEVENLABS_API_KEY, so the video will have no sound design")
        log("the Short still gets made, it is just quieter")
        return 0

    # Each cue keeps its own time on the clip's timeline, spread across it, then
    # nudged into whichever line is speaking so it never falls in a gap. The
    # nudge only moves a cue by a fraction of the line, so cues that started
    # apart stay apart: collapsing them onto one instant sounds like a single
    # stacked hit rather than a designed sequence.
    plan: list[dict] = []
    if parts:
        spans = [(float(p.get("start") or 0.0),
                  float(p.get("start") or 0.0)
                  + float(p.get("seconds") or 0.0)) for p in parts]

        span_cues = max(CUES[-1][3], 0.001)
        raw = []
        for name, text, kind, at in CUES:
            if at >= total:
                continue
            at = at / span_cues * max(total - 0.5, 0.5)
            raw.append([name, text, kind, at])

        # Nudging can push a cue past the next one, so the order is fixed
        # afterwards. Two hits within a tenth of a second of each other are
        # one sound with extra work, not a sequence.
        raw.sort(key=lambda r: r[3])
        spaced: list[float] = []
        for r in raw:
            ts = r[3]
            if spaced and ts - spaced[-1] < 0.22:
                ts = spaced[-1] + 0.22
            spaced.append(ts)

        for (name, text, kind, _), ts in zip(raw, spaced):
            plan.append({
                "name": name, "text": text, "kind": kind,
                "at": round(min(ts, max(total - 0.2, 0.1)), 2),
                "line": next((p["text"][:48] for p, (b0, b1) in
                              zip(parts, spans) if b0 <= ts < b1),
                             parts[0]["text"][:48])})

    log(f"generating {len(plan)} cues over {total:.1f}s")
    made = 0
    for cue in plan:
        dest = out / f"{cue['name']}.mp3"
        if sound_effect(cue["text"], dest):
            made += 1
            log(f"  {cue['name']:8} at {cue['at']:5.2f}s")
        elif OUT_OF_CREDITS:
            log(f"  {cue['name']:8} skipped, out of credits")
        else:
            log(f"  {cue['name']:8} skipped")

    bed = out / "bed.mp3"
    if music(bed, int(total)):
        log(f"music bed {total:.0f}s")
    elif OUT_OF_CREDITS:
        log("no music bed, out of credits")
    else:
        log("no music bed this time")

    (ROOT / "data" / "shorts_sfx.json").write_text(
        json.dumps({"cues": [c for c in plan if (out / f"{c['name']}.mp3")
                             .exists()],
                    "bed": bed.exists(), "seconds": total,
                    "out_of_credits": bool(OUT_OF_CREDITS)},
                   indent=2), encoding="utf-8")

    if made == 0:
        log("no sound design this time; the video still gets made")
    else:
        log(f"{made} cues ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())