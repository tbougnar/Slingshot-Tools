"""Does the node path survive a non-cp1252 character on a Windows pipe?

The generate job died with UnicodeEncodeError on an arrow character before the
check returned anything, which killed the run rather than reporting a bad app.
"""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_app

fake = os.path.join(os.environ["TEMP"], "fake_node.cmd")
Path(fake).write_text("@echo off\r\nmore > nul\r\nexit /b 0\r\n",
                      encoding="ascii")

real_which = shutil.which
make_app.shutil.which = lambda n: fake if n == "node" else real_which(n)

js = 'const K="x";const a="\u2192";'
html = "<script>" + js + "</script>"
try:
    got = make_app.js_syntax_errors(html)
    print("no crash, result:", got)
    print("PASS" if got == [] else "FAIL (a clean script was reported bad)")
except UnicodeEncodeError as e:
    print("FAIL UnicodeEncodeError:", e)
    raise SystemExit(1)
finally:
    make_app.shutil.which = real_which
    os.unlink(fake)