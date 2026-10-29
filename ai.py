"""One HTTP path for the AI calls.

The backend is whichever key exists: OpenRouter first, Groq second. Both speak
the OpenAI wire format, so only the base URL and the attribution headers differ.

Groq sits behind Cloudflare, and Cloudflare answers Python's urllib with
"error code: 1010" (blocked by browser signature) even though the API key is
perfectly valid. requests presents a normal header set, so all model calls go
through here instead.
"""
from __future__ import annotations

import json
import os


def backend() -> tuple[str, str]:
    """(base, key) for the live backend. OpenRouter wins when both exist."""
    or_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if or_key:
        return "https://openrouter.ai/api/v1", or_key
    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if groq_key:
        return "https://api.groq.com/openai/v1", groq_key
    raise RuntimeError("OPENROUTER_API_KEY (or GROQ_API_KEY) is not set")


def key() -> str:
    return backend()[1]


def _headers() -> dict:
    base, _ = backend()
    h = {
        "Authorization": f"Bearer {key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    if "openrouter.ai" in base:
        h["HTTP-Referer"] = "https://tbougnar.github.io/Slingshot-Tools/"
        h["X-Title"] = "Slingshot Tools"
    else:
        # Groq's browser console origin; omitting it is what Cloudflare blocks.
        h["Origin"] = "https://console.groq.com"
        h["Referer"] = "https://console.groq.com/"
    return h


def _read(resp) -> bytes:
    """urllib does not decompress, so a gzipped reply has to be handled here.

    Without this the API answers with gzip (byte 0x8b) and every call dies with
    a decode error that looks nothing like the real problem.
    """
    import gzip as _gz
    import zlib as _zl
    raw = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc or raw[:2] == b"\x1f\x8b":
        try:
            raw = _gz.decompress(raw)
        except Exception:  # noqa: BLE001
            try:
                raw = _zl.decompress(raw, 16 + _zl.MAX_WBITS)
            except Exception:  # noqa: BLE001
                pass
    return raw


def post(path: str, payload: dict, timeout: int = 180) -> dict:
    import requests
    base, _ = backend()
    r = requests.post(base + path, headers=_headers(), data=json.dumps(payload),
                      timeout=timeout)
    if r.status_code != 200:
        # The provider explains refusals in the body (token limits, rate
        # limits, retired models). Losing that turns every fault into
        # "nothing came back".
        raise RuntimeError(f"ai {path} -> {r.status_code}: {r.text[:500]}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        raise RuntimeError(
            f"ai {path} returned non-JSON ({r.headers.get('Content-Type')}): "
            f"{r.text[:200]}") from None


def get(path: str, timeout: int = 60) -> dict:
    import requests
    base, _ = backend()
    r = requests.get(base + path, headers=_headers(), timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"ai {path} -> {r.status_code}: {r.text[:500]}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        # a body that is not JSON means something between us and the API
        # rewrote it; say so instead of failing later with a confusing parse error
        raise RuntimeError(
            f"ai {path} returned non-JSON ({r.headers.get('Content-Type')}): "
            f"{r.text[:200]}") from None


def models() -> list[str]:
    return sorted(m["id"] for m in get("/models").get("data", []))


def _groq_reasoning(model: str) -> bool:
    """Does this Groq model accept reasoning_effort?

    llama-3.3-70b-versatile and several others reject the field, so sending it
    to every Groq model broke a chat chain that was otherwise valid.
    """
    low = (model or "").lower()
    return any(s in low for s in ("gpt-oss", "qwen", "deepseek", "kimi",
                                  "reasoning"))


def chat(model: str, system: str, user: str, temperature: float = 0.2,
         max_tokens: int = 6000, reasoning: bool = False) -> str:
    payload = {
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if not reasoning and "api.groq.com" in backend()[0] \
            and _groq_reasoning(model):
        # Groq's reasoning models otherwise spend the budget thinking and
        # return a file that stops mid-way. OpenRouter rejects the field on
        # models that do not support it, so it is only sent to Groq, and only
        # to the models there that accept it.
        payload["reasoning_effort"] = "low"
    d = post("/chat/completions", payload)
    return d["choices"][0]["message"]["content"] or ""
