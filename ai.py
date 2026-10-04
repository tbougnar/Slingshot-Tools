"""One HTTP path for the AI calls.

Groq sits behind Cloudflare, and Cloudflare answers Python's urllib with
"error code: 1010" (blocked by browser signature) even though the API key is
perfectly valid. requests presents a normal header set, so all model calls go
through here instead.
"""
from __future__ import annotations

import json
import os
import urllib.error

BASE = "https://api.groq.com/openai/v1"

# A real browser's header set. Nothing here is a secret.
HEADERS = {
    "Authorization": "Bearer {key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Origin": "https://console.groq.com",
    "Referer": "https://console.groq.com/",
}


def key() -> str:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if not k:
        raise RuntimeError("GROQ_API_KEY is not set")
    return k


def _headers() -> dict:
    return {k: v.format(key=key()) if "{key}" in v else v for k, v in HEADERS.items()}


def post(path: str, payload: dict, timeout: int = 180) -> dict:
    import requests
    r = requests.post(BASE + path, headers=_headers(), data=json.dumps(payload),
                      timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"groq {path} -> {r.status_code}: {r.text[:400]}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        raise RuntimeError(
            f"groq {path} returned non-JSON ({r.headers.get('Content-Type')}): "
            f"{r.text[:200]}") from None


def get(path: str, timeout: int = 60) -> dict:
    import requests
    r = requests.get(BASE + path, headers=_headers(), timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"groq {path} -> {r.status_code}: {r.text[:400]}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        # a body that is not JSON means something between us and the API
        # rewrote it; say so instead of failing later with a confusing parse error
        raise RuntimeError(
            f"groq {path} returned non-JSON ({r.headers.get('Content-Type')}): "
            f"{r.text[:200]}") from None


def models() -> list[str]:
    return sorted(m["id"] for m in get("/models").get("data", []))


def chat(model: str, system: str, user: str, temperature: float = 0.2,
         max_tokens: int = 6000, reasoning: bool = False) -> str:
    payload = {
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if not reasoning:
        # reasoning models otherwise spend the budget thinking and return a
        # file that stops mid-way
        payload["reasoning_effort"] = "low"
    d = post("/chat/completions", payload)
    return d["choices"][0]["message"]["content"] or ""