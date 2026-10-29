"""Prove the AI provider works, using a key you type once.

Why this exists: GitHub secrets cannot be read back, by design. But that only
matters if you need the old value. You do not. You make a new one, and the
old one becomes irrelevant.

This asks for a key at the terminal, uses it once, and forgets it. It is never
written to disk and never printed back. The backend is read from the key's own
prefix: ``sk-or-v1-`` is OpenRouter, ``gsk_`` is Groq.

    python groq_live_check.py
"""
from __future__ import annotations

import getpass
import json
import os
import urllib.error
import urllib.request

TIMEOUT = 45
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"

# The first model of each role's chain: builder, debug, chat. A job calls its
# first model on every run, so one of these failing is a real outage rather
# than a spare fallback being retired.
NEEDED = {
    "openrouter": ["poolside/laguna-s-2.1:free",
                   "nvidia/nemotron-3-ultra-550b-a55b:free",
                   "thinkingmachines/inkling:free"],
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b",
             "llama-3.3-70b-versatile"],
}


def log(m: str) -> None:
    print(f"\n[m] {m}", flush=True)


def backend_for(key: str) -> tuple[str, str]:
    """(name, base) from the key's prefix. Empty name when it is not a key."""
    if key.startswith("sk-or-v1-"):
        return "openrouter", OPENROUTER_BASE
    if key.startswith("gsk_"):
        return "groq", GROQ_BASE
    return "", ""


def call_chat(key: str, model: str, base: str = GROQ_BASE) -> tuple[bool, str]:
    """Ask for the smallest possible completion. Proves the key AND the model."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single "
                                                        "word: ok"}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    if "openrouter.ai" in base:
        headers["HTTP-Referer"] = "https://tbougnar.github.io/Slingshot-Tools/"
        headers["X-Title"] = "Slingshot Tools"
    req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                 headers=headers)
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


def main(key: str = "") -> int:
    # The key arrives as an argument rather than being read from the module
    # global. Assigning to _KEY here made it local to main, so the very first
    # line raised UnboundLocalError and the check never ran at all.
    key = key or _KEY

    log("this checks a key you type now. it is not stored or printed back.")

    if not key:
        log("no key given, so nothing was tested")
        return 1

    name, base = backend_for(key)
    if not name:
        log(f"that does not look like an API key, it starts "
            f"{key[:4]!r}. OpenRouter keys begin sk-or-v1-, Groq keys begin gsk_")
        print("\n    make a new OpenRouter one at "
              "https://openrouter.ai/keys")
        return 1

    needed = NEEDED[name]
    works = []
    for model in needed:
        passed, detail = call_chat(key, model, base)
        print(f"  {'PASS' if passed else 'FAIL'}  {detail}")
        if passed:
            works.append(model)
    key = None

    log("")
    if len(works) == len(needed):
        print(f"  all {len(needed)} models the repo uses first work.")
        print("")
        secret = "OPENROUTER_API_KEY" if name == "openrouter" else "GROQ_API_KEY"
        # The workflows read OPENROUTER_CHAT_MODEL from vars and
        # GROQ_CHAT_MODEL from secrets. Sending people to the wrong one left
        # the pin silently unset.
        where = "variable" if name == "openrouter" else "secret"
        var = "OPENROUTER_CHAT_MODEL" if name == "openrouter" else "GROQ_CHAT_MODEL"
        print(f"  Now set it for the scheduled runs ({name}):")
        print(f"    gh secret set {secret} --repo tbougnar/Slingshot-Tools")
        print("")
        print(f"  or pin the model explicitly with {var}:")
        print(f"    gh {where} set {var} --body {works[0]} \\")
        print("      --repo tbougnar/Slingshot-Tools")
        return 0

    if works:
        print(f"  only {len(works)} of {len(needed)} required models work, so "
              "a job that starts on a failing one will not run.")
        print("  Fix the failing model above, or pin a working one with:")
        secret = "OPENROUTER_API_KEY" if name == "openrouter" else "GROQ_API_KEY"
        where = "variable" if name == "openrouter" else "secret"
        var = "OPENROUTER_CHAT_MODEL" if name == "openrouter" else "GROQ_CHAT_MODEL"
        print(f"    gh secret set {secret} --repo tbougnar/Slingshot-Tools")
        print(f"    gh {where} set {var} --body {works[0]} \\")
        print("      --repo tbougnar/Slingshot-Tools")
        return 1

    print("  No model worked. Common causes:")
    print("    - the key was revoked, or belongs to another account")
    print("    - that IP is blocked; try a phone hotspot")
    print("    - the key has no quota or is rate limited")
    print("    - a free model was retired; check "
          "https://openrouter.ai/models")
    return 1


_KEY = ""


def _read() -> None:
    global _KEY
    _KEY = getpass.getpass("Paste an OpenRouter (sk-or-v1-...) or Groq "
                           "(gsk_...) API key (input is hidden): ").strip()
    if not _KEY:
        raise SystemExit("\n[m] no key given, so nothing was tested")


if __name__ == "__main__":
    # An exported key is used when the prompt is not interactive, so the same
    # script works in a terminal and in a CI step.
    _KEY = (os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("GROQ_API_KEY") or "").strip()
    if not _KEY:
        _read()
    try:
        raise SystemExit(main())
    finally:
        _KEY = ""
