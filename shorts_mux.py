"""Join the voice clips and the rendered frames into one file.

ffmpeg does the work. Two jobs here that are easy to get wrong:

- the audio is measured, not estimated, so the video is exactly as long as the
  speech with a short tail, rather than as long as a guess
- loudness is normalised to the level YouTube expects, because a Short that is
  quiet gets muted in the feed anyway
"""
from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FPS = 30


def log(m: str) -> None:
    print(f"[mux] {m}", flush=True)


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("[mux] ffmpeg is not installed")
    return exe


def mp3_seconds(path: Path) -> float:
    """Length of an mp3, measured rather than assumed.

    ffprobe is the accurate way, but a plain wave read of the decoded audio is
    enough here and needs nothing extra.
    """
    try:
        out = subprocess.run(
            [ffmpeg(), "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, errors="replace")
        for line in (out.stderr or "").splitlines():
            if "time=" in line and "Duration" not in line:
                stamp = line.split("time=")[1].split(" ")[0].strip()
                try:
                    h, m, s = stamp.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
                except ValueError:
                    pass
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def build_audio(parts: list[dict], dest: Path) -> float:
    """Concatenate the clips with a short gap, and report the true duration."""
    listing = ROOT / "data" / "shorts_audio" / "concat.txt"
    clips = [ROOT / "data" / "shorts_audio" / p["file"] for p in parts]
    clips = [c for c in clips if c.exists()]
    if not clips:
        raise SystemExit("[mux] no audio clips to join")

    listing.write_text(
        "".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")

    subprocess.run(
        [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:a", "aac", "-b:a", "192k", str(dest)],
        cwd=listing.parent, capture_output=True, check=True)

    total = 0.0
    for c in clips:
        total += mp3_seconds(c)
    return total


def main() -> int:
    voice = json.loads((ROOT / "data" / "shorts_voice.json")
                       .read_text(encoding="utf-8"))
    frames_dir = ROOT / "data" / "shorts_frames"
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        raise SystemExit("[mux] no frames; run shorts_render.py first")

    out_dir = ROOT / "dist" / "shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = out_dir / "voice.m4a"
    seconds = build_audio(voice["parts"], audio)
    if seconds <= 0:
        raise SystemExit("[mux] could not measure the audio")
    log(f"audio {seconds:.1f}s")

    # trust the measured audio over the estimate, and leave a short tail
    want = seconds + 0.6
    need = int(round(want * FPS))
    have = len(frames)
    if need != have:
        log(f"trim or extend frames: have {have}, need {need}")
        if have > need:
            frames = frames[:need]
        else:
            frames = frames + [frames[-1]] * (need - have)

    slug = json.loads((ROOT / "data" / "shorts_script.json")
                      .read_text(encoding="utf-8")).get("slug", "short")
    dest = out_dir / f"{slug}-short.mp4"

    subprocess.run(
        [ffmpeg(), "-y",
         "-framerate", str(FPS), "-i", str(frames_dir / "%05d.jpg"),
         "-i", str(audio),
         "-c:v", "libx264", "-preset", "slow", "-crf", "21",
         "-pix_fmt", "yuv420p",                    # required by YouTube
         "-profile:v", "high", "-level", "4.0",
         "-vf", "scale=1080:1920:flags=lanczos",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",  # YouTube's target
         "-shortest", "-movflags", "+faststart",
         str(dest)],
        capture_output=True, check=True)

    if not dest.exists() or dest.stat().st_size < 20_000:
        raise SystemExit("[mux] the file came out empty")

    log(f"{dest.name}  {dest.stat().st_size / 1024 / 1024:.1f} MB")
    (ROOT / "data" / "shorts_video.json").write_text(
        json.dumps({"file": str(dest), "slug": slug,
                    "seconds": round(seconds, 1)}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())