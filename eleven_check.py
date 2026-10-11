"""Say whether the configured ElevenLabs voice can actually be used.

A wrong voice id and an exhausted account look the same from inside the
pipeline: every line falls back to Edge and the video still gets made, so the
failure is easy to miss. The reason matters, though, because the fix is
different. An id from another account needs changing; a dead key needs paying.

The voice listing cannot settle it on its own, because a key that is not
allowed to list reports no voices at all rather than an error. So the check
speaks with a public voice that belongs to nobody in particular: if that
works, the key is healthy and the problem is the configured id.

    python eleven_check.py
"""
from __future__ import annotations

import os
import sys
import urllib.error

import shorts_voice as sv

# a stock public voice, used only to prove the key itself still works
KNOWN_GOOD = "21m00Tcm4TlvDq8ikWAM"


def log(m: str) -> None:
    print(f"[eleven] {m}", flush=True)


def speaks(voice_id: str) -> tuple[bool, int]:
    """One short line through the real synthesis path.

    Returns the HTTP code too, because the difference matters: 401 is a voice
    or key the account cannot use, 402 is an account that simply has no
    credits left. They need opposite fixes and read identically if flattened.
    """
    dest = sv.ROOT / "data" / "eleven_probe.mp3"
    dest.unlink(missing_ok=True)
    try:
        sv.ELEVEN_VOICE_ID = voice_id
        sv._eleven_speak("Hello.", dest)
    except urllib.error.HTTPError as e:
        dest.unlink(missing_ok=True)
        return False, e.code
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        log(f"  {voice_id} failed: {str(e)[:90]}")
        return False, 0
    ok = dest.exists() and dest.stat().st_size > 1024
    dest.unlink(missing_ok=True)
    return ok, 200 if ok else 0


def main() -> int:
    if not os.environ.get("ELEVENLABS_API_KEY", "").strip():
        log("no API key")
        return 0

    want = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not want:
        log("no ELEVENLABS_VOICE_ID set")
        return 0

    # does the key work at all?
    healthy, code = speaks(KNOWN_GOOD)
    if not healthy:
        if code == 402:
            log(f"HTTP 402 on a stock public voice: this account has no "
                f"credits left, so nothing will synthesise")
            log("top the account up, or the pipeline keeps using the Edge "
                "voice and the Shorts ship with it")
            return 0
        log(f"the key cannot synthesise with a stock public voice either "
            f"(HTTP {code or 'error'}), so the key itself is the problem")
        return 0
    log(f"the key is healthy (stock voice {KNOWN_GOOD} synthesised)")

    voices = sv.list_voices()
    names = {v.get("voice_id"): (v.get("name") or "?") for v in voices}
    log(f"the account lists {len(names)} voice(s)"
        + ("" if names else " (listing unavailable on this plan)"))
    for vid, name in sorted(names.items(), key=lambda kv: kv[1]):
        mark = " <- ELEVENLABS_VOICE_ID" if vid == want else ""
        log(f"  {vid}  {name}{mark}")

    works, code = speaks(want)
    if works:
        log(f"the configured voice {want} works")
        return 0

    log(f"voice {want} was refused by this key (HTTP {code or 'error'}), so it "
        f"belongs to a different ElevenLabs account or was deleted")
    if names:
        log("set ELEVENLABS_VOICE_ID to one of the ids listed above, or use "
            "the key for the account that owns that voice")
    else:
        log("this plan cannot list voices, so the id has to be copied from "
            "the ElevenLabs site for this same account")
    return 0


if __name__ == "__main__":
    sys.exit(main())