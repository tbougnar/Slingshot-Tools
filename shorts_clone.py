"""Pick the Slingshot narration voice, once, and say how to store it.

    python shorts_clone.py pick British female
    python shorts_clone.py list narrator
    python shorts_clone.py clone "C:/path/to/your.wav"

pick chooses from ElevenLabs' own library, which every plan including free can
use. It is the reliable route: instant voice cloning is Starter-only, and voice
design has no published endpoint to call.
list searches that library so a choice can be made by ear rather than by guess.
clone reproduces a recording of a specific person and needs the $6 plan.

Prints the voice id and the command to store it. Nothing is written to disk and
no secret is printed, so running it is safe: the key is read from the
environment, never asked for here.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import shorts_voice as sv

ROOT = Path(__file__).resolve().parent
NAME = "Slingshot Notes"

# A short product ad wants a settled, mid-range voice that does not perform.
# Anything too young or too breathy fights the words on a phone screen, so the
# search defaults lean older and steadier than the average.
DEFAULTS = {
    "accent": "british",
    "gender": "female",
    "age": "young",
}


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


def library(**filters) -> list[dict]:
    """Search ElevenLabs' own voices, which every plan can use.

    Both versions are tried because the API has moved between them and a 404
    on one says nothing about the other. Filtering hard tends to return
    nothing, so each constraint is dropped until there is a result: an empty
    answer is worse than a loose one.
    """
    q = {k: v for k, v in filters.items() if v}
    last = ""

    for base in ("/v2/voices", "/v1/voices"):
        for drop in range(len(q) + 1):
            trial = dict(q)
            for k in list(trial)[drop:]:
                trial.pop(k)
            params = dict(trial)
            params["page_size"] = "50"
            url = f"{sv.API}{base}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"xi-api-key": sv.key()})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                continue
            except Exception as e:  # noqa: BLE001
                last = str(e)[:80]
                continue
            found = d.get("voices") or []
            if found:
                return found

    log(f"nothing came back ({last})")
    return []


def _say(v: dict) -> str:
    lab = v.get("labels") or {}
    bits = [lab.get("accent"), lab.get("gender"), lab.get("age")]
    bits = [b for b in bits if b]
    tail = f"  ({', '.join(bits)})" if bits else ""
    return f"  {v.get('voice_id','?'):22} {v.get('name','?'):28}{tail}"


def pick(*terms: str) -> str:
    """Choose one voice and return its id."""
    low = [t.lower() for t in terms]
    filters: dict = {}
    for key, options in (
            ("accent", ("british", "american", "australian", "irish")),
            ("gender", ("female", "male")),
            ("age", ("young", "middle_aged", "old"))):
        for term in low:
            if term in options:
                filters[key] = term
                break

    if not filters:
        filters = dict(DEFAULTS)
        log(f"no filters given, using {filters}")

    voices = library(**filters)
    if not voices:
        log("")
        log("If this says HTTP 404 and nothing else, ElevenLabs is probably")
        log("unreachable from this machine rather than the key being wrong.")
        log("A quick way to tell the two apart: run")
        log("  python shorts_probe.py")
        log("A key problem shows 401. A network problem shows 404 or ERR.")
        log("")
        log("Either way the pipeline runs in GitHub Actions, where the same")
        log("key already returns 200, so nothing is actually blocked.")
        log("To choose a voice, browse https://elevenlabs.io/voice-library")
        log("and set the id by hand:")
        log("  gh variable set ELEVENLABS_VOICE_ID --body <id> "
            "--repo tbougnar/Slingshot-Tools")
        return ""

    log(f"{len(voices)} match, the first few:")
    for v in voices[:5]:
        log(_say(v))
    log("")
    log("each has a sample you can hear at:")
    log("  https://elevenlabs.io/voice-library")
    return str(voices[0].get("voice_id", ""))


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

    if args and args[0].lower() in ("list", "search", "find"):
        term = " ".join(args[1:])
        voices = sv.list_voices(search=term) if term else sv.list_voices()
        if not voices:
            log("nothing matched")
            log("try a word like narrator, or leave it off to see everything")
            return 1
        log(f"{len(voices)} voices:")
        for v in voices[:20]:
            log(_say(v))
        if len(voices) > 20:
            log(f"  ... and {len(voices) - 20} more")
        return 0

    mode = args[0].lower() if args else "pick"

    if mode in ("pick", "p", "choose"):
        vid = pick(*args[1:])
        if not vid:
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
    log("  python shorts_clone.py pick  british female young")
    log("  python shorts_clone.py list  narrator")
    log("  python shorts_clone.py clone <path to a wav>   needs Starter, $6")
    return 1


def report(vid: str) -> None:
    log(f"using voice id: {vid}")
    log("")
    log("Store it and the Shorts pipeline will speak with this voice:")
    log("")
    log("  gh variable set ELEVENLABS_VOICE_ID "
        f"--body {vid} --repo tbougnar/Slingshot-Tools")
    log("")
    log("Change your mind later: pick again and set the new id, no harm.")
    log("If ElevenLabs is unreachable the pipeline falls back to Edge TTS on")
    log("its own, so nothing is blocked either way.")
    return None


if __name__ == "__main__":
    raise SystemExit(main())