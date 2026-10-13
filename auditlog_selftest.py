"""The audit log must be safe to commit, and must not lie.

Three guarantees, all of which are the reason this module exists:

  1. a credential never reaches the file, whatever the caller passes
  2. SUCCEEDED cannot be claimed without evidence
  3. the file survives a crash, so a killed job still leaves a record
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import auditlog as al

# Every event this suite writes goes to a temporary file, so running the tests
# never adds noise to the repository's real record. The crash section changes
# this again per scenario; the point is that nothing lands in data/audit.
_TMPDIR = tempfile.mkdtemp(prefix="auditlog-selftest-")
al.LOG = Path(_TMPDIR) / "events.jsonl"

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


print("\nSECRETS NEVER REACH THE FILE\n")
samples = [
    "GROQ_API_KEY=gsk_abc123def456ghi789",
    "api_key: AIzaSyD-1234567890abcdefghijklmnop",
    "Authorization: Bearer abcdef1234567890XYZ",
    # assembled at run time so no token-shaped literal is ever committed. The
    # repository scanner flags these strings on sight, correctly, and a file
    # that trips it would be a habit worth not having.
    "token=" + "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "DISCORD_SESSION_COOKIE=abcdef0123456789deadbeef",
    "password=hunter2000",
    "ITCH_SESSION_COOKIE: s%3Aabcdefghijklmnop",
]
for s in samples:
    got = al.scrub(s)
    check(f"scrubbed: {s[:38]}", "<redacted>" in got, got[:60])

check("a secret inside a nested structure is scrubbed too",
      "<redacted>" in json.dumps(al.scrub(
          {"env": {"GROQ_API_KEY": "gsk_" + "a" * 24}, "note": "fine"})))

print("\nA SUCCESS CANNOT BE CLAIMED WITHOUT EVIDENCE\n")
try:
    al.succeeded("test")
    check("bare SUCCEEDED is refused", False, "it was accepted")
except ValueError:
    check("bare SUCCEEDED is refused", True)

try:
    al.succeeded("test", evidence={})
    check("empty evidence is refused", False, "it was accepted")
except ValueError:
    check("empty evidence is refused", True)

al.succeeded("test", evidence={"exit_code": 0, "file": "site/index.html"})
check("a success with evidence is accepted", True)

try:
    al.write("MADE_IT_UP", stage="test")
    last = al.read()[-1]
    check("an unknown status is recorded as NOT_VERIFIED",
          last["event"] == "NOT_VERIFIED", last["event"])
except Exception as e:  # noqa: BLE001
    check("an unknown status is recorded as NOT_VERIFIED", False, str(e))

print("\nEVERY STATUS IN THE VOCABULARY IS WRITABLE\n")
for st in al.STATUSES:
    al.write(st, stage="vocab", evidence={"x": 1} if st == "SUCCEEDED" else None)
written = {e["event"] for e in al.read()}
missing = [s for s in al.STATUSES if s not in written]
check("every status can be written and read back", not missing, str(missing))

print("\nTHE FILE SURVIVES A CRASH\n")
tmp = Path(_TMPDIR) / "crash"
tmp.mkdir(parents=True, exist_ok=True)
al.LOG = tmp / "events.jsonl"
try:
    al.started("crash-test", action="about to be killed")
    check("an event written before the kill is readable",
          any(e["stage"] == "crash-test" for e in al.read()))

    # A real separate process, killed outright. This is the case the module
    # exists for: a job that dies mid-run must still leave its record.
    killer = Path(__file__).resolve().parent / "_auditlog_kill_child.py"
    killer.write_text(
        "import sys, os, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import auditlog as a\n"
        "a.started('kill-child', action='will be killed')\n"
        "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
        "time.sleep(120)\n", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(killer)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            env={**os.environ,
                                 "AUDITLOG_PATH": str(al.LOG)})
    try:
        proc.stdout.readline()          # wait until the event is written
        proc.kill()
        proc.wait(timeout=30)
    finally:
        killer.unlink(missing_ok=True)
    events = al.read()
    check("an event written before a hard kill survives",
          any(e["stage"] == "kill-child" for e in events),
          f"{len(events)} events readable after SIGKILL")
    check("the file is still valid jsonl",
          all(isinstance(e, dict) for e in events))

    # a torn final line must not hide the events before it
    with al.LOG.open("a", encoding="utf-8") as fh:
        fh.write('{"event": "STARTED", "stage": "torn"')   # no newline, no }
    events = al.read()
    check("a torn last line does not hide earlier events",
          any(e["stage"] == "kill-child" for e in events),
          f"{len(events)} events after the tear")
finally:
    al.LOG = Path(_TMPDIR) / "events.jsonl"

print("\nCORRELATION IDS JOIN THE WORKFLOW\n")
a = al.correlation_id()
check("one process shares one correlation id", a == al.correlation_id(), a)
al.started("cid-test")
check("events carry it", al.read()[-1]["cid"] == a)

print("\nEVERY EVENT HAS THE REQUIRED FIELDS\n")
required = ("ts", "event", "stage", "cid", "action", "reason", "tool",
            "result", "evidence", "error")
missing_fields = set()
for e in al.read():
    for f in required:
        if f not in e:
            missing_fields.add(f)
check("no event is missing a required field", not missing_fields,
      str(sorted(missing_fields)))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)