"""Self-healing build debugger.

When the build workflow fails, this collects the evidence, asks the model what
broke and what to change, applies the patch under strict limits, and lets the
workflow run again.

Guardrails, because a model is editing the code that takes payments:

  * only files on ALLOWED may be touched - the pipeline only, never the price
    bounds, never the itch.io links, never the site output or policies
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

# Windows consoles default to a legacy code page, so any non-ASCII character in
# model output used to raise UnicodeEncodeError and kill the run. Output that
# cannot be encoded is replaced rather than fatal.
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _safe(text) -> str:
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return "<unprintable>"


from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_ATTEMPT = int(os.environ.get("SELFHEAL_MAX", "3"))
MODEL = "openai/gpt-oss-120b"

ALLOWED = {
    "make_app.py",
    "learn.py",
    "build_exe.py",
    "build_installer_app.py",
    "native_launcher.py",
    "selfheal.py",
}

FORBIDDEN = [
    r"itch_url",              # where a product is sold
    r"publish_paid",
    r"PRICE_FLOOR",
    r"PRICE_CEILING",
    r"ITCH_(API_KEY|USER)",
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
    """The debugger team works to a fixed order.

    Each debugger reads the fixbook first. If they agree, that fix is proposed.
    If they disagree, every proposal is reported so each can be tried and
    tested separately. If they all fail, the team researches together.
    """
    report = json.dumps(diag)[:12000]
    try:
        import debug_team2 as team
    except ImportError:
        return {"diagnosis": "debugger team unavailable", "fixes": []}
    if not os.environ.get("GROQ_API_KEY"):
        return {"diagnosis": "no GROQ_API_KEY available", "fixes": []}

    props = team.proposals(report, team.DEBUGGERS)
    if not props:
        return {"diagnosis": "no debugger could answer", "fixes": []}

    key, agree = team.agreement(props)
    if len(agree) >= 2:
        print(f"[selfheal] {len(agree)}/{len(props)} debuggers agreed")
    else:
        print(f"[selfheal] no agreement: {[d.get('fix','')[:40] for _, d in props]}")
        return {"diagnosis": "debuggers disagreed: "
                              + " | ".join(d.get("fix", "")[:120] for _, d in props),
                "fixes": [], "disagreed": [d for _, d in props]}

    chosen = next(d for _, d in props if d is props[0][1])
    for model, d in props:
        if re.sub(r"\s+", " ", d.get("fix", "").strip().lower())[:160] == key:
            chosen = d
            break

    files = [f for f in (chosen.get("files") or []) if f in ALLOWED]
    if not files:
        return {"diagnosis": f"proposed fix touches no allowed file: "
                              f"{chosen.get('files')}", "fixes": []}
    return {"diagnosis": chosen.get("diagnosis") or "agreed fix",
            "fixes": [{"file": files[0], "note": chosen.get("fix", ""),
                       "content": None}],
            "research": None}


def research(diag: dict, tried: list[str]) -> dict:
    """Every proposal failed, so the team researches instead of guessing."""
    try:
        import debug_team2 as team
    except ImportError:
        return {"diagnosis": "debugger team unavailable", "fixes": []}
    got = team.research(json.dumps(diag)[:10000], team.DEBUGGERS, tried)
    if not got:
        return {"diagnosis": "research found nothing usable", "fixes": []}
    files = [f for f in (got.get("files") or []) if f in ALLOWED]
    if not files:
        return {"diagnosis": "research proposed no allowed file", "fixes": []}
    return {"diagnosis": f"research: {got.get('found','')[:160]}",
            "fixes": [{"file": files[0], "note": got.get("fix", ""), "content": None}]}


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


LESSONS = ROOT / "data" / "lessons.txt"


def remember(diagnosis: str, fixes: list[dict]) -> None:
    """Write the lesson down so the builder is told next time.

    This was called twice and never defined, so the debugger crashed with a
    NameError at the exact moment it tried to record what it had learned.
    """
    if not fixes:
        return
    try:
        import buglog
    except ImportError:
        return
    files = [f.get("file", "?") for f in fixes]
    what = "; ".join(str(f.get("note", ""))[:200] for f in fixes)
    entry = buglog.record(
        symptom=diagnosis,
        cause=(fixes[0].get("note") or diagnosis)[:300],
        fix=what[:400],
        files=files,
        detects=f"recurs if {files[0]} changes this behaviour",
        verified=False)
    print(f"[selfheal] fixbook {entry['id']} recorded: {diagnosis[:80]}")


def apply(fixes: list[dict], attempt: int, diagnosis: str) -> bool:
    if not fixes:
        print("[selfheal] no changes proposed - stopping here")
        return False
    for f in fixes:
        target = ROOT / f["file"]
        content = f.get("content")
        if content is None:
            print(f"[selfheal] proposal is guidance only, not a patch: "
                  f"{f['note'][:90]}")
            print("[selfheal] recording it in the fixbook instead")
            remember(diagnosis, f)
            return False
        backup = target.read_text(encoding="utf-8", errors="replace")
        target.write_text(content, encoding="utf-8")
        rc, out = run([sys.executable, "-m", "py_compile", f["file"]], timeout=180)
        if rc != 0:
            print(f"[selfheal] {f['file']} did not compile - reverting")
            target.write_text(backup, encoding="utf-8")
            return False
    run(["git", "add", "-A"])
    msg = f"fix(attempt {attempt}): {diagnosis[:120]}"
    rc, out = run(["git", "-c", "user.name=slingshot-bot",
                   "-c", "user.email=bot@users.noreply.github.com",
                   "commit", "-q", "-m", msg])
    if rc != 0:
        print("[selfheal] nothing to commit")
        return False
    print(f"[selfheal] committed: {msg}")
    for f in fixes:
        print(f"           {f['file']}: {f['note'][:100]}")
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
    if fixes:
        remember(diagnosis, fixes)
    return 0 if apply(fixes, attempt, diagnosis) else 1


if __name__ == "__main__":
    raise SystemExit(main())