"""Which backend the pipeline talks to, and how it survives a refusal.

This is the test that makes the Groq -> OpenRouter swap safe. Three things
matter and each has broken a run before:

1. the backend is chosen by which key exists, OpenRouter first
2. the model ids belong to that backend -- a Groq id sent to OpenRouter is a
   404, and that 404 used to kill the whole build on its first call
3. a 404 or a per-day cap on one model moves to the next model in the chain,
   while a rejected key stops immediately instead of walking every model

No network: the provider is faked, so this runs on a machine with no keys.
"""
from __future__ import annotations

import io
import os
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import ai
import providers

fails: list[str] = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


KEYS = ("OPENROUTER_API_KEY", "GROQ_API_KEY",
        "OPENROUTER_CHAT_MODEL", "GROQ_CHAT_MODEL")
_saved = {k: os.environ.get(k) for k in KEYS}


def env(**kw):
    """A clean credential set plus exactly what this case needs."""
    for k in KEYS:
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = v


def http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid", code, body, {},
                                  io.BytesIO(body.encode()))


print("\nTHE BACKEND IS CHOSEN BY THE KEY THAT EXISTS\n")
env()
check("with no key, configured() is False", providers.configured() is False)
try:
    providers.compat()
    check("with no key, compat() refuses", False, "it returned a backend")
except SystemExit:
    check("with no key, compat() refuses", True)

env(OPENROUTER_API_KEY="sk-or-v1-test")
name, base, key, chains = providers.compat()
check("an OpenRouter key selects OpenRouter", name == "openrouter", name)
check("and the base URL is OpenRouter's",
      base == providers.OPENROUTER_BASE, base)
check("and the key is passed through unchanged", key == "sk-or-v1-test")
check("and the chains are the OpenRouter ones", chains is providers.OPENROUTER_CHAINS)

env(GROQ_API_KEY="gsk_test")
name, base, _, chains = providers.compat()
check("a Groq key alone selects Groq", name == "groq", name)
check("and the base URL is Groq's", base == providers.GROQ_BASE, base)
check("and the chains are the Groq ones", chains is providers.GROQ_CHAINS)

env(OPENROUTER_API_KEY="sk-or-v1-test", GROQ_API_KEY="gsk_test")
check("OpenRouter wins when both keys exist",
      providers.compat()[0] == "openrouter", providers.compat()[0])

# With both secrets present (the rollback stays in place) the transport and the
# model chain must still belong to the same backend. A role split used to send
# OpenRouter ids to Groq, which is a 404 for every model.
for role in providers.ROLES:
    check(f"the {role} transport is OpenRouter when both keys exist",
          providers.for_role(role)[0] == "openrouter",
          providers.for_role(role)[0])
check("and the builder chain is the OpenRouter one",
      providers.model_chain("builder") ==
      list(providers.OPENROUTER_CHAINS["builder"]),
      str(providers.model_chain("builder")))

env()
try:
    ai.backend()
    check("ai.backend() refuses when no key exists", False, "it returned")
except RuntimeError:
    check("ai.backend() refuses when no key exists", True)

try:
    providers.chat("m", "sys", "user")
    check("chat() refuses without a key, catchably", False, "it returned")
except RuntimeError:
    check("chat() refuses without a key, catchably", True)
except SystemExit as e:
    check("chat() refuses without a key, catchably", False,
          f"it raised SystemExit: {e}")

env(OPENROUTER_API_KEY="sk-or-v1-test")
check("ai.backend() follows the same choice",
      ai.backend()[0] == providers.OPENROUTER_BASE, ai.backend()[0])
env(GROQ_API_KEY="gsk_test")
check("ai.backend() falls back to Groq",
      ai.backend()[0] == providers.GROQ_BASE, ai.backend()[0])

print("\nEVERY MODEL ID BELONGS TO THE LIVE BACKEND\n")
env(OPENROUTER_API_KEY="sk-or-v1-test")
for role in providers.ROLES:
    chain = providers.model_chain(role)
    check(f"{role}: the chain has at least two models", len(chain) >= 2,
          str(chain))
    check(f"{role}: no duplicate ids", len(chain) == len(set(chain)), str(chain))
    check(f"{role}: every id is an OpenRouter free model",
          all(m.endswith(":free") for m in chain), str(chain))
    check(f"{role}: no Groq id leaked in",
          not any("gpt-oss" in m or "llama-3" in m for m in chain), str(chain))
    check(f"{role}: default_model() is the head of the chain",
          providers.default_model(role) == chain[0])

env(OPENROUTER_API_KEY="sk-or-v1-test", OPENROUTER_CHAT_MODEL="vendor/pinned:free")
check("a pinned model is tried first",
      providers.model_chain("chat")[0] == "vendor/pinned:free",
      str(providers.model_chain("chat")))
check("and the rest of the chain is still there",
      len(providers.model_chain("chat")) ==
      len(providers.OPENROUTER_CHAINS["chat"]) + 1)

env(GROQ_API_KEY="gsk_test", GROQ_CHAT_MODEL="vendor/pinned")
check("the Groq pin applies on the Groq backend",
      providers.model_chain("chat")[0] == "vendor/pinned")
env(OPENROUTER_API_KEY="sk-or-v1-test", GROQ_CHAT_MODEL="vendor/pinned")
check("a Groq pin cannot leak into the OpenRouter chain",
      "vendor/pinned" not in providers.model_chain("chat"))

print("\nA REFUSAL IS CLASSIFIED, NOT GUESSED\n")
check("404 is a missing model", providers._is_model_not_found(404, ""))
check("'model_not_found' is a missing model",
      providers._is_model_not_found(400, '{"error":"model_not_found"}'))
check("a rate limit is not a missing model",
      not providers._is_model_not_found(429, "rate limit reached"))
check("the OpenRouter per-day message is a daily cap",
      providers._is_daily_cap('{"error":"free-models-per-day limit reached"}'))
check("the Groq tokens-per-day message is a daily cap",
      providers._is_daily_cap("tokens per day (TPD) exceeded"))
check("a per-minute limit is not a daily cap",
      not providers._is_daily_cap("tokens per minute exceeded"))

print("\nTHE CHAIN IS WALKED ON THE RIGHT ERRORS\n")
_real_for_role, _real_chain = providers.for_role, providers.model_chain
try:
    env(OPENROUTER_API_KEY="sk-or-v1-test")
    providers.model_chain = lambda role="chat": ["first/model", "second/model"]

    calls: list[str] = []

    def send_404(model, *a, **kw):
        calls.append(model)
        if model == "first/model":
            raise http_error(404, '{"error":"no such model"}')
        return "answered"

    providers.for_role = lambda role="debug": ("openrouter", None, send_404)
    out = providers.chat("first/model", "sys", "user", role="debug")
    check("a 404 moves to the next model", out == "answered", out)
    check("and it did not retry the missing model", calls == ["first/model",
                                                              "second/model"],
          str(calls))

    calls.clear()

    def send_cap(model, *a, **kw):
        calls.append(model)
        if model == "first/model":
            raise http_error(429, '{"error":"free-models-per-day exceeded"}')
        return "answered"

    providers.for_role = lambda role="debug": ("openrouter", None, send_cap)
    out = providers.chat("first/model", "sys", "user", role="debug")
    check("a per-day cap moves to the next model", out == "answered", out)
    check("and it does not sleep on a cap that will not refill",
          calls == ["first/model", "second/model"], str(calls))

    calls.clear()

    def send_bad_key(model, *a, **kw):
        calls.append(model)
        raise http_error(401, '{"error":"invalid api key"}')

    providers.for_role = lambda role="debug": ("openrouter", None, send_bad_key)
    try:
        providers.chat("first/model", "sys", "user", role="debug")
        check("a rejected key raises instead of walking the chain", False,
              "it returned")
    except RuntimeError as e:
        check("a rejected key raises instead of walking the chain",
              "401" in str(e), str(e)[:80])
    check("and only one call was made", calls == ["first/model"], str(calls))
finally:
    providers.for_role, providers.model_chain = _real_for_role, _real_chain

print("\nNO MODULE KEEPS ITS OWN BACKEND\n")
# The swap is only complete if the base URL lives in providers.py/ai.py. A
# module that still names Groq will keep working on the old key and quietly
# fail on the new one.
allowed = {"providers.py", "ai.py", "groq_live_check.py", "check_connections.py"}
offenders = []
for p in sorted(ROOT.glob("*.py")):
    if p.name in allowed or p.name == Path(__file__).name:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if "api.groq.com" in line and not line.strip().startswith("#"):
            offenders.append(f"{p.name}:{i}")
check("no module outside the provider layer hard-codes a Groq URL",
      not offenders, ", ".join(offenders[:4]))

for k, v in _saved.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
