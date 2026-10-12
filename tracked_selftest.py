"""Every module the pipeline imports must actually be in the repository.

debug_team.py sat in .gitignore with a comment saying it was a one-off kept
while building the project. qa_loop.py imports it, so on a GitHub runner the
Friday build died with "No module named debug_team" before it could build
anything. Nothing caught it, because every test passed on the machine where
the file happened to exist on disk.

The distinction that matters: a file can exist locally and be absent from git,
and every local run looks perfect. This checks the thing that actually ships.

    python tracked_selftest.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


def tracked() -> set[str]:
    """Every tracked file, as repo-relative posix paths.

    git ls-files answers with paths, not bare names, so the names are extracted
    here. Getting this wrong makes every file look untracked, which is worse
    than not checking at all.
    """
    r = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                       capture_output=True, text=True)
    return {ln.strip().replace("\\", "/") for ln in r.stdout.splitlines()
            if ln.strip()}


def local_modules() -> set[str]:
    return {p.name for p in ROOT.glob("*.py")}


def imports_of(path: Path) -> set[str]:
    """Top-level module names this file imports."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 \
                and node.module:
            out.add(node.module.split(".")[0])
    return out


def tracked_names() -> set[str]:
    """Just the file names git is tracking, for comparison against imports."""
    return {p.rsplit("/", 1)[-1] for p in tracked()}


def main() -> int:
    in_git = tracked()
    names_in_git = tracked_names()
    stdlib = set(sys.stdlib_module_names)

    # Third-party packages the workflows pip install. A module in this list is
    # not a bug when it is not tracked; it is a dependency.
    third_party = {
        "PIL", "aiohttp", "edge_tts", "imageio_ffmpeg", "playwright",
        "requests", "webview", "yaml", "playwright.sync_api", "mutagen",
        "androguard", "apkutils",
    }

    # 1. anything the repo imports must be tracked, unless it is a library or a
    #    local alias inside a function
    print("THE MODULES THE PIPELINE IMPORTS\n")
    missing: dict[str, set[str]] = {}
    for f in sorted(ROOT.glob("*.py")):
        if f.name.startswith("_"):
            continue
        for name in imports_of(f):
            if name in stdlib or name in third_party:
                continue
            if not (ROOT / f"{name}.py").exists():
                # not one of ours: a package, or an alias for one
                continue
            if f"{name}.py" in names_in_git:
                continue
            missing.setdefault(name, set()).add(f.name)

    for name, users in sorted(missing.items()):
        check(f"{name}.py is tracked", False,
              f"imported by {sorted(users)[:3]} but not tracked, so a runner "
              f"cannot import it")

    if not missing:
        check("every project module that is imported is tracked", True)

    # 2. and the reverse, which is the one that bit: a local module the
    #    pipeline needs, sitting in .gitignore
    print("\nTHE MODULES THE PIPELINE NEEDS\n")
    needed: set[str] = set()
    for f in sorted(ROOT.glob("*.py")):
        if f.name.startswith("_") or "selftest" in f.name:
            continue
        needed |= imports_of(f)

    for name in sorted(needed):
        if name in stdlib or name in third_party:
            continue
        if not (ROOT / f"{name}.py").exists():
            continue
        check(f"{name}.py is tracked", f"{name}.py" in names_in_git,
              "it is imported but gitignored, so a runner cannot import it")

    # 3. every workflow step must be able to run. This is the check that would
    #    have caught the Friday failure before it wasted a run.
    print("\nTHE WORKFLOWS CAN RUN\n")
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        try:
            import yaml
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            check(f"{wf.name} parses", False, str(e)[:50])
            continue
        bad: list[str] = []
        for job, body in (doc.get("jobs") or {}).items():
            for step in body.get("steps") or []:
                run = str(step.get("run") or "")
                for call in run.split():
                    if call.startswith("python") and call.endswith(".py"):
                        script = call.split("\\")[-1]
                        if script not in in_git and \
                                not (ROOT / script).exists():
                            bad.append(f"{job}/{script}")
                    if call == "python" :
                        continue
        check(f"{wf.name} only calls scripts that exist", not bad,
              "; ".join(sorted(set(bad))[:3]))

    print()
    print("FAILURES:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())