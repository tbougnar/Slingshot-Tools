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
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.elevenlabs.io/v1"

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
            detail = e.read().decode("utf-8", "replace")[:120]
        except Exception:  # noqa: BLE001
            detail = ""
        log(f"{path} refused: HTTP {e.code} {detail}")
    except Exception as e:  # noqa: BLE001
        log(f"{path} failed: {str(e)[:80]}")
    return None


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


def music(dest: Path, seconds: int) -> bool:
    raw = _post("/music", {
        "prompt": MUSIC_PROMPT,
        "music_length_ms": max(5000, min(seconds * 1000, 120_000)),
    }, timeout=240)
    if not raw or len(raw) < 4096:
        return False
    dest.write_bytes(raw)
    return True


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

    # a cue lands on a real moment in the voice, not on a guess
    plan: list[dict] = []
    for name, text, kind, at in CUES:
        if at >= total:
            continue
        # nearest line start, so effects land with the words they sit under
        when = min(parts, key=lambda p: abs(float(p.get("start") or 0.0) - at))
        ts = float(when.get("start") or 0.0)
        plan.append({"name": name, "text": text, "kind": kind,
                     "at": round(ts, 2), "line": when["text"][:48]})

    log(f"generating {len(plan)} cues over {total:.1f}s")
    made = 0
    for cue in plan:
        dest = out / f"{cue['name']}.mp3"
        if sound_effect(cue["text"], dest):
            made += 1
            log(f"  {cue['name']:8} at {cue['at']:5.2f}s")
        else:
            log(f"  {cue['name']:8} skipped")

    bed = out / "bed.mp3"
    if music(bed, int(total)):
        log(f"music bed {total:.0f}s")
    else:
        log("no music bed this time")

    (ROOT / "data" / "shorts_sfx.json").write_text(
        json.dumps({"cues": [c for c in plan if (out / f"{c['name']}.mp3")
                             .exists()],
                    "bed": bool(bed.exists()), "seconds": total},
                   indent=2), encoding="utf-8")
    log(f"{made} cues ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())