"""Regression tests for the bugs the whole-project scan found.

Each one was a real defect that shipped, so each gets a check that fails if it
comes back. The list is deliberately short and specific: a test that cannot
fail on the bug it is named after is worse than no test.

    python scan_selftest.py
"""
from __future__ import annotations

import ast
import importlib
from testenv import clean_env
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


# ---- 1. discord_post logged an undefined name on the 403 path
import discord_post as dp

_real_rest, _real_find = dp._rest, dp.find_channel
try:
    dp.TOKEN, dp.GUILD_ID = "t", "1"
    dp.find_channel = lambda name, fresh=False: "99"
    cases = [(200, [{"id": "1"}]), (403, []), (404, []),
             (429, []), (500, [])]
    for code, want in cases:
        # a 200 has to carry a list, because that is what the real API sends
        body = [{"id": "1"}] if code == 200 else "x"
        dp._rest = lambda m, p, body=None, _c=code, _b=body: (_c, _b)
        try:
            got = dp.messages("announcements", 5)
        except Exception as e:  # noqa: BLE001
            got = f"raised {type(e).__name__}: {e}"
        check(f"messages() survives HTTP {code}", got == want, str(got))
finally:
    dp._rest, dp.find_channel = _real_rest, _real_find

# the source must not name an undefined identifier in that branch
src = (ROOT / "discord_post.py").read_text(encoding="utf-8")
fn = src[src.find("def messages("):src.find("def find_message(")]
check("the 403 branch does not mention a bare 'name'",
      "cannot read #{name}" not in fn)


# ---- 2. groq_live_check shadowed the module global
import groq_live_check as gq

for label, value, expect in (("empty", "", "no key"),
                             ("wrong prefix", "sk-abc", "does not look"),
                             ("a real looking key", "gsk_" + "0" * 20, "")):
    got = gq.main(value)
    check(f"groq_live_check handles a {label} key",
          got == 1 and isinstance(got, int), f"returned {got}")
try:
    importlib.reload(gq)
    check("the module still imports after reload", True)
except Exception as e:  # noqa: BLE001
    check("the module still imports after reload", False, str(e)[:60])


# ---- 3. the fixbook and the coach must not share a file
import buglog
import learn

check("the coach does not write the fixbook's lessons file",
      learn.LESSONS != buglog.LESSONS,
      f"{learn.LESSONS.name} vs {buglog.LESSONS.name}")
check("the coach's file is its own",
      learn.LESSONS.name == "coach_lessons.txt", learn.LESSONS.name)
check("the fixbook keeps lessons.txt",
      buglog.LESSONS.name == "lessons.txt", buglog.LESSONS.name)


# ---- 4. nothing anywhere may reference a name that does not exist
def undefined_names(tree: ast.AST, source: str) -> set[str]:
    """Names read but never bound, ignoring builtins and module constants."""
    import builtins

    bound: set[str] = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)

    missing = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id not in bound):
            missing.add(node.id)
    return missing


bad_files = []
for f in sorted(ROOT.glob("*.py")):
    if f.name.startswith("_"):
        continue
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as e:
        bad_files.append(f"{f.name}: {e}")
        continue
    missing = undefined_names(tree, f.read_text(encoding="utf-8"))
    # names defined only by an import inside a function are still bound, and
    # __file__ / __name__ are module dunders
    missing -= {"__file__", "__name__", "__doc__"}
    if missing:
        bad_files.append(f"{f.name}: {sorted(missing)[:4]}")

check("no file reads a name it never binds", not bad_files,
      "; ".join(bad_files[:3]))


# ---- 5. the coach must honour the model's own keep list
check("the coach reads the keep field",
      'd.get("keep")' in (ROOT / "learn.py").read_text(encoding="utf-8"))
check("and prefers it over the subtraction",
      "if keep:" in (ROOT / "learn.py").read_text(encoding="utf-8"))


# ---- 6. the stage wait must use the real allowance check
stage = (ROOT / "stage_app.py").read_text(encoding="utf-8")
check("the build waits on affordable(), not on spent()",
      "tokenmeter.affordable(limit, need)" in stage)
check("the bare spent()>0 wait is gone",
      "while tokenmeter.spent() > 0" not in stage)


# ---- 7. the model that worked must be remembered
mk = (ROOT / "make_app.py").read_text(encoding="utf-8")
body = mk[mk.find("def groq("):mk.find("def _salvage_html(")]
check("groq() assigns to CHAT_MODEL", "CHAT_MODEL = model" in body)
check("and it keeps the global declaration", "global CHAT_MODEL" in body)


# ---- 8. the protected-commit audit must actually use the guard
audit = (ROOT / "selftest_audit.py").read_text(encoding="utf-8")
check("the audit calls the guard, not a substring test",
      "_guard.is_protected(" in audit)
check("the old substring check is gone",
      '"site/index.html", "check_exposure.py "' not in audit)


# ---- 9. nothing may be left in the public site that should not ship


def _site_side_effects() -> list[str]:
    """Import every module in a fresh interpreter and see what appears.

    paypal.py created site/licenses when it was imported, which is what this
    exists to catch: the folder is gitignored, so it never showed up in a
    diff, but Pages serves it and check_exposure.py fails the release over it.
    """
    import shutil
    import subprocess

    site = ROOT / "site"
    before = {p.name for p in site.iterdir()}
    mods = [p.stem for p in ROOT.glob("*.py")
            if not p.stem.startswith("_") and "selftest" not in p.stem]
    script = ("import importlib\n"
              f"for m in {mods!r}:\n"
              "    try:\n"
              "        importlib.import_module(m)\n"
              "    except Exception:\n"
              "        pass\n")
    # Every module is imported here, and some of them talk to a service at
    # import time. The child gets the scrubbed environment, so a module with
    # an import-time side effect cannot reach the real service.
    subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                   env=clean_env(),
                   capture_output=True, timeout=180)
    after = {p.name for p in site.iterdir()}
    shutil.rmtree(site / "licenses", ignore_errors=True)
    return [f"appeared: {n}" for n in sorted(after - before)]


check("there is no licenses folder in site/",
      not (ROOT / "site" / "licenses").exists())
check("the exposure check passes",
      importlib.import_module("check_exposure").main() == 0)

# importing a module must never write into the directory GitHub Pages serves
_extra = _site_side_effects()
check("no module creates a folder under site/ at import time",
      not _extra, "; ".join(_extra[:3]))


print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)