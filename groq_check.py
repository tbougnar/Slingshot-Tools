"""Report why Groq may be refusing calls, without leaking the key."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MODELS = "https://api.groq.com/openai/v1/models"
CHAT = "https://api.groq.com/openai/v1/chat/completions"


def show(label: str, url: str, payload: dict | None = None) -> int:
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + os.environ.get("GROQ_API_KEY", ""))
    req.add_header("Content-Type", "application/json")
    if payload:
        req.data = json.dumps(payload).encode()
        req.method = "POST"
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()
            print(f"{label}: HTTP {r.status}")
            try:
                d = json.loads(body)
                ids = [m["id"] for m in d.get("data", [])]
                if ids:
                    print(f"{label}: {len(ids)} models available")
                    for i in sorted(ids):
                        print("   -", i)
                else:
                    print(f"{label}: ok, response {body[:200]}")
            except Exception:  # noqa: BLE001
                print(f"{label}: {body[:200]}")
            return r.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:600]
        print(f"{label}: HTTP {e.code} {e.reason}")
        print(f"{label}: body -> {detail}")
        return e.code
    except Exception as e:  # noqa: BLE001
        print(f"{label}: network error {type(e).__name__}: {str(e)[:200]}")
        return 0


def main() -> int:
    key = os.environ.get("GROQ_API_KEY", "")
    print("key present:", bool(key), "length:", len(key),
          "prefix:", (key[:8] + "...") if key else "none")
    if not key:
        return 1
    a = show("models", MODELS)
    b = show("chat", CHAT, {"model": "llama-3.3-70b-versatile",
                           "messages": [{"role": "user", "content": "say ok"}],
                           "max_tokens": 5})
    return 0 if (a == 200 and b == 200) else 1


if __name__ == "__main__":
    raise SystemExit(main())