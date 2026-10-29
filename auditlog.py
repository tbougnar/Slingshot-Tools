"""A structured record of what the automation actually did.

Everything in this system used to report itself by printing. A line in a CI log
is not a record: it is not queryable, it has no identity, it cannot be joined to
the job that caused it, and it disappears when the run ends. So when a release
quietly failed to publish, there was nothing afterwards to ask.

This writes one JSON object per event, one line each, so the file is both
append-only and greppable. Each event carries:

  ts        when it happened, UTC
  event     a name from the fixed vocabulary below
  stage     which part of the workflow this was
  cid       correlation id, shared by every event of one job
  job       the job or product id
  action    what was asked for, and by which component
  reason    why, with the evidence that led to it
  tool      the script, API or integration invoked
  result    sanitised outcome
  evidence  files, exit codes, URLs, test results
  error     the failure and any recovery taken

Statuses are a fixed vocabulary, not free text, so a query can separate a thing
that was attempted from a thing that happened:

  PLANNED STARTED SUCCEEDED FAILED RETRIED ROLLED_BACK BLOCKED NOT_VERIFIED

Two rules are enforced rather than hoped for. A secret never reaches the file:
every value passes through _scrub, which drops anything that looks like a key,
and the module refuses to write a value it has redacted from a key we asked to
keep. And SUCCEEDED is never inferred: a caller has to say the evidence that
made it succeed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG = DATA / "audit" / "events.jsonl"

# AUDITLOG_PATH lets a test, or a job that wants its own file, point the log
# somewhere specific. It must be an absolute path inside the repository or the
# environment, because a relative one is resolved against whatever directory
# the job happens to run in and the log disappears.
_env_log = os.environ.get("AUDITLOG_PATH", "").strip()
if _env_log:
    LOG = Path(_env_log)

STATUSES = ("PLANNED", "STARTED", "SUCCEEDED", "FAILED", "RETRIED",
            "ROLLED_BACK", "BLOCKED", "NOT_VERIFIED")

# Keep the file from growing without bound in a repo that is committed forever.
MAX_BYTES = 8 * 1024 * 1024
KEEP_AFTER_ROTATE = 2

# Anything shaped like a credential is replaced before it is written. The point
# is that a log can be committed and published without thinking about it.
_PATTERNS = [
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|cookie|session)"
               r"(\"?\s*[:=]\s*\"?)([^\s\"',}]{6,})"), r"\1\2<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "<redacted>"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{16,}"), "<redacted>"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), "<redacted>"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{16,}"), "<redacted>"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "<redacted>"),
    (re.compile(r"(?i)(itch[_-]session[_-]?cookie\s*[:=]\s*)\S+"), r"\1<redacted>"),
    # A value that follows a name ending in COOKIE or SECRET is a credential
    # whatever the separator, including the = sign the generic rule above did
    # not match because the name contains an underscore-heavy suffix.
    (re.compile(r"(?i)\b([A-Za-z0-9_]*(?:cookie|secret|token|passwd|api_key)"
               r"[A-Za-z0-9_]*)\s*=\s*([^\s\"',}]{6,})"), r"\1=<redacted>"),
]

_cid = ""

# A key that names a credential means the value is one, however ordinary the
# value looks. The patterns above need the name and the value side by side in
# one string, and in a dict they are two separate strings, so a credential
# held as a dict value was written to the log as it was. The log is a tracked
# file in a public repository, so that is a secret in plain sight.
_CRED_NAME = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|cookie|session"
    r"|authorization|credential|bearer|refresh)")


def correlation_id() -> str:
    """The id shared by everything one job does.

    Taken from the environment when the CI provides one, so the generate job
    and the verify job it triggers can be joined. Otherwise generated once and
    kept for the life of the process.
    """
    global _cid
    if not _cid:
        _cid = (os.environ.get("SLINGSHOT_CID")
                or os.environ.get("GITHUB_RUN_ID", "")
                or uuid.uuid4().hex[:12])
    return _cid


def scrub(value):
    """Return value with anything credential-shaped replaced."""
    if isinstance(value, str):
        for pattern, repl in _PATTERNS:
            value = pattern.sub(repl, value)
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _CRED_NAME.search(k):
                out[scrub(k)] = "<redacted>"
                continue
            out[scrub(k)] = scrub(v)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def _rotate() -> None:
    """Keep events.jsonl plus a couple of older files.

    Without this the log grows forever in a repository that is kept forever.
    Rotation never deletes the newest file, so a crash mid-rotation still
    leaves a readable record of the run that caused it.
    """
    try:
        if not LOG.exists() or LOG.stat().st_size < MAX_BYTES:
            return
        for i in range(KEEP_AFTER_ROTATE, 0, -1):
            older = LOG.with_suffix(f".jsonl.{i}")
            newer = (LOG if i == 1
                     else LOG.with_suffix(f".jsonl.{i - 1}"))
            if newer.exists():
                if older.exists():
                    older.unlink()
                older.write_bytes(newer.read_bytes())
        # The newest file has just been copied to .1, so it is emptied
        # rather than deleted. It used to be deleted, which is the opposite
        # of what this function says it does: read() only ever read the
        # newest file, so past the size limit the whole audit trail became
        # empty and the report that depends on it reported nothing.
        LOG.write_bytes(b"")
    except OSError:
        # Rotation is housekeeping. Failing to do it must never lose the event
        # that is being written right now.
        pass


def _read_one(path: Path) -> list[dict]:
    """Every event in one log file, skipping a torn last line."""
    out = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            # A torn final line after a kill is expected and must not hide the
            # events before it.
            continue
    return out


def read(limit: int = 0) -> list[dict]:
    """Read events back, newest last. Used by the tests and by tooling.

    The rotated files are read too, oldest first, so the trail is continuous
    across a rotation instead of starting again from nothing.
    """
    out = []
    # Rotations live next to the live log (data/audit/events.jsonl.N), not in
    # the repository root. Globbing ROOT found none of them, so every event
    # before the last rotation silently disappeared from the trail.
    for path in reversed(sorted(LOG.parent.glob(LOG.name + ".*"),
                                key=lambda p: p.name)):
        if not path.is_file():
            continue
        out += _read_one(path)
    if LOG.exists():
        out += _read_one(LOG)
    return out[-limit:] if limit else out


def write(event: str, stage: str = "", job: str = "", action: str = "",
          reason: str = "", tool: str = "", result: str = "",
          evidence: dict | None = None, error: str = "",
          cid: str | None = None, **extra) -> dict:
    """Append one event. Returns it, scrubbed, so callers can log what is safe."""
    if event not in STATUSES:
        # An unknown status would make the log unqueryable, so it is named
        # rather than silently accepted as something it is not.
        event = "NOT_VERIFIED"
        result = f"unknown status requested; recorded as NOT_VERIFIED ({result})"
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        "stage": stage,
        "cid": cid or correlation_id(),
        "job": job,
        "action": action,
        "reason": reason,
        "tool": tool,
        "result": result,
        "evidence": evidence or {},
        "error": error,
    }
    rec.update(extra)
    rec = scrub(rec)
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        # appended and flushed, so an exception or a kill -9 right after this
        # still leaves the event on disk
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        _rotate()
    except OSError as e:
        # The log must not be the reason a release fails, but the failure has
        # to be visible, because a silently missing log is the defect this
        # module was written to remove.
        print(f"[audit] could not write the event log: {e}", file=sys.stderr)
    return rec


# Convenience wrappers, so call sites read as the thing they mean.
def planned(stage: str, **kw):
    return write("PLANNED", stage=stage, **kw)


def started(stage: str, **kw):
    return write("STARTED", stage=stage, **kw)


def succeeded(stage: str, evidence: dict | None = None, **kw):
    if not evidence:
        raise ValueError(
            "a SUCCEEDED event needs evidence; a log line that says it worked "
            "is the defect this module exists to remove")
    return write("SUCCEEDED", stage=stage, evidence=evidence, **kw)


def failed(stage: str, error: str = "", **kw):
    return write("FAILED", stage=stage, error=error, **kw)


def retried(stage: str, reason: str = "", **kw):
    return write("RETRIED", stage=stage, reason=reason, **kw)


def rolled_back(stage: str, reason: str = "", **kw):
    return write("ROLLED_BACK", stage=stage, reason=reason, **kw)


def blocked(stage: str, reason: str = "", **kw):
    return write("BLOCKED", stage=stage, reason=reason, **kw)


def not_verified(stage: str, reason: str = "", **kw):
    return write("NOT_VERIFIED", stage=stage, reason=reason, **kw)


if __name__ == "__main__":
    events = read(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    for e in events:
        print(f"{e['ts']} {e['event']:13s} {e['stage']:16s} {e['result'][:60]}")
    print(f"\n{len(events)} event(s) in {LOG.relative_to(ROOT)}")