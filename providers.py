"""One place that talks to any model provider.

Groq is the default because it is the key this project already has, but the
provider is chosen by whichever credentials exist. Adding a provider means
adding one function and one env var, not touching the callers.

Every provider is asked to behave identically: send a system prompt and a user
prompt, get text back. None of the rest of the pipeline knows or cares which
one answered.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

TIMEOUT = 180
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")


def _post(url: str, payload: dict, headers: dict, timeout: int = TIMEOUT) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "gzip, deflate")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        raise RuntimeError(f"non-JSON reply: {raw[:200]}") from None


def _get(url: str, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Accept", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ----------------------------------------------------------------- providers
def groq_available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def groq_models() -> list[str]:
    key = os.environ["GROQ_API_KEY"].strip()
    d = _get("https://api.groq.com/openai/v1/models",
             {"Authorization": f"Bearer {key}"})
    out = sorted(m["id"] for m in d.get("data", []))
    # only these can chat: the rest are classifiers and audio
    chat = [m for m in out if any(s in m for s in
                                  ("gpt-oss", "qwen", "llama-3.3", "kimi", "mistral"))]
    return chat or out


def groq_chat(model: str, system: str, user: str, temperature: float,
              max_tokens: int) -> str:
    key = os.environ["GROQ_API_KEY"].strip()
    payload = {"model": model, "temperature": temperature,
               "max_tokens": max_tokens, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    d = _post("https://api.groq.com/openai/v1/chat/completions", payload,
              {"Authorization": f"Bearer {key}"})
    return d["choices"][0]["message"]["content"] or ""


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def gemini_models() -> list[str]:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")).strip()
    d = _get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", {})
    out = []
    for m in d.get("models", []):
        name = m.get("name", "")
        if "generateContent" in str(m.get("supportedGenerationMethods", [])):
            out.append(name.split("/")[-1])
    return sorted(out)


def gemini_chat(model: str, system: str, user: str, temperature: float,
                max_tokens: int) -> str:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")).strip()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature,
                             "maxOutputTokens": max_tokens},
    }
    d = _post(url, payload, {})
    parts = (d.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def openrouter_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def openrouter_models() -> list[str]:
    key = os.environ["OPENROUTER_API_KEY"].strip()
    d = _get("https://openrouter.ai/api/v1/models",
             {"Authorization": f"Bearer {key}"})
    return sorted(m["id"] for m in d.get("data", []))


def openrouter_chat(model: str, system: str, user: str, temperature: float,
                    max_tokens: int) -> str:
    key = os.environ["OPENROUTER_API_KEY"].strip()
    payload = {"model": model, "temperature": temperature,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    d = _post("https://openrouter.ai/api/v1/chat/completions", payload,
              {"Authorization": f"Bearer {key}",
               "HTTP-Referer": "https://tbougnar.github.io/Slingshot-Tools/",
               "X-Title": "Slingshot Tools"})
    return d["choices"][0]["message"]["content"] or ""


def cerebras_available() -> bool:
    return bool(os.environ.get("CEREBRAS_API_KEY"))


def cerebras_models() -> list[str]:
    key = os.environ["CEREBRAS_API_KEY"].strip()
    d = _get("https://api.cerebras.ai/v1/models",
             {"Authorization": f"Bearer {key}"})
    return sorted(m["id"] for m in d.get("data", []))


def cerebras_chat(model: str, system: str, user: str, temperature: float,
                  max_tokens: int) -> str:
    key = os.environ["CEREBRAS_API_KEY"].strip()
    payload = {"model": model, "temperature": temperature,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    d = _post("https://api.cerebras.ai/v1/chat/completions", payload,
              {"Authorization": f"Bearer {key}"})
    return d["choices"][0]["message"]["content"] or ""


# ------------------------------------------------------------------ registry
# The debugger team stays on Groq so it keeps that allowance to itself. Set
# DEBUG_PROVIDER to move it.
DEBUG_PROVIDER = (os.environ.get("DEBUG_PROVIDER") or "groq").strip().lower()

# Order matters: the first provider with credentials wins.
PROVIDERS = [
    ("gemini", gemini_available, gemini_models, gemini_chat),
    ("cerebras", cerebras_available, cerebras_models, cerebras_chat),
    ("openrouter", openrouter_available, openrouter_models, openrouter_chat),
    ("groq", groq_available, groq_models, groq_chat),
]

# Preferences per job. The builder wants the strongest coder, the debugger team
# is happy with anything that answers.
ROLE_MODEL_HINTS = {
    "builder": ("gemini", "cerebras", "openrouter", "groq"),
    "debug": ("gemini", "cerebras", "groq", "openrouter"),
}


def active() -> tuple:
    for name, avail, models, chat in PROVIDERS:
        if avail():
            return name, models, chat
    raise SystemExit("no model provider is configured")


def provider_name() -> str:
    return active()[0]


def for_role(role: str) -> tuple:
    """Provider for a job, kept strictly separate.

    The builder and the debugger team must not share an allowance. The builder
    takes the best coder available elsewhere; debugging keeps Groq to itself,
    because patching is many small calls and the builder's job is one large
    one. Sharing them is what starved the debugger team and stopped any app
    from ever passing QA.
    """
    if role == "builder":
        # anything that is not the debugger's provider, best coder first
        for name, avail, models_fn, send in PROVIDERS:
            if name == DEBUG_PROVIDER:
                continue
            if avail():
                return name, models_fn, send
        return active()

    # debugging: prefer the dedicated provider, then anything else
    for name, avail, models_fn, send in PROVIDERS:
        if name == DEBUG_PROVIDER and avail():
            return name, models_fn, send
    return active()


def models(role: str = "debug") -> list[str]:
    name, list_models, _ = for_role(role)
    try:
        found = list_models()
    except Exception as e:  # noqa: BLE001
        print(f"[ai] {name} could not list models: {str(e)[:120]}")
        return []
    if not found:
        return []
    return found[:3] if role == "debug" else found[:1]


def chat(model: str, system: str, user: str, temperature: float = 0.2,
         max_tokens: int = 4000, tries: int = 2, role: str = "debug") -> str:
    _, _, send = for_role(role)
    last = ""
    for attempt in range(tries):
        try:
            out = send(model, system, user, temperature, max_tokens)
            if out:
                return out
            last = "empty reply"
        except urllib.error.HTTPError as e:
            last = f"{e.code}: {e.read().decode()[:200]}"
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
        if "429" in last or "Rate limit" in last:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(last or "no reply")


if __name__ == "__main__":
    print("active provider:", provider_name())
    for m in models("builder"):
        print("  builder model:", m)
    for m in models("debug"):
        print("  debugger model:", m)