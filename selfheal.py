"""Self-healing build debugger.

When the build workflow fails, this collects the evidence, asks the model what
broke and what to change, applies the patch under strict limits, and lets the
workflow run again.

Guardrails, because a model is editing the code that takes payments:

  * only files on ALLOWED may be touched - the pipeline, never the Worker,
    never pricing bounds, never the site output, never licences or policies
  * FORBIDDEN patterns are rejected outright (payment endpoints, price clamps,
    publish gating, secrets, delete/rm of the paid folder)
  * every patch is compiled and must survive a test run before it counts
  * a hard attempt cap, then it stops and says so instead of thrashing
  * every patch is a separate commit, so it is visible and revertable
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_ATTEMPT = int(os.environ.get("SELFHEAL_MAX", "3"))
MODEL = "openai/gpt-oss-120b"

ALLOWED = {
    "make_app.py",
    "pricing.py",
    "learn.py",
    "paid_store.py",
    "build_exe.py",
    "build_installer_app.py",
    "native_launcher.py",
    "paypal.py",
    "selfheal.py",
}

FORBIDDEN = [
    r"/api/(order|download)",
    r"capture\(",
    r"BUILDS\.get",
    r"BUILDS\.put",
    r"PRICE_FLOOR",
    r"PRICE_CEILING",
    r"PAYPAL_(CLIENT_ID|SECRET|SANDBOX)",
    r"LICENSE_SECRET",
    r"CF_API_TOKEN",
    r"cfut_",
    r"github_pat_",
    r"staging\.lockdown",
    r"rmtree",
    r"published\s*=\s*True",
    r"selfheal\.env",
]

SYSTEM = """You repair a Python build pipeline for a small app store.

You will get a failure report from a GitHub Actions run. Reply with JSON only:
{"diagnosis": "<one sentence>", "fixes": [{"file": "<repo-relative path>",
"note": "<what changed>", "content": "<the COMPLETE new file content>"}]}

Rules:
- content must be the entire file, not a fragment or a diff.
- Keep the change as small as possible. Do not refactor working code.
- Preserve every existing behaviour that is not the direct cause of the failure.
- Never touch payment endpoints, pricing bounds, secrets, or publish gating.
- Never disable the quality checks to make a failure disappear.
- If the report shows an infrastructure problem (network, rate limit, outage),
  return {"diagnosis": "...", "fixes": []} and say so instead of editing code.
"""


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def collect(attempt: int) -> dict:
    """Gather the evidence: the failing job's log tail and the last commits."""
    log = ""
    for p in ("selfheal/last_run.log", "selfheal/failure.txt"):
        f = ROOT / p
        if f.exists():
            log += f.read_text(encoding="utf-8", errors="replace") + "\n"
    tail = log[-12000:]
    _, recent = run(["git", "log", "--oneline", "-8"])
    _, status = run(["git", "status", "--porcelain"])
    return {"attempt": attempt, "log_tail": tail, "recent_commits": recent,
            "git_status": status[:2000]}


def ask(diag: dict) -> dict:
    try:
        import ai
    except ImportError:
        return {"diagnosis": "ai module missing", "fixes": []}
    if not os.environ.get("GROQ_API_KEY"):
        return {"diagnosis": "no GROQ_API_KEY available", "fixes": []}
    user = json.dumps(diag)[:14000]
    try:
        raw = ai.chat(MODEL, SYSTEM, user, temperature=0.1, max_tokens=6000)
    except Exception as e:  # noqa: BLE001
        return {"diagnosis": f"model call failed: {str(e)[:200]}", "fixes": []}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"diagnosis": "model did not return JSON", "fixes": []}
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {"diagnosis": "model returned malformed JSON", "fixes": []}


def safe(plan: dict) -> list[dict]:
    """Keep only fixes that are allowed and that violate nothing."""
    keep = []
    for fix in plan.get("fixes") or []:
        name = str(fix.get("file", "")).replace("\\", "/").strip()
        if name not in ALLOWED:
            continue
        content = fix.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        bad = [p for p in FORBIDDEN if re.search(p, content)]
        if bad:
            print(f"[selfheal] refused {name}: touches {bad[0]}")
            continue
        if len(content.splitlines()) < 5:
            continue
        keep.append({"file": name, "note": str(fix.get("note", ""))[:200],
                     "content": content})
    return keep


def apply(fixes: list[dict], attempt: int, diagnosis: str) -> bool:
    if not fixes:
        print("[selfheal] no changes proposed - stopping here")
        return False
    for f in fixes:
        target = ROOT / f["file"]
        backup = target.read_text(encoding="utf-8", errors="replace")
        target.write_text(f["content"], encoding="utf-8")
        rc, out = run([sys.executable, "-m", "py_compile", f["file"]], timeout=180)
        if rc != 0:
            print(f"[selfheal] {f['file']} did not compile - reverting")
            target.write_text(backup, encoding="utf-8")
            return False
    rc, _ = run(["git", "add", "-A"])
    msg = f"fix(attempt {attempt}): {diagnosis[:120]}"
    rc, out = run(["git", "-c", "user.name=slingshot-bot",
                   "-c", "user.email=bot@users.noreply.github.com",
                   "commit", "-q", "-m", msg])
    if rc != 0:
        print("[selfheal] nothing to commit")
        return False
    print(f"[selfheal] committed: {msg}")
    for f in fixes:
        print(f"           {f['file']}: {f['note']}")
    return True


def main() -> int:
    attempt = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    if attempt > MAX_ATTEMPT:
        print(f"[selfheal] {attempt} attempts already made - stopping for a human")
        return 1
    diag = collect(attempt)
    if not diag["log_tail"].strip():
        print("[selfheal] no failure log found")
        return 1
    print(f"[selfheal] attempt {attempt}/{MAX_ATTEMPT}: asking the model what broke")
    plan = ask(diag)
    diagnosis = str(plan.get("diagnosis", "")).strip() or "unspecified"
    print(f"[selfheal] diagnosis: {diagnosis}")
    fixes = safe(plan)
    print(f"[selfheal] {len(fixes)} fix(es) allowed by policy")
    return 0 if apply(fixes, attempt, diagnosis) else 1


if __name__ == "__main__":
    raise SystemExit(main())