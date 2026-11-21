"""24/7 Kerit AI monitor: scans system/apps for errors, glitches, and vulnerabilities.

- Runs continuously in Kerit Cloud (started by kerit_service.py).
- Errors/glitches: fixed on the spot when safe/deterministic.
- App vulnerabilities/security issues: handed off to AI dev team to produce
  update metadata/code fixes and publish same-day update manifests.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
REPORT = DATA / "kerit_ai_monitor.json"
TASKS = DATA / "ai_dev_team_tasks.json"
FIXLOG = DATA / "kerit_ai_monitor_fixes.json"

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "_audit_tmp"}
TEXT_EXTS = {".py", ".js", ".ts", ".html", ".css", ".json", ".yml", ".yaml", ".md", ".ps1", ".cmd", ".txt"}
APP_EXTS = {".py", ".js", ".ts", ".html", ".css", ".json"}


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[kerit-ai-monitor {ts}] {msg}", flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_files(roots=None, exts=None):
    roots = roots or [ROOT]
    exts = exts or TEXT_EXTS
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in exts:
                yield p


def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


# ----------------------------- scanning -----------------------------

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "Possible AWS access key", "high"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "Possible GitHub token", "high"),
    (re.compile(r"sk_live_[A-Za-z0-9]{16,}"), "Possible Stripe live key", "critical"),
    (re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----"), "Private key material", "critical"),
]
VULN_PATTERNS = [
    (re.compile(r"\beval\(\s*"), "Use of eval (code injection risk)", "medium"),
    (re.compile(r"\bexec\(\s*"), "Use of exec (code injection risk)", "medium"),
    (re.compile(r"subprocess\..*shell\s*=\s*True"), "subprocess shell=True (command injection risk)", "medium"),
    (re.compile(r"verify\s*=\s*False"), "TLS verification disabled", "high"),
    (re.compile(r"debug\s*=\s*True", re.I), "Debug mode enabled", "low"),
    (re.compile(r"ALLOWED_HOSTS\s*=\s*\[\s*['\"]\*['\"]\s*\]"), "Wildcard ALLOWED_HOSTS", "medium"),
]
APP_VULN_PATTERNS = [
    (re.compile(r"innerHTML\s*=\s*[^;]*\+"), "Potential XSS via innerHTML concatenation", "high"),
    (re.compile(r"document\.write\("), "document.write usage (XSS risk)", "medium"),
    (re.compile(r"eval\(\s*"), "eval in app code", "high"),
    (re.compile(r"child_process|execSync|spawn\(.+shell:\s*true"), "Shell execution in app code", "high"),
]


def scan_system() -> dict:
    findings = {
        "glitches": [],
        "vulnerabilities": [],
        "app_vulnerabilities": [],
        "stats": {"files_scanned": 0, "apps_scanned": 0},
    }

    # 1) JSON/data file glitches
    for p in DATA.glob("*.json"):
        txt = read_text(p)
        if txt is None:
            findings["glitches"].append({"type": "unreadable_json", "file": p.relative_to(ROOT).as_posix(), "severity": "medium"})
            continue
        try:
            json.loads(txt)
        except Exception as e:
            findings["glitches"].append({"type": "invalid_json", "file": p.relative_to(ROOT).as_posix(), "severity": "high", "detail": str(e)[:180]})

    # 2) Python syntax glitches in repo scripts
    for p in ROOT.glob("*.py"):
        txt = read_text(p)
        if txt is None:
            continue
        try:
            compile(txt.lstrip("\ufeff"), p.name, "exec")
        except SyntaxError as e:
            findings["glitches"].append({"type": "python_syntax_error", "file": p.relative_to(ROOT).as_posix(), "severity": "high", "detail": f"{e.msg} at line {e.lineno}"})
        except Exception:
            pass

    # 3) Security/vulnerability patterns in codebase
    seen_v = set()
    for p in iter_files([ROOT], TEXT_EXTS):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("data/") or rel.startswith("site/apps/") or rel.startswith("apps/") or rel.startswith("paid/"):
            continue
        txt = read_text(p)
        if txt is None:
            continue
        findings["stats"]["files_scanned"] += 1
        for rx, label, sev in SECRET_PATTERNS:
            m = rx.search(txt)
            if m:
                k = (rel, label)
                if k not in seen_v:
                    seen_v.add(k)
                    findings["vulnerabilities"].append({"type": "secret", "file": rel, "issue": label, "severity": sev, "match": m.group(0)[:20]})
        for rx, label, sev in VULN_PATTERNS:
            if rx.search(txt):
                k = (rel, label)
                if k not in seen_v:
                    seen_v.add(k)
                    findings["vulnerabilities"].append({"type": "code_pattern", "file": rel, "issue": label, "severity": sev})

    # 4) App vulnerability scan (all made apps)
    app_roots = [ROOT / "apps", ROOT / "paid", ROOT / "site" / "apps"]
    seen_a = set()
    for base in app_roots:
        if not base.exists():
            continue
        for app_dir in base.iterdir() if base.exists() else []:
            if not app_dir.is_dir():
                continue
            findings["stats"]["apps_scanned"] += 1
            for p in iter_files([app_dir], APP_EXTS):
                rel = p.relative_to(ROOT).as_posix()
                txt = read_text(p)
                if txt is None:
                    continue
                for rx, label, sev in APP_VULN_PATTERNS:
                    if rx.search(txt):
                        k = (rel, label)
                        if k not in seen_a:
                            seen_a.add(k)
                            findings["app_vulnerabilities"].append({"type": "app_vuln", "app": app_dir.name, "file": rel, "issue": label, "severity": sev})

    # 5) Manifest/glitch checks
    for name in ["site/update.json", "site/apps.json", "site/votes.json", "site/events.json"]:
        p = ROOT / name
        if not p.exists():
            findings["glitches"].append({"type": "missing_manifest", "file": name, "severity": "high"})
            continue
        txt = read_text(p)
        try:
            json.loads(txt or "")
        except Exception as e:
            findings["glitches"].append({"type": "invalid_json", "file": name, "severity": "high", "detail": str(e)[:160]})

    # Deduplicate and cap
    for k in ("glitches", "vulnerabilities", "app_vulnerabilities"):
        findings[k] = findings[k][:120]
    return findings


# ----------------------------- auto-fix -----------------------------

def auto_fix_glitches(findings: dict) -> list[dict]:
    fixes = []
    for g in findings.get("glitches", []):
        ftype = g.get("type")
        rel = g.get("file")
        if not rel:
            continue
        p = ROOT / rel
        try:
            if ftype == "missing_manifest":
                if rel.endswith(".json"):
                    default = [] if rel.endswith("apps.json") else {}
                    if rel == "site/update.json":
                        default = {"version":"0.0.0","updated":datetime.now(timezone.utc).date().isoformat(),"apps":{},"latest_update":{"title":"Auto-fix","description":"Manifest recreated by Kerit AI monitor.","notes":["Auto-fixed missing manifest"],"released":datetime.now(timezone.utc).date().isoformat()}}
                    write_json(p, default)
                    fixes.append({"file": rel, "action": "recreated_missing_manifest", "ok": True})
            elif ftype == "invalid_json":
                txt = read_text(p)
                if txt is None:
                    continue
                # Safe deterministic fix: try to recover by stripping BOM/trailing junk and reparse; if fails, reset known manifests only
                cleaned = txt.lstrip("\ufeff").strip()
                try:
                    obj = json.loads(cleaned)
                    write_json(p, obj)
                    fixes.append({"file": rel, "action": "normalized_json", "ok": True})
                except Exception:
                    if rel.startswith("site/") and rel.endswith(".json"):
                        # reset only known site manifests to safe defaults
                        defaults = {
                            "site/apps.json": [],
                            "site/votes.json": {"poll": None},
                            "site/events.json": {"events": []},
                        }
                        if rel in defaults:
                            write_json(p, defaults[rel])
                            fixes.append({"file": rel, "action": "reset_known_manifest", "ok": True})
                    elif rel.startswith("data/") and rel.endswith(".json"):
                        # For data json, attempt minimal salvage: wrap? No - too risky. Leave for dev team.
                        fixes.append({"file": rel, "action": "needs_dev_team", "ok": False, "reason": "invalid_json_not_safe_to_auto_reset"})
            elif ftype == "python_syntax_error":
                # On-the-spot syntax fix attempt via AI dev team (lightweight) only for safe files? 
                # We'll hand off to dev team; do not guess.
                fixes.append({"file": rel, "action": "handoff_syntax_error", "ok": False})
        except Exception as e:
            fixes.append({"file": rel, "action": f"auto_fix_failed:{ftype}", "ok": False, "error": str(e)[:160]})
    return fixes

# ----------------------------- AI dev team -----------------------------

def _ai_chat(system: str, user: str) -> str:
    try:
        import providers
        if not providers.configured():
            return ""
        return providers.chat(providers.best_model("chat"), system, user, 0.2, 1200, role="chat") or ""
    except Exception as e:
        log(f"AI unavailable: {str(e)[:140]}")
        return ""


def handoff_to_ai_dev_team(findings: dict, auto_fixes: list[dict]) -> dict:
    """Hand vulnerabilities/app issues to AI dev team; produce updates/tasks."""
    vulns = list(findings.get("vulnerabilities", []))
    app_vulns = list(findings.get("app_vulnerabilities", []))
    # glitches that couldn't be auto-fixed
    pending_glitches = [g for g in findings.get("glitches", []) if g.get("type") in ("python_syntax_error", "invalid_json")]
    pending_glitches = [g for g in pending_glitches if not any(f.get("file")==g.get("file") and f.get("ok") for f in auto_fixes)]

    result = {"tasks_created": 0, "updates_published": [], "actions": []}
    if not vulns and not app_vulns and not pending_glitches:
        return result

    # Build dev-team task
    task = {
        "id": hashlib.sha1((now_iso()+json.dumps(vulns[:5],sort_keys=True)).encode()).hexdigest()[:12],
        "created": now_iso(),
        "status": "open",
        "vulnerabilities": vulns[:40],
        "app_vulnerabilities": app_vulns[:40],
        "pending_glitches": pending_glitches[:40],
        "auto_fixes": auto_fixes[:40],
    }

    # Ask AI dev team for remediation plan/update notes
    system = (
        "You are the Slingshot AI dev team. Analyze reported system/app findings. "
        "Return ONLY JSON with keys: summary (string), severity (low|medium|high|critical), "
        "fix_now (array of {file,action,reason}), app_updates (array of {app,title,description,notes}), "
        "publish_update (boolean). Be concrete and safe."
    )
    user = json.dumps({
        "vulnerabilities": vulns[:20],
        "app_vulnerabilities": app_vulns[:20],
        "pending_glitches": pending_glitches[:20],
        "auto_fixes": auto_fixes[:20],
    }, ensure_ascii=False)[:12000]
    raw = _ai_chat(system, user)
    plan = {}
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                plan = json.loads(m.group(0))
            except Exception:
                plan = {}
    if not plan:
        plan = {
            "summary": "Automated monitor detected issues requiring developer attention.",
            "severity": "high" if (vulns or app_vulns) else "medium",
            "fix_now": [],
            "app_updates": [],
            "publish_update": bool(app_vulns or vulns),
        }
    task["plan"] = plan

    # Attempt safe "fix now" actions suggested by AI dev team (only for known-safe ops)
    for item in (plan.get("fix_now") or [])[:20]:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("file") or "")
        action = str(item.get("action") or "")
        if not rel or ".." in rel.replace("\\", "/"):
            continue
        p = ROOT / rel
        # Only allow safe manifest normalization/reset actions on data/site json
        if action == "normalize_json" and p.exists() and rel.endswith(".json"):
            txt = read_text(p)
            try:
                obj = json.loads((txt or "").lstrip("\ufeff"))
                write_json(p, obj)
                result["actions"].append({"file": rel, "action": action, "ok": True})
            except Exception as e:
                result["actions"].append({"file": rel, "action": action, "ok": False, "error": str(e)[:120]})
        else:
            result["actions"].append({"file": rel, "action": action, "ok": False, "reason": "not_auto_safe"})

    # For app vulnerabilities: publish same-day update manifest (AI dev team handoff)
    if app_vulns or (plan.get("publish_update") and (vulns or app_vulns)):
        try:
            import update_state as us
            state = us.load()
            today = datetime.now(timezone.utc).date().isoformat()
            affected = sorted({v.get("app") for v in app_vulns if v.get("app")})
            # also include apps in state if generic app vuln reported
            if not affected:
                affected = sorted((state.get("apps") or {}).keys())
            for slug in affected:
                cur = us.app_version(state, slug)
                new_ver = us.bump(cur, "patch")
                desc = str(plan.get("summary") or "Security and stability update applied.").strip()
                notes = ["Security hardening", "Bug/glitch fixes", "Stability improvements"]
                for au in (plan.get("app_updates") or []):
                    if isinstance(au, dict) and str(au.get("app") or "") == slug:
                        desc = str(au.get("description") or desc)
                        n = au.get("notes")
                        if isinstance(n, list) and n:
                            notes = [str(x) for x in n[:6]]
                us.set_app_update(state, slug, version=new_ver,
                                  title="Security and stability update",
                                  description=desc[:1200], notes=notes,
                                  download_url="https://tbougnar.github.io/Slingshot-Tools/",
                                  restart_required=True)
                result["updates_published"].append({"app": slug, "version": new_ver})
            if affected:
                state["last_update_title"] = "Security and stability update"
                state["last_update_description"] = str(plan.get("summary") or "Kerit AI monitor detected issues and queued updates.")[:1200]
                state["last_update_notes"] = ["Security hardening", "Bug fixes", "Stability improvements"]
                state["last_update_at"] = today
                us.save(state)
                us.publish_public(state)
                result["actions"].append({"action": "publish_update_manifest", "ok": True, "apps": affected})
        except Exception as e:
            result["actions"].append({"action": "publish_update_manifest", "ok": False, "error": str(e)[:160]})

    # On-the-spot AI fix attempts for pending glitches (syntax/invalid json in safe files)
    for g in pending_glitches[:10]:
        rel = str(g.get("file") or "")
        if not rel or ".." in rel.replace("\\", "/"):
            continue
        p = ROOT / rel
        if not p.exists() or p.suffix.lower() not in {".py", ".json"}:
            continue
        txt = read_text(p)
        if not txt:
            continue
        system_fix = (
            "You are the Slingshot AI dev team. Fix the reported file error. "
            "Return ONLY the full corrected file content, no markdown fences, no explanation."
        )
        user_fix = f"File: {rel}\nError: {g.get('detail','')}\n\nCurrent content:\n{txt[:12000]}"
        fixed = _ai_chat(system_fix, user_fix)
        if not fixed or len(fixed) < 10:
            continue
        if fixed.strip().startswith("```"):
            fixed = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", fixed.strip())
            fixed = re.sub(r"\n?```$", "", fixed)
        ok = False
        try:
            if p.suffix.lower() == ".py":
                compile(fixed, rel, "exec")
                p.write_text(fixed, encoding="utf-8")
                ok = True
            elif p.suffix.lower() == ".json":
                obj = json.loads(fixed)
                write_json(p, obj)
                ok = True
        except Exception as e:
            result["actions"].append({"file": rel, "action": "ai_fix_on_spot", "ok": False, "error": str(e)[:140]})
            continue
        if ok:
            result["actions"].append({"file": rel, "action": "ai_fix_on_spot", "ok": True})

    # Persist task/report
    tasks = load_json(TASKS, [])
    if not isinstance(tasks, list):
        tasks = []
    task["result"] = result
    tasks = (tasks + [task])[-200:]
    write_json(TASKS, tasks)
    result["tasks_created"] = 1
    log(f"AI dev team handoff: vulns={len(vulns)} app_vulns={len(app_vulns)} pending_glitches={len(pending_glitches)} updates={len(result['updates_published'])}")
    return result

# ----------------------------- 24/7 loop -----------------------------

def run_monitor_cycle() -> dict:
    started = time.time()
    findings = scan_system()
    auto_fixes = auto_fix_glitches(findings)
    handoff = {"tasks_created": 0, "updates_published": [], "actions": []}
    needs_handoff = bool(findings.get("vulnerabilities") or findings.get("app_vulnerabilities"))
    # also handoff glitches that couldn't be fixed on spot
    unfixed = [g for g in findings.get("glitches", []) if not any(f.get("file")==g.get("file") and f.get("ok") for f in auto_fixes)]
    if needs_handoff or unfixed:
        handoff = handoff_to_ai_dev_team(findings, auto_fixes)

    report = {
        "ts": now_iso(),
        "duration_s": round(time.time() - started, 2),
        "stats": findings.get("stats", {}),
        "counts": {
            "glitches": len(findings.get("glitches", [])),
            "vulnerabilities": len(findings.get("vulnerabilities", [])),
            "app_vulnerabilities": len(findings.get("app_vulnerabilities", [])),
            "auto_fixes": len([f for f in auto_fixes if f.get("ok")]),
            "handoff_tasks": handoff.get("tasks_created", 0),
        },
        "auto_fixes": auto_fixes[:80],
        "handoff": handoff,
        "findings": {
            "glitches": findings.get("glitches", [])[:40],
            "vulnerabilities": findings.get("vulnerabilities", [])[:40],
            "app_vulnerabilities": findings.get("app_vulnerabilities", [])[:40],
        },
    }
    write_json(REPORT, report)

    # append fix log
    flog = load_json(FIXLOG, [])
    if not isinstance(flog, list):
        flog = []
    if auto_fixes or handoff.get("tasks_created"):
        flog = (flog + [{"ts": report["ts"], "auto_fixes": auto_fixes, "handoff": handoff}])[-200:]
        write_json(FIXLOG, flog)

    log(f"cycle done: glitches={report['counts']['glitches']} vulns={report['counts']['vulnerabilities']} app_vulns={report['counts']['app_vulnerabilities']} fixed={report['counts']['auto_fixes']} handoffs={report['counts']['handoff_tasks']}")
    return report


def monitor_loop(stop_event=None) -> None:
    interval = max(60, int(os.environ.get("SLINGSHOT_AI_MONITOR_INTERVAL", "600")))
    log(f"24/7 AI monitor started (interval={interval}s)")
    while True:
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            log("monitor stop requested")
            return
        try:
            run_monitor_cycle()
        except Exception as e:
            log(f"monitor cycle error: {str(e)[:180]}")
            traceback.print_exc()
        # sleep in small chunks so stop_event is responsive
        for _ in range(max(1, interval // 5)):
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                return
            time.sleep(5)


def start_background(stop_event=None):
    import threading
    t = threading.Thread(target=monitor_loop, args=(stop_event,), daemon=True, name="kerit-ai-monitor")
    t.start()
    return t


if __name__ == "__main__":
    run_monitor_cycle()
