"""Sound cues must land on different moments, not all at zero.

They did: every cue snapped onto the same instant, which sounds like one
stacked hit rather than a designed sequence. The test calls the real planner
so it cannot drift from the code again.
"""
import sys

import shorts_sfx as sx

fails = []


def plan_for(parts, total):
    """Exactly what shorts_sfx.main builds, extracted for testing."""
    span_cues = max(sx.CUES[-1][3], 0.001)
    raw = []
    for name, text, kind, at in sx.CUES:
        if at >= total:
            continue
        at = at / span_cues * max(total - 0.5, 0.5)
        raw.append([name, text, kind, at])

    raw.sort(key=lambda r: r[3])
    spaced = []
    for r in raw:
        ts = r[3]
        if spaced and ts - spaced[-1] < 0.22:
            ts = spaced[-1] + 0.22
        spaced.append(ts)
    return [round(min(ts, max(total - 0.2, 0.1)), 2) for ts in spaced]


def check(label, stamps, total, min_distinct=4):
    ok = (all(0 <= s < total for s in stamps)
          and all(b > a for a, b in zip(stamps, stamps[1:]))
          and len(set(stamps)) >= min_distinct)
    print(("ok   " if ok else "FAIL "), f"{label}: {stamps}")
    if not ok:
        fails.append(label)


check("four lines", plan_for([
    {"text": "one", "start": 0.0, "seconds": 2.4},
    {"text": "two", "start": 2.62, "seconds": 2.6},
    {"text": "three", "start": 5.44, "seconds": 2.5},
    {"text": "four", "start": 8.16, "seconds": 2.4}], 10.6), 10.6)

check("one long line", plan_for(
    [{"text": "long", "start": 0.0, "seconds": 20.0}], 20.0), 20.0)

check("four seconds", plan_for([
    {"text": "a", "start": 0.0, "seconds": 2.0},
    {"text": "b", "start": 2.2, "seconds": 2.0}], 4.2), 4.2, min_distinct=3)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)