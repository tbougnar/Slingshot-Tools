"""The debugger team protocol.

Builders write the app. When one fails, the failure goes to the debuggers, and
they work to a fixed order:

  1. every debugger reads the fixbook first and proposes a fix from it
  2. if a majority propose the same fix, it is applied and tested
  3. if they disagree, each fix is applied to a copy and tested on its own
  4. the fix that passes is kept
  5. if every proposal fails, the team researches together and proposes again

A fix is never applied on agreement alone. It has to survive a test.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
BASE = "https://api.groq.com/openai/v1"

# Builders get the strongest model; the debuggers share what is left.
BUILDERS = ["openai/gpt-oss-120b"]
DEBUGGERS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]

HEADERS = {
    "Authorization": "Bearer {key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"),
    "Accept-Encoding": "gzip, deflate",
}
MAX_TOKENS = 16000


def _headers() -> dict:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return {k: v.format(key=key) if "{key}" in v else v for k, v in HEADERS.items()}


def chat(model: str, system: str, user: str, max_tokens: int = 3000,
         temperature: float = 0.1, tries: int = 3) -> str:
    import time
    body = {"model": model, "temperature": temperature,
            "max_tokens": min(max_tokens, MAX_TOKENS), "reasoning_effort": "low",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    last = ""
    for attempt in range(tries):
        r = requests.post(BASE + "/chat/completions", headers=_headers(),
                          data=json.dumps(body), timeout=180)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"] or ""
        last = f"{r.status_code}: {r.text[:200]}"
        if "429" in last:
            time.sleep(20 * (attempt + 1))
            continue
        break
    raise RuntimeError(last or "no reply")


def fixbook_text(limit: int = 20000) -> str:
    f = ROOT / "data" / "fixbook.md"
    if f.exists():
        return f.read_text(encoding="utf-8")[:limit]
    try:
        import buglog
        return buglog.brief(40)[:limit]
    except Exception:  # noqa: BLE001
        return "(fixbook unavailable)"


PROPOSE = """You are a debugger on a small app-building pipeline.

You are given a failure report and the project's fixbook.

FIRST: if the failure matches a fixbook entry, propose exactly that fix.

Reply with JSON only:
{"known": "<entry id such as B008, or empty>",
 "diagnosis": "<one sentence>",
 "fix": "<the change to make>",
 "files": ["<path>"]}

If nothing matches, diagnose it yourself from first principles. Do not guess at a
change you cannot explain."""


def propose(model: str, report: str) -> dict | None:
    user = f"FIXBOOK:\n{fixbook_text(12000)}\n\nFAILURE:\n{report[:10000]}"
    try:
        raw = chat(model, PROPOSE, user, max_tokens=1500)
    except Exception as e:  # noqa: BLE001
        print(f"[debug] {model} could not answer: {str(e)[:140]}")
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    if d.get("fix"):
        print(f"[debug] {model}: {d.get('known') or 'new'} -> {d['fix'][:90]}")
        return d
    return None


def proposals(report: str, models: list[str]) -> list[tuple[str, dict]]:
    out = []
    for m in models:
        d = propose(m, report)
        if d:
            out.append((m, d))
    return out


def agreement(props: list[tuple[str, dict]]) -> tuple[str, list[str]]:
    """Return the fix a majority proposed, and who agreed."""
    if not props:
        return "", []
    tally: dict[str, list[str]] = {}
    for model, d in props:
        key = re.sub(r"\s+", " ", str(d.get("fix", "")).strip().lower())[:160]
        tally.setdefault(key, []).append(model)
    best, who = max(tally.items(), key=lambda kv: len(kv[1]))
    return best, who


SEARCH = """Your proposed fixes were tested and every one of them failed.

Search the web for the real cause and the correct fix. Use the tools and
documentation for the exact libraries involved rather than reasoning from
memory, because the library may have changed.

Reply with JSON only:
{"found": "<what you found, with the source>",
 "fix": "<the change to make>",
 "files": ["<path>"]}"""


def research(report: str, models: list[str], tried: list[str]) -> dict | None:
    """The team researches together, strongest model first."""
    user = (f"FAILURE:\n{report[:8000]}\n\nALREADY TRIED AND REJECTED:\n"
            + json.dumps(tried)[:3000])
    for m in models:
        try:
            raw = chat(m, SEARCH, user, max_tokens=2000)
        except Exception as e:  # noqa: BLE001
            print(f"[debug] research {m} failed: {str(e)[:120]}")
            continue
        g = re.search(r"\{.*\}", raw, re.S)
        if not g:
            continue
        try:
            d = json.loads(g.group(0))
        except Exception:  # noqa: BLE001
            continue
        if d.get("fix"):
            print(f"[debug] research by {m}: {str(d.get('found',''))[:90]}")
            return d
    return None


def compile_ok(files: list[str]) -> tuple[bool, str]:
    """A proposed fix has to at least compile."""
    import subprocess
    import sys
    for f in files:
        p = ROOT / f
        if not p.exists():
            return False, f"{f} does not exist"
        if f.endswith(".py"):
            r = subprocess.run([sys.executable, "-m", "py_compile", f],
                               cwd=str(ROOT), capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{f}: {(r.stderr or '')[-200:]}"
    return True, ""


if __name__ == "__main__":
    print("builders  :", BUILDERS)
    print("debuggers :", DEBUGGERS)