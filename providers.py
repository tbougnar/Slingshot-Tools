"""One place that talks to any model provider.

OpenRouter is the default: it is the key this project runs on. Groq stays as a
drop-in fallback so an existing .env or GitHub secret keeps working, and the
other providers are still registered. Adding a provider means adding one
function and one env var, not touching the callers.

Every provider is asked to behave identically: send a system prompt and a user
prompt, get text back. None of the rest of the pipeline knows or cares which
one answered.

Two things live here that callers should use instead of hard-coding a model id:

  compat()          which OpenAI-compatible backend is live, its base URL, key
                    and free-model chains
  model_chain()     the models to try, best first, for a job
  best_model()      one safe model id for a job

A model id from the other backend is the failure this prevents: sending a Groq
id to OpenRouter is a 404, and sending an OpenRouter id to Groq is a 404 too.
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


def _post(url: str, payload: dict, headers: dict, timeout: int = TIMEOUT) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "identity")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = _read(r).decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        raise RuntimeError(f"non-JSON reply: {raw[:200]}") from None


def _account(d: dict, model: str, provider: str) -> None:
    """Providers report usage; record it so the run knows its budget."""
    try:
        import tokenmeter
    except ImportError:
        return
    u = d.get("usage") or {}
    tokenmeter.add(int(u.get("prompt_tokens") or 0),
                   int(u.get("completion_tokens") or 0), model, provider)


def _account_gemini(d: dict, model: str) -> None:
    try:
        import tokenmeter
    except ImportError:
        return
    m = d.get("usageMetadata") or {}
    tokenmeter.add(int(m.get("promptTokenCount") or 0),
                   int(m.get("candidatesTokenCount") or 0), model, "gemini")


def _get(url: str, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Accept", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(_read(r).decode("utf-8", "replace"))


# ------------------------------------------------- OpenAI-compatible backends
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"

# Free OpenRouter models, best first. A daily cap on one model must never kill
# a run, so every job has a chain and the caller walks it.
OPENROUTER_CHAINS = {
    "builder": ("poolside/laguna-s-2.1:free",
                "recursive/flint-v1.0:free",
                "thinkingmachines/inkling:free"),
    "debug": ("nvidia/nemotron-3-ultra-550b-a55b:free",
              "cohere/north-mini-code:free",
              "poolside/laguna-xs-2.1:free"),
    "chat": ("thinkingmachines/inkling:free",
             "dots-studio/dots-3-note-preview:free",
             "nvidia/nemotron-3-ultra-550b-a55b:free"),
}
GROQ_CHAINS = {
    "builder": ("openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
    "debug": ("qwen/qwen3.8-27b", "openai/gpt-oss-20b"),
    "chat": ("qwen/qwen3.8-27b", "llama-3.3-70b-versatile"),
}
ROLES = ("builder", "debug", "chat")


def compat() -> tuple[str, str, str, dict]:
    """The OpenAI-compatible backend: (name, base, key, chains).

    OpenRouter wins whenever its key exists. Groq is only reached when the
    OpenRouter key is missing, so adding the new secret cannot break a box that
    still has the old one.
    """
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if key:
        return "openrouter", OPENROUTER_BASE, key, OPENROUTER_CHAINS
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if key:
        return "groq", GROQ_BASE, key, GROQ_CHAINS
    raise SystemExit("no model provider is configured")


def configured() -> bool:
    """True when the backend this module can actually talk to is configured.

    This used to return True for a Gemini, Google or Cerebras key, none of
    which compat() can select. Callers believed a model was available and then
    model_chain() raised SystemExit, which their ``except Exception`` did not
    catch, so one stray key killed a whole job. Report only the backends that
    are real here.
    """
    return bool((os.environ.get("OPENROUTER_API_KEY") or "").strip()
                or (os.environ.get("GROQ_API_KEY") or "").strip())


def model_chain(role: str = "chat") -> list[str]:
    """Model ids to try, best first, for this job on the active backend."""
    name, _, _, chains = compat()
    chain = list(chains.get(role) or chains["chat"])
    pin = "OPENROUTER_CHAT_MODEL" if name == "openrouter" else "GROQ_CHAT_MODEL"
    pinned = (os.environ.get(pin) or "").strip()
    if pinned:
        chain = [pinned] + [m for m in chain if m != pinned]
    return chain


def default_model(role: str = "chat") -> str:
    return model_chain(role)[0]


def _is_model_not_found(code: int, body: str) -> bool:
    low = (body or "").lower()
    return code == 404 or "model_not_found" in low or "not a valid model" in low


def _is_daily_cap(body: str) -> bool:
    low = (body or "").lower()
    return any(s in low for s in ("free-models-per-day", "per-day", "per day",
                                  "daily limit", "tokens per day", "tpd"))


# ----------------------------------------------------------------- providers
# A key that is present but only whitespace is not a key. compat() already
# strips, so an unstripped check here could choose a provider that then fails
# with an empty credential.
def groq_available() -> bool:
    return bool((os.environ.get("GROQ_API_KEY") or "").strip())


def groq_models() -> list[str]:
    key = os.environ["GROQ_API_KEY"].strip()
    d = _get(f"{GROQ_BASE}/models",
             {"Authorization": f"Bearer {key}"})
    out = sorted(m["id"] for m in d.get("data", []))
    # only these can chat: the rest are classifiers and audio
    chat = [m for m in out if any(s in m for s in
                                  ("gpt-oss", "qwen", "llama-3.3", "kimi", "mistral"))]
    return chat or out


def _groq_reasoning(model: str) -> bool:
    """Does this Groq model accept reasoning_effort?

    llama-3.3-70b-versatile does not, and sending the field made an otherwise
    valid chat chain fail. The reasoning models are the ones that need it.
    """
    low = (model or "").lower()
    return any(s in low for s in ("gpt-oss", "qwen", "deepseek", "kimi",
                                  "reasoning"))


def groq_chat(model: str, system: str, user: str, temperature: float,
              max_tokens: int) -> str:
    key = os.environ["GROQ_API_KEY"].strip()
    payload = {"model": model, "temperature": temperature,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    if _groq_reasoning(model):
        payload["reasoning_effort"] = "low"
    d = _post(f"{GROQ_BASE}/chat/completions", payload,
              {"Authorization": f"Bearer {key}"})
    _account(d, model, "groq")
    return d["choices"][0]["message"]["content"] or ""


def gemini_available() -> bool:
    return bool((os.environ.get("GEMINI_API_KEY") or "").strip()
                or (os.environ.get("GOOGLE_API_KEY") or "").strip())


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
    _account_gemini(d, model)
    return "".join(p.get("text", "") for p in parts)


def openrouter_available() -> bool:
    return bool((os.environ.get("OPENROUTER_API_KEY") or "").strip())


def openrouter_models() -> list[str]:
    key = os.environ["OPENROUTER_API_KEY"].strip()
    d = _get(f"{OPENROUTER_BASE}/models",
             {"Authorization": f"Bearer {key}"})
    return sorted(m["id"] for m in d.get("data", []))


def openrouter_chat(model: str, system: str, user: str, temperature: float,
                    max_tokens: int) -> str:
    key = os.environ["OPENROUTER_API_KEY"].strip()
    payload = {"model": model, "temperature": temperature,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    d = _post(f"{OPENROUTER_BASE}/chat/completions", payload,
              {"Authorization": f"Bearer {key}",
               "HTTP-Referer": "https://tbougnar.github.io/Slingshot-Tools/",
               "X-Title": "Slingshot Tools"})
    _account(d, model, "openrouter")
    return d["choices"][0]["message"]["content"] or ""


def cerebras_available() -> bool:
    return bool((os.environ.get("CEREBRAS_API_KEY") or "").strip())


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
    _account(d, model, "cerebras")
    return d["choices"][0]["message"]["content"] or ""


# ------------------------------------------------------------------ registry
# Roles do NOT get separate providers. They used to: with an OpenRouter key and
# a Groq key both present, the builder was told to use Groq while its model ids
# came from the OpenRouter chain, so every builder call was a 404 on a model id
# the other backend had never heard of. The chain in providers.py already gives
# each job several models and fails over on a 404 or a per-day cap, which is
# what the separation was trying to buy.

# Order matters: the first provider with credentials wins.
PROVIDERS = [
    ("openrouter", openrouter_available, openrouter_models, openrouter_chat),
    ("gemini", gemini_available, gemini_models, gemini_chat),
    ("cerebras", cerebras_available, cerebras_models, cerebras_chat),
    ("groq", groq_available, groq_models, groq_chat),
]


def _by_name(name: str):
    for entry in PROVIDERS:
        if entry[0] == name:
            return entry
    return None


def _pick(names, skip: str = "") -> tuple | None:
    for name in names:
        if name == skip:
            continue
        entry = _by_name(name)
        if entry and entry[1]():
            return name, entry[2], entry[3]
    return None


def active() -> tuple:
    for name, avail, models_fn, chat_fn in PROVIDERS:
        if avail():
            return name, models_fn, chat_fn
    raise SystemExit("no model provider is configured")


def provider_name() -> str:
    return active()[0]


def for_role(role: str) -> tuple:
    """The live backend for a job. One backend, so ids and transport agree.

    ``role`` is still accepted because callers pass it and because the model
    chain is per role; the transport is whichever backend owns that chain.
    """
    entry = _by_name(compat()[0])
    if entry and entry[1]():
        return entry[0], entry[2], entry[3]
    return active()


def models(role: str = "debug") -> list[str]:
    name, list_models, _ = for_role(role)
    chain = model_chain(role)
    try:
        found = list_models()
    except Exception as e:  # noqa: BLE001
        print(f"[ai] {name} could not list models: {str(e)[:120]}")
        found = []
    if not found:
        return chain[:3] if role == "debug" else chain[:1]
    if name == "openrouter":
        # The catalogue is hundreds of ids, nearly all paid. Only the
        # configured free chain is affordable, so that is what callers get.
        usable = [m for m in chain if m in found]
        if usable:
            return usable[:3] if role == "debug" else usable[:1]
        free = [m for m in found if m.endswith(":free")]
        if free:
            return free[:3]
        return chain[:3]
    return found[:3] if role == "debug" else found[:1]


def best_model(role: str = "debug") -> str:
    """One model id that is safe to send for this job."""
    got = models(role)
    return got[0] if got else model_chain(role)[0]


def _rate_limit_wait(attempt: int) -> int:
    """How long to sit out a 429.

    Groq's limit is on tokens per minute, so waiting ten seconds just spends
    another request inside the same window. Wait out the window the meter is
    actually using, and a little past it, so the next call starts fresh. The
    backoff still grows so a genuinely exhausted key does not spin.
    """
    window = 60.0
    try:
        import tokenmeter
        window = float(tokenmeter.WINDOW)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return min(90, int(window + 5) * (attempt + 1))


def chat(model: str, system: str, user: str, temperature: float = 0.2,
         max_tokens: int = 4000, tries: int = 2, role: str = "debug") -> str:
    """Ask the job's backend, walking the job's chain when an id is refused.

    A model id that belongs to the other backend answers 404 and used to kill
    the run on its first call. Retrying a daily cap is just as pointless: the
    cap does not refill for hours, so the next model in the chain is tried
    instead of sleeping the run's whole time budget away.
    """
    try:
        _, _, send = for_role(role)
    except SystemExit as e:
        # A missing key is a normal, catchable failure for every caller. Letting
        # SystemExit through killed the process instead of letting a job fall
        # back to its deterministic path.
        raise RuntimeError(str(e) or "no model provider is configured") from None
    order = list(dict.fromkeys([m for m in [model] + model_chain(role) if m]))
    last = ""
    for m in order:
        for attempt in range(tries):
            try:
                out = send(m, system, user, temperature, max_tokens)
                if out:
                    return out
                last = f"{m}: empty reply"
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                last = f"{m}: {e.code}: {body[:200]}"
                if e.code in (401, 403):
                    # A bad key is not model-specific; walking the chain only
                    # spends time and hides the real cause.
                    raise RuntimeError(f"{e.code}: {body[:200]}") from None
                if _is_model_not_found(e.code, body):
                    break
                if e.code == 429:
                    if _is_daily_cap(body):
                        break
                    time.sleep(_rate_limit_wait(attempt))
            except Exception as e:  # noqa: BLE001
                last = f"{m}: {str(e)[:200]}"
                if _is_model_not_found(0, last):
                    break
                if "429" in last or "Rate limit" in last:
                    if _is_daily_cap(last):
                        break
                    time.sleep(_rate_limit_wait(attempt))
    raise RuntimeError(last or "no reply")


if __name__ == "__main__":
    print("active provider:", provider_name())
    for m in models("builder"):
        print("  builder model:", m)
    for m in models("debug"):
        print("  debugger model:", m)