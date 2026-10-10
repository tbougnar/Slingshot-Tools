"""Prove the AI provider works, using a key you type once.

Why this exists: GitHub secrets cannot be read back, by design. But that only
matters if you need the old value. You do not. You make a new one, and the
old one becomes irrelevant.

This asks for a key at the terminal, uses it once, and forgets it. It is never
written to disk and never printed back.

    python groq_live_check.py
"""
from __future__ import annotations

import getpass
import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 45
MODELS = "https://api.groq.com/openai/v1/models"
CHAT = "https://api.groq.com/openai/v1/chat/completions"

# the models this repo actually calls, so a pass here means Friday can work
NEEDED = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


def log(m: str) -> None:
    print(f"\n[m] {m}", flush=True)


def call_chat(key: str, model: str) -> tuple[bool, str]:
    """Ask for the smallest possible completion. Proves the key AND the model."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single "
                                                        "word: ok"}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        CHAT, data=payload,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
        got = d["choices"][0]["message"]["content"].strip()
        return True, f"{model} replied {got!r}"
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
            msg = body.get("error", {}).get("message", "")[:110]
        except Exception:  # noqa: BLE001
            msg = ""
        if e.code == 401:
            return False, "the key was rejected (401)"
        if e.code == 429:
            return False, "rate limited or no quota (429)"
        return False, f"HTTP {e.code} {msg}".strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:90]


def main() -> int:
    key = _KEY
    _KEY = ""  # drop our reference before anything can print it

    log("this checks a key you type now. it is not stored or printed back.")

    if not key:
        log("no key given, so nothing was tested")
        return 1

    if not key.lower().startswith("gsk_"):
        log(f"that does not look like a Groq key, it starts "
            f"{key[:4]!r}. Groq keys begin gsk_")
        print("\n    make a new one at https://console.groq.com/keys")
        return 1

    works = []
    for model in NEEDED:
        passed, detail = call_chat(key, model)
        print(f"  {'PASS' if passed else 'FAIL'}  {detail}")
        if passed:
            works.append(model)
    key = None

    log("")
    if works:
        print(f"  {len(works)} of {len(NEEDED)} models the repo uses work.")
        if len(works) < len(NEEDED):
            print("  A missing model only matters if a job calls it. "
                  "Each script")
            print("  has its own default, so a partial result is usually "
                  "fine.")
        print("")
        print("  Now set it for Friday:")
        print("    gh secret set GROQ_API_KEY --repo tbougnar/Slingshot-Tools")
        print("")
        print("  or add GROQ_CHAT_MODEL to pin the model explicitly:")
        print("    gh variable set GROQ_CHAT_MODEL "
              f"--body {works[0]} \\")
        print("      --repo tbougnar/Slingshot-Tools")
        return 0

    print("  No model worked. Common causes:")
    print("    - the key was revoked, or belongs to another account")
    print("    - that IP is blocked; try a phone hotspot")
    print("    - the key has no quota or is rate limited")
    return 1


_KEY = ""


def _read() -> None:
    global _KEY
    _KEY = getpass.getpass("Paste a Groq API key (input is hidden): ").strip()
    if not _KEY:
        raise SystemExit("\n[m] no key given, so nothing was tested")


if __name__ == "__main__":
    _read()
    try:
        raise SystemExit(main())
    finally:
        _KEY = ""