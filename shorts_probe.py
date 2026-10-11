"""Find which ElevenLabs endpoints this key can actually reach.

Written because guessing paths cost two failed runs already. Each candidate is
tried and the exact status recorded, so the working one is found by evidence
rather than by another guess. Nothing is printed except statuses and ids.

    python shorts_probe.py
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.elevenlabs.io"


def call(label: str, path: str, method: str = "GET",
         body: dict | None = None) -> object | None:
    key = __import__("os").environ.get("ELEVENLABS_API_KEY", "").strip()
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"xi-api-key": key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8", "replace")
            print(f"  {r.status}  {label}")
            return raw
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:150]
        except Exception:  # noqa: BLE001
            pass
        print(f"  {e.code}  {label}   {detail}")
    except Exception as e:  # noqa: BLE001
        print(f"  ERR  {label}   {str(e)[:90]}")
    return None


def main() -> int:
    print("checking which endpoints this key can reach")
    print()
    print("identity and account:")
    call("GET /v1/user", "/v1/user")
    call("GET /v1/user/subscription", "/v1/user/subscription")
    print()
    print("voice listing:")
    for path in ("/v2/voices?page_size=5",
                 "/v1/voices",
                 "/v1/voices?page_size=5"):
        call(f"GET {path}", path)
    print()
    print("shared library (may not need a key at all):")
    for path in ("/v1/voices/shared",
                 "/v2/voices/shared"):
        call(f"GET {path}", path)
    print()
    print("text to speech with a stock voice id, to prove the key speaks:")
    call("POST /v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb (GEORGE)",
         "/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb",
         method="POST",
         body={"text": "testing one two three",
               "model_id": "eleven_multilingual_v2"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())