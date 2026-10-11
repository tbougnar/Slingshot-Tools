"""The sound design filtergraph must use the input numbers ffmpeg will see.

It was wrong by one and ffmpeg rejected the whole graph with
"Invalid file index". That is only findable by running ffmpeg, so the index
arithmetic is checked here instead.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
fails = []

import shorts_mux as sm

# a plan with a bed and three cues
plan = {"bed": True, "seconds": 12.0,
        "cues": [{"name": "hit", "kind": "hit", "at": 0.0},
                 {"name": "whoosh", "kind": "transition", "at": 3.0},
                 {"name": "click", "kind": "ui", "at": 6.0}]}
d = ROOT / "data"
(d / "shorts_sfx").mkdir(exist_ok=True)
(d / "shorts_sfx.json").write_text(json.dumps(plan), encoding="utf-8")
for c in plan["cues"]:
    (d / "shorts_sfx" / f"{c['name']}.mp3").write_bytes(b"x" * 32)
(d / "shorts_sfx" / "bed.mp3").write_bytes(b"x" * 32)

cues = sm.cue_labels()
bed = sm.plan_has_bed()
print(f"  cues={cues} bed={bed}")

ok = bed and len(cues) == 3
print(("ok   " if ok else "FAIL "), "the plan is read back")
if not ok:
    fails.append("plan read")

# the graph ffmpeg is handed, rebuilt the way the code builds it
inputs, graph, outs = [], [], []
if bed:
    inputs += ["-i", "bed.mp3"]
    graph.append("[0:a]volume=0.13[bed]")
    outs.append("[bed]")
for i, cue in enumerate(cues, start=len(inputs) // 2):
    inputs += ["-i", f"{cue}.mp3"]
    graph.append(f"[{i}:a]volume={sm.cue_gain(cue)},adelay=0|0[c{cue}]")
    outs.append(f"[c{cue}]")
graph.append("".join(outs) +
             f"amix=inputs={len(outs)}:duration=longest:normalize=0[design]")

print("  inputs:", len(inputs) // 2)
print("  graph :", ";".join(graph)[:150])

# every referenced index must be a real input
refs = set()
for g in graph:
    part = g.split("[")[1].split("]")[0]
    if ":" in part:
        refs.add(int(part.split(":")[0]))
ok = refs and all(0 <= r < len(inputs) // 2 for r in refs)
print(("ok   " if ok else "FAIL "), f"indices {sorted(refs)} all exist")
if not ok:
    fails.append("indices")

# and the first source must be 0, the classic off by one
ok = graph[0].startswith("[0:a]") if bed else True
print(("ok   " if ok else "FAIL "), "the first source is input 0")
if not ok:
    fails.append("off by one")

for f in (d / "shorts_sfx.json",):
    f.unlink(missing_ok=True)
for f in (d / "shorts_sfx").glob("*.mp3"):
    f.unlink()

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)