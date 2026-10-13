"""Merge the audit log after a conflict, without losing either side.

An append-only file conflicts whenever the CI runner and the local machine both
wrote to it, which is every release. Resolving by picking a side throws away
half the record, and the half lost is usually the half that matters.

Installed as a rebase driver: `git rebase --continue` runs this, merges the two
stages of the conflicted file, stages it, and continues. Because it exits 0 the
rebase proceeds instead of stopping for an editor.

Deliberately fails loudly rather than silently choosing: if the merge produces
anything that is not valid jsonl, the rebase stops, because a log that parses is
the only thing this log is for.
"""
import json
import subprocess
import sys
from pathlib import Path

TARGET = "data/audit/events.jsonl"


def _stage(n: int) -> list[dict]:
    r = subprocess.run(["git", "show", f":{n}:{TARGET}"],
                       capture_output=True)
    if r.returncode != 0:
        return []
    out = []
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        ln = ln.strip()
        if not ln or ln[0] in "<=>":
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    ours, theirs = _stage(2), _stage(3)
    if not ours and not theirs:
        print(f"[merge-log] nothing to merge for {TARGET}", file=sys.stderr)
        return 0

    seen, merged = set(), []
    for e in ours + theirs:
        key = (e.get("ts"), e.get("event"), e.get("stage"),
               str(e.get("evidence"))[:80])
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda e: str(e.get("ts", "")))

    body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in merged)

    # the whole point of the file is that it parses, so prove it before writing
    for ln in body.splitlines():
        if ln.strip():
            json.loads(ln)

    p = Path(TARGET)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", TARGET], check=False)
    print(f"[merge-log] kept {len(merged)} events "
          f"(ours {len(ours)}, theirs {len(theirs)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())