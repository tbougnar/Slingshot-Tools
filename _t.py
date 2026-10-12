import pathlib
import re

t = pathlib.Path("selftest_deep.py").read_text(encoding="utf-8")
refs = set(re.findall(r'HERE / "([^"]+)"', t)) | \
    set(re.findall(r'p / "([^"]+)"', t))
print("files selftest_deep needs:")
for r in sorted(refs):
    p = pathlib.Path(r)
    tracked = False
    print(f"  {r:24} on disk={p.exists()}  tracked=?", end="")
    import subprocess
    rc = subprocess.run(["git", "ls-files", "--error-unmatch", r],
                        capture_output=True).returncode
    print("yes" if rc == 0 else "NO")