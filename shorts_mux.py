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


def ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise SystemExit("[mux] ffprobe is not installed")
    return exe


def media_seconds(path: Path) -> float:
    """Exact length, read by ffprobe rather than parsed out of ffmpeg's log.

    ffmpeg's stderr format for the progress line has changed between releases,
    so scraping it breaks on a runner image update. ffprobe returns a number.
    """
    out = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, errors="replace")
    try:
        return float((out.stdout or "").strip())
    except ValueError:
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

    if not dest.exists() or dest.stat().st_size < 512:
        raise SystemExit("[mux] the joined audio came out empty")
    return media_seconds(dest)


def cue_times() -> dict:
    """When each cue fires, read from the plan shorts_sfx.py wrote."""
    p = ROOT / "data" / "shorts_sfx.json"
    if not p.exists():
        return {}
    try:
        return {c["name"]: float(c["at"])
                for c in json.loads(p.read_text(encoding="utf-8")).get("cues")
                or []}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def cue_gain(name: str) -> float:
    """Hits carry the ad, transitions carry it, UI ticks only punctuate.

    Left any louder and the mix fights the narration, which is worse than no
    sound design at all.
    """
    p = ROOT / "data" / "shorts_sfx.json"
    if p.exists():
        try:
            for c in json.loads(p.read_text(encoding="utf-8")).get("cues") or []:
                if c["name"] == name:
                    return {"hit": 0.55, "transition": 0.38,
                            "ui": 0.30}.get(c.get("kind", "ui"), 0.30)
        except (json.JSONDecodeError, OSError):
            pass
    return 0.30


def plan_has_bed() -> bool:
    p = ROOT / "data" / "shorts_sfx.json"
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("bed"))
    except (json.JSONDecodeError, OSError):
        return False


def cue_labels() -> list[str]:
    p = ROOT / "data" / "shorts_sfx.json"
    if not p.exists():
        return []
    try:
        return [c["name"] for c in
                (json.loads(p.read_text(encoding="utf-8")).get("cues") or [])
                if (ROOT / "data" / "shorts_sfx" / f"{c['name']}.mp3").exists()]
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def _run(cmd: list[str], what: str) -> None:
    """Run ffmpeg, showing its own complaint when it refuses.

    check=True on its own produces a bare CalledProcessError with the reason
    printed nowhere, which is how a filter typo costs twenty minutes.
    """
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        tail = (r.stderr or b"").decode("utf-8", "replace").strip()
        tail = "\n".join(tail.splitlines()[-14:])
        raise SystemExit(f"[mux] {what} failed:\n{tail}")


def mix_video(dest: Path, voice: Path) -> list[str]:
    """Lay the sound design under the finished video.

    Runs after the picture is done and never before, because frames are the
    expensive part and sound design may be missing, retimed or replaced. The
    video stream is copied rather than re-encoded, so this is fast and lossless.
    """
    cues = cue_labels()
    bed = plan_has_bed()
    if not (bed or cues):
        return ["sound design: none, voice only"]

    sfx = ROOT / "data" / "shorts_sfx"
    times = cue_times()

    # stage one: the design on its own, each cue delayed to its own timestamp
    # ffmpeg numbers inputs from 0, and this filtergraph has no video and no
    # voice in it, so the bed is input 0 and each cue follows. Off by one here
    # is rejected wholesale as an invalid file index.
    inputs: list[str] = []
    graph: list[str] = []
    outs: list[str] = []

    if bed:
        inputs += ["-i", str(sfx / "bed.mp3")]
        graph.append("[0:a]volume=0.13[bed]")
        outs.append("[bed]")

    for i, cue in enumerate(cues, start=len(inputs) // 2):
        ms = int(times.get(cue, 0.0) * 1000)
        inputs += ["-i", str(sfx / f"{cue}.mp3")]
        graph.append(f"[{i}:a]volume={cue_gain(cue)},"
                     f"adelay={ms}|{ms}[c{cue}]")
        outs.append(f"[c{cue}]")

    graph.append("".join(outs) +
                 f"amix=inputs={len(outs)}:duration=longest:"
                 f"normalize=0[design]")

    stem = dest.parent / "design.m4a"
    _run([ffmpeg(), "-y"] + inputs +
         ["-filter_complex", ";".join(graph), "-map", "[design]",
          "-c:a", "aac", "-b:a", "192k", str(stem)],
         "building the sound design stem")

    # stage two: narration over the design, normalised for the feed. loudnorm
    # has to live inside the complex graph, because ffmpeg refuses a simple
    # -af filter on a stream that came out of one.
    _run([ffmpeg(), "-y", "-i", str(dest), "-i", str(stem),
          "-i", str(voice),
          "-filter_complex",
          "[1:a]volume=1.0[bed];[bed][2:a]amix=inputs=2:duration=longest:"
          "normalize=0,alimiter=limit=0.95[mixed];"
          "[mixed]loudnorm=I=-14:TP=-1.5:LRA=11[out]",
          "-map", "0:v", "-map", "[out]",
          "-c:v", "copy",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
          "-movflags", "+faststart", str(dest)],
         "mixing narration over the design")

    what = f"{len(cues)} cue(s)" + (" plus a music bed" if bed else "")
    return [f"sound design: {what}"]


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
    (ROOT / "data" / "shorts_audio_seconds.json").write_text(
        json.dumps({"seconds": round(seconds, 3)}), encoding="utf-8")

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

    # the sound design is mixed in afterwards so it can be skipped, retimed or
    # replaced without re-rendering a single frame
    notes = mix_video(dest, audio)

    log(f"{dest.name}  {dest.stat().st_size / 1024 / 1024:.1f} MB")
    for n in notes:
        log(f"  {n}")
    (ROOT / "data" / "shorts_video.json").write_text(
        json.dumps({"file": str(dest), "slug": slug,
                    "seconds": round(seconds, 1)}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())