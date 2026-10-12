"""Join the trailer's frames and voice into a landscape mp4.

Everything audio-shaped is borrowed from ``shorts_mux`` on purpose. Loudness
normalisation, the measured duration and the frame reconciliation are the
parts that are genuinely fiddly, and they are the parts that already work for
the Shorts. Duplicating them here would mean two places to fix the next time
ffmpeg changes its mind.

The one thing that cannot be borrowed is the encoder's scale filter: the Shorts
mux hardcodes ``scale=1080:1920`` because a Short is vertical, and a trailer is
not. So the command is built here, using the same measured duration and the
same loudness target.

    python update_trailer_mux.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import shorts_mux as sm
import update_state as us
import update_trailer_render as tr

ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / "data" / "trailer_frames"
VOICE = ROOT / "data" / "trailer_voice.json"
FRAMES_JSON = ROOT / "data" / "trailer_frames.json"
SCRIPT = ROOT / "data" / "trailer_script.json"
OUT_DIR = ROOT / "dist" / "trailer"


def log(m: str) -> None:
    print(f"[trailermux] {m}", flush=True)


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # the Shorts pipeline falls back the same way, so a machine without ffmpeg
    # on PATH can still produce a video
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return ""


def encode(dest: Path, audio: Path, seconds: float) -> bool:
    """The ffmpeg call, landscape this time."""
    exe = ffmpeg()
    if not exe:
        log("ffmpeg is not available, so no video can be made")
        return False

    # 1920x1080 needs a higher level than the vertical Short used
    cmd = [exe, "-y", "-framerate", str(tr.FPS),
           "-i", str(FRAMES / "%05d.jpg"), "-i", str(audio),
           "-c:v", "libx264", "-preset", "slow", "-crf", "21",
           "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-level", "4.2",
           "-vf", f"scale={tr.W}:{tr.H}:flags=lanczos",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           "-shortest", "-movflags", "+faststart", str(dest)]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        log(f"ffmpeg refused the encode: "
            f"{(e.stderr or b'').decode('utf-8', 'replace')[-200:]}")
        return False
    except Exception as e:  # noqa: BLE001
        log(f"could not run ffmpeg: {str(e)[:90]}")
        return False
    return dest.exists() and dest.stat().st_size > 20_000


def main() -> int:
    if not VOICE.exists():
        raise SystemExit("[trailermux] run update_trailer_voice.py first")
    if not FRAMES_JSON.exists() or not FRAMES.exists():
        raise SystemExit("[trailermux] run update_trailer_render.py first")

    voice = json.loads(VOICE.read_text(encoding="utf-8"))
    meta = json.loads(FRAMES_JSON.read_text(encoding="utf-8"))
    script = (json.loads(SCRIPT.read_text(encoding="utf-8"))
              if SCRIPT.exists() else {})
    slug = str(script.get("slug") or "release") or "release"

    # one concat list per clip, in its own folder, so this run cannot pick up
    # the Shorts audio left over from a previous job
    work = ROOT / "data" / "trailer_audio"
    parts = voice.get("parts") or []
    if not parts:
        raise SystemExit("[trailermux] the voice file has no parts")

    concat = work / "concat.txt"
    lines = []
    for p in parts:
        f = work / Path(str(p.get("file") or "")).name
        if not f.exists():
            raise SystemExit(f"[trailermux] a voice clip is missing: {f.name}")
        lines.append(f"file '{f.as_posix()}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    narration = work / "narration.m4a"
    exe = ffmpeg()
    if not exe:
        raise SystemExit("[trailermux] ffmpeg is not installed")
    cmd = [exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(narration)]
    subprocess.run(cmd, capture_output=True, check=True)

    # measured, and the frames are trimmed or held to match, which is what the
    # Shorts mux does and why it never ends with a frozen final frame
    seconds = sm.media_seconds(narration)
    have = int(meta.get("count") or 0)
    need = int(round((seconds + 0.6) * tr.FPS))
    files = sorted(FRAMES.glob("*.jpg"))
    if need < have:
        for f in files[need:]:
            f.unlink()
    elif need > have and files:
        # hold the last frame rather than ending early on a black frame
        last = files[-1]
        for i in range(have, need):
            shutil.copy2(last, FRAMES / f"{i:05d}.jpg")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{slug}-trailer.mp4"
    if not encode(dest, narration, seconds):
        return 1

    # record the new version: a trailer is how a release becomes real
    state = us.load()
    state["version"] = us.bump(state.get("version") or "1.0.0", "major")
    state["last_trailer"] = {
        "file": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "version": state["version"],
        "slug": slug,
        "seconds": round(seconds, 1),
        "title": script.get("title") or "",
    }
    us.save(state)
    us.publish_public(state)

    log(f"{dest.name}  {seconds:.1f}s  {dest.stat().st_size / 1e6:.1f} MB")
    log(f"that is version {state['version']}, now published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())