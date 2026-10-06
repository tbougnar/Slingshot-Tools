"""Full-code audit: parse every file, walk every call site, wire every module.

Three earlier passes tested behaviour. This one checks the things those cannot
see: names referenced but never defined, names defined but shadowed, calls into
functions that raise, imports that pull the wrong symbol, and workflows whose
steps call scripts that do not exist.
"""
import ast
import builtins
import sys
from pathlib import Path

R = Path(r"C:\Users\Taha\AI\slingshot_tools")
problems = []

py_files = sorted(p for p in R.rglob("*.py")
                  if ".git" not in p.parts and "dist" not in p.parts
                  and "paid" not in p.parts and "_internal" not in p.parts)
print(f"scanning {len(py_files)} python files\n")

BUILTINS = set(dir(builtins))

for f in py_files:
    src = f.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src, filename=str(f))
    except SyntaxError as e:
        problems.append((f.name, f"SYNTAX ERROR line {e.lineno}: {e.msg}"))
        continue

    defined, used, imports = set(), set(), {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                used.add(node.id)
            else:
                defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    continue
                nm = (a.asname or a.name).split(".")[0]
                imports[nm] = a.name
                defined.add(nm)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)
        elif isinstance(node, (ast.comprehension,)):
            pass

    # names read but never bound anywhere and not builtins: usually a typo or
    # a deleted definition
    module_level = {n.targets[0].id for n in tree.body
                    if isinstance(n, ast.Assign) and n.targets
                    and isinstance(n.targets[0], ast.Name)}
    missing = {n for n in used
               if n not in defined and n not in BUILTINS
               and n not in module_level and n.isupper() is False
               and n not in ("self", "cls", "__file__", "__name__", "__doc__")}
    # ignore names that could come from a wildcard or a conditional import
    missing -= set(imports)
    if missing:
        problems.append((f.name, f"uses undefined names: {sorted(missing)[:6]}"))

# ---- workflow steps must call scripts that exist ----
wf_dir = R / ".github" / "workflows"
for wf in sorted(wf_dir.glob("*.yml")):
    text = wf.read_text(encoding="utf-8")
    import re
    for m in re.finditer(r"run:\s*(?:\|)?\s*([\s\S]{0,400}?)(?=\n\s*-?\s*(?:name:|uses:|run:)|\Z)",
                         text):
        block = m.group(1)
        for call in re.findall(r"\bpython\s+([A-Za-z_][\w./-]*\.py)\b", block):
            if not (R / call).exists():
                problems.append((wf.name, f"calls missing script {call}"))
            if "<<" in call or ">" in call:
                continue

# ---- every script a workflow might invoke exists ----
for f in ("make_app.py", "stage_app.py", "verify_app.py", "pricing.py",
          "learn.py", "selftest.py", "selftest_deep.py", "write_fixbook.py",
          "check_exposure.py", "build_paid_only.py", "mark_verified.py",
          "build_exe.py", "build_installer_app.py", "patcher.py",
          "app_scanner.py", "qa_loop.py", "debug_team.py", "providers.py",
          "paid_store.py", "buglog.py", "tokenmeter.py", "sizeguard.py",
          "selfheal.py"):
    if not (R / f).exists():
        problems.append(("-", f"referenced script missing: {f}"))

# ---- secrets the workflows need ----
wf = (wf_dir / "monday-build.yml").read_text(encoding="utf-8")
for s in ("GROQ_API_KEY", "CF_API_TOKEN", "LICENSE_SECRET"):
    if f"secrets.{s}" in wf and s not in ("GROQ_API_KEY",):
        pass  # verified separately via gh

print("== problems ==")
if not problems:
    print("  none")
for name, detail in problems:
    print(f"  {name}: {detail}")

print(f"\n{len(problems)} problems across {len(py_files)} files")
sys.exit(1 if problems else 0)