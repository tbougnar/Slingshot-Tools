"""Repair a broken control with a small patch instead of reprinting the app.

The free tier allows about 8k output tokens per minute, and a full 30 KB file
is roughly 8k tokens by itself, so asking a model to reprint the whole app can
never complete twice in a row. A patch costs a few hundred tokens and is what
the rate limit actually allows.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error

import requests

BASE = "https://api.groq.com/openai/v1"
CHAT_MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
HEADERS = {
    "Authorization": "Bearer {key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"),
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://console.groq.com/",
}
# 16384 is the hard ceiling Groq accepts; asking for more is refused outright.
MAX_TOKENS = 16000
# qwen is limited to about 1000 output tokens a minute on this tier, and a
# larger request is refused as "Request too large" rather than truncated.
MODEL_LIMITS = {"qwen/qwen3.8-27b": 900, "openai/gpt-oss-20b": 8000,
                "openai/gpt-oss-120b": 8000}


def budget(model: str, want: int) -> int:
    return max(200, min(want, MODEL_LIMITS.get(model, 4000)))


def _headers() -> dict:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return {k: v.format(key=key) if "{key}" in v else v for k, v in HEADERS.items()}


def chat(model: str, system: str, user: str, max_tokens: int = 4000,
         temperature: float = 0.1, tries: int = 1) -> str:
    """Ask whichever provider is configured. One retry, then move on."""
    import providers
    return providers.chat(model, system, user, temperature,
                          budget(model, max_tokens), tries, role="debug")


PATCH_SYSTEM = """You fix broken controls in a single-file HTML app.

You get the app's HTML and a list of controls that do nothing when clicked.
Read the inventory and target elements by id, class or visible label.

Reply with JSON only:
{"patches": [{"control": "<label from the list>", "selector": "<css selector>",
"code": "<the javascript to run on click>"}]}

Hard rules:
- Keep every code fragment SHORT. You are rate limited, so never reprint the file.
- ONLY use things that already exist in the app. Before writing code, look at
  the ids, class names, function names and element structure in the HTML you were
  given, and call those. Never invent a function name you have not seen.
- If the app has no suitable function, write self-contained code that uses the
  element's own value and updates the DOM or localStorage directly.
- Do not use innerHTML to rebuild the whole page, do not querySelectorAll, and do
  not touch any class name or style.
- Attach with addEventListener on the exact element, and guard for a missing
  element so a null never throws.
- One patch per broken control. Nothing else may change.
"""

PATCH_USER = """BROKEN CONTROLS:
{controls}

EXISTING IDS AND FUNCTIONS IN THE APP:
{inventory}

THE APP:
{html}

Return JSON with one patch per broken control."""


def focus(html: str) -> str:
    """Only the part a patch needs: the script block and the tail of the markup.

    Sending the whole document costs thousands of tokens per patch, which is
    most of the per-minute allowance for a file this size.
    """
    import re as _re
    head = _re.sub(r"<style.*?</style>", "", html, flags=_re.S | _re.I)
    script = "".join(_re.findall(r"<script.*?</script>", html, _re.S | _re.I))
    return ("STYLE REMOVED. MARKUP AND SCRIPT:\n"
            + head[-4000:] + "\n" + script[-4000:])


def inventory(html: str) -> str:
    """List what the app already has, so a patch calls real things."""
    # both quote styles: generated markup uses single quotes at least as often
    ids = sorted(set(re.findall(r'id="([^"]+)"', html))
                 | set(re.findall(r"id='([^']+)'", html)))[:60]
    fns = sorted(set(re.findall(r"function\s+([A-Za-z_$][\w$]*)", html)))[:40]
    consts = sorted(set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=",
                                  html)))[:40]
    keys = sorted(set(re.findall(r"localStorage\.([A-Za-z]+|['\"][^'\"]+['\"])",
                                  html)))[:20]
    # A patch targets an id, a class or a visible label, and the markup itself
    # is trimmed away to save tokens, so all three ways of finding an element
    # have to be listed or the patch has nothing to point at.
    classes = sorted({c
                      for m in (re.findall(r'class="([^"]*)"', html)
                                + re.findall(r"class='([^']*)'", html))
                      for c in m.split()})[:40]
    controls = []
    for m in re.finditer(r"<(button|select|a)\b[^>]*>([^<]{1,40})<", html):
        txt = m.group(2).strip()
        if txt:
            controls.append(f"{m.group(1)}:{txt}")
    controls = sorted(set(controls))[:25]
    return (f"ids: {ids}\nclasses: {classes}\ncontrols: {controls}\n"
            f"functions: {fns}\nvariables: {consts}\n"
            f"storage keys: {keys}")


BANNED_CALLS = ("document.write", "outerHTML", "insertAdjacentHTML",
                "location.href", "location.replace", "eval(",
                "new Function(", "fetch(", "XMLHttpRequest", "import(")


def code_is_safe(code: str) -> bool:
    """Refuse anything that rewrites the page or reaches the network."""
    flat = " ".join(str(code).split())
    for bad in BANNED_CALLS:
        if bad in flat:
            return False
    return True


PATCH_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


def plan_patches(html: str, controls: list[str],
                 models: list[str] | None = None) -> list[dict] | None:
    models = models or PATCH_MODELS
    known = ""
    try:
        import buglog
        known = buglog.match(" ".join(controls) + " " + html[-3000:])
    except Exception:  # noqa: BLE001
        known = ""
    known_block = (f"\n\nFIXES FOR THIS FAULT (use them if they fit):\n{known}\n"
                   if known else "")
    user = PATCH_USER.format(controls=json.dumps(controls)[:2000],
                             inventory=inventory(html),
                             html=focus(html)) + known_block
    for m in models:
        try:
            raw = chat(m, PATCH_SYSTEM, user,
                       max_tokens=budget(m, 1200))
        except Exception as e:  # noqa: BLE001
            print(f"[patch] {m}: {str(e)[:160]}")
            continue
        got = re.search(r"\{.*\}", raw, re.S)
        if not got:
            continue
        try:
            d = json.loads(got.group(0))
        except Exception:  # noqa: BLE001
            continue
        patches = [p for p in (d.get("patches") or [])
                   if p.get("selector") and p.get("code")]
        if patches:
            print(f"[patch] {m} produced {len(patches)} patch(es)")
            return patches
    return None


def apply_patches(html: str, patches: list[dict]) -> str | None:
    """Insert the handlers into the app's script block, refusing any styling change."""
    out = html
    for p in patches:
        sel = str(p["selector"]).strip()
        code = str(p["code"]).strip().rstrip(";")
        # a selector that could match many elements is too blunt to inject blind
        if not re.fullmatch(r"[#.\w\[\]=\"'\-\s>:(),>+~]+", sel):
            print(f"[patch] refused suspicious selector {sel!r}")
            continue
        handler = (
            "try{var __n=document.querySelector(" + json.dumps(sel) + ");"
            "if(__n&&!__n.dataset.slFixed){__n.dataset.slFixed='1';"
            "__n.addEventListener('click',function(ev){" + code + "});}}"
            "catch(__e){console.error(__e);}")
        if not code_is_safe(code):
            print(f"[patch] refused dangerous code for {sel!r}")
            continue
        if re.search(r"\bquerySelectorAll\b", code):
            print(f"[patch] refused bulk selector code for {sel!r}")
            continue
        if "<script>" in out:
            # add the wiring at the end of the last script block
            idx = out.rfind("</script>")
            out = out[:idx] + f"\n{handler}\n" + out[idx:]
        else:
            out += f"\n<script>{handler}</script>\n"
    if out == html:
        return None
    if not _styling_intact(html, out):
        print("[patch] rejected: a patch changed the styling")
        return None
    return out


def _styling_intact(before: str, after: str) -> bool:
    def snap(h: str) -> tuple:
        h2 = re.sub(r"<script.*?</script>", "", h, flags=re.S | re.I)
        return (tuple(re.findall(r"<style[^>]*>.*?</style>", h, re.S | re.I)),
                tuple(sorted(re.findall(r'style\s*=\s*"[^"]*"', h, re.I))),
                tuple(sorted(set(re.findall(r'class\s*=\s*"([^"]*)"', h2)))))
    return snap(before) == snap(after)


if __name__ == "__main__":
    print("repair budget:", MAX_TOKENS, "tokens per call")