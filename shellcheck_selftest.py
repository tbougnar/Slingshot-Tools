"""Which steps write bash syntax into a job that runs on PowerShell?

This caught a real defect: a gate step added to the installer job used "$VAR",
[[ ]]-style conditionals and $GITHUB_OUTPUT, but that job's runner is
windows-latest, where the default shell is pwsh. The step failed with a
ParserError before it ran any of its logic, so the gate never actually gated
anything.
"""
import pathlib

import yaml

# Only constructs pwsh genuinely cannot run. "$VAR" is not here because pwsh
# reads it, "fi" is not here because it appears inside ordinary words, and
# "&&" and "||" are not here because pwsh 7 supports both.
BASH_MARKERS = ("$GITHUB_OUTPUT", "$GITHUB_STEP_SUMMARY", "$GITHUB_PATH",
                'if [ "', 'elif [ "', "&& export", "fi\n", "<<EOF",
                "cat <<", "source ", "apt-get", "chmod +x")


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    bad = []
    checked = 0
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job, jd in (data.get("jobs") or {}).items():
            runs_on = str(jd.get("runs-on", ""))
            windows = "windows" in runs_on
            for step in jd.get("steps", []) or []:
                run = str(step.get("run", ""))
                if not run:
                    continue
                checked += 1
                shell = str(step.get("shell", "")).lower()
                forced_bash = shell.startswith("bash")
                forced_ps = "pwsh" in shell or "powershell" in shell
                if forced_bash or forced_ps:
                    continue
                if not windows:
                    continue
                # a windows runner defaults to pwsh; bash syntax there is a bug
                hits = [m for m in BASH_MARKERS
                        if m in run and not m.startswith("${{")]
                if hits:
                    bad.append((wf.name, job, step.get("name"), hits))
    print(f"checked {checked} steps across the workflows")
    for f, j, n, h in bad:
        print(f"  {f} :: {j} :: {n!r}")
        print(f"      bash syntax on a windows runner: {h}")
    print()
    if bad:
        print(f"FAILURES: {len(bad)} step(s) mix bash syntax into pwsh")
        return 1
    print("FAILURES: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())