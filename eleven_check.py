"""Say whether the configured ElevenLabs voice can actually be used.

A wrong voice id and an exhausted account look the same from inside the
pipeline: every line falls back to Edge and the video still gets made, so the
failure is easy to miss. The reason matters, though, because the fix is
different. An id from another account needs changing; a dead key needs paying.

    python eleven_check.py
"""
from __future__ import annotations

import json
import os
import sys

import shorts_voice as sv


def log(m: str) -> None:
    print(f"[eleven] {m}", flush=True)


def main() -> int:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        log("no API key")
        return 0

    want = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not want:
        log("no ELEVENLABS_VOICE_ID set")
        return 0

    voices = sv.list_voices()
    names = {v.get("voice_id"): (v.get("name") or "?") for v in voices}
    log(f"{len(voices)} voices on this account")
    for vid, name in sorted(names.items(), key=lambda kv: kv[1]):
        mark = " <- ELEVENLABS_VOICE_ID" if vid == want else ""
        log(f"  {vid}  {name}{mark}")

    if want in names:
        log(f"the configured voice {names[want]!r} is on this account")
        return 0

    # not in the account listing, but ElevenLabs will happily synthesise with
    # a public voice the listing hides, so ask before calling it wrong
    probe = sv._eleven_speak("Hello.", sv.ROOT / "data" / "eleven_probe.mp3")
    if probe and sv.ROOT.joinpath("data", "eleven_probe.mp3").exists():
        log("the configured voice works even though it is not listed")
        return 0

    log(f"voice {want} is not usable with this key: it is not on this "
        f"account, and speaking with it was refused")
    log("set ELEVENLABS_VOICE_ID to one of the ids listed above")
    return 0


if __name__ == "__main__":
    sys.exit(main())