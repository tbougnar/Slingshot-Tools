"""The design gate has to reject the app that was actually sold.

The password manager that shipped first passed every functional check in the
repository and looked like a form someone filled in in ten minutes: a red
slab across the top for a title, browser-default checkbox, label rows with
nothing beside them, 607 characters of CSS for the whole page. It went on
sale at $3.00. Nothing had ever looked at it.

These checks hold the measurable half of the gate to the mark: the ugly page
must fail, a page built to the spec must pass, and neither may depend on a
model being available. The screenshot review is deliberately not tested here -
this suite runs with no credentials, which is exactly when the gate must fall
back to the static rules instead of raising.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import design_gate

fails = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


# ------------------------------------------------------------------ samples

# Shaped like the app that was rejected: a banner title, no tokens, no
# breakpoint, no focus ring, no layout system, and almost no CSS.
UGLY = """<!DOCTYPE html>
<html><head><style>
body{background:#14100F;color:#F6EFEC;font-family:Arial;margin:0}
h1{background:#C1272D;color:#fff;padding:40px;margin:0;font-size:48px}
.card{background:#F6EFEC;color:#000;padding:8px;border-radius:4px}
button{background:#C1272D;color:#fff;border:0;padding:8px;cursor:pointer}
button:hover{background:#a01f24}
input[type=checkbox]{cursor:pointer}
footer{background:#C1272D;color:#fff;padding:8px}
</style></head>
<body><h1>Passit - Offline Password Manager</h1>
<h2>Passwords</h2><button id="add">Add Password</button>
<div class="card"><p>Username:</p><p>Password:</p><button id="del">Delete</button>
</div>
<label><input type="checkbox" id="dark">Dark Mode</label>
<footer>Full edition</footer>
<script>
document.getElementById('add').addEventListener('click',function(){});
document.getElementById('del').addEventListener('click',function(){});
document.getElementById('dark').addEventListener('change',function(){});
</script></body></html>"""

# Built to APP_SPEC: a palette in :root, both themes, a type scale under 32px,
# a compact header instead of a slab, cards in a grid, restyled controls,
# focus and hover and motion, a constrained measure, and a quiet footer.
GOOD = """<!DOCTYPE html>
<html data-theme="dark"><head><style>
:root{
  --bg:#14100F; --surface:#1E1817; --surface2:#272020;
  --border:#3A2F2E; --text:#F6EFEC; --muted:#A89996;
  --accent:#C1272D; --accent-hover:#A01F24;
  --radius:12px; --gap:18px; --pad:22px;
  --shadow:0 1px 3px rgba(0,0,0,.25);
}
html[data-theme="light"]{
  --bg:#F7F4F3; --surface:#FFFFFF; --surface2:#F0EBEA;
  --border:#E2D9D7; --text:#1B1514; --muted:#6B5E5C;
  --shadow:0 1px 3px rgba(0,0,0,.08);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:15px; line-height:1.5;
}
.topbar{
  display:flex; align-items:center; gap:12px;
  height:56px; padding:0 20px;
  background:var(--surface); border-bottom:1px solid var(--border);
}
.mark{
  display:grid; place-items:center; width:30px; height:30px;
  border-radius:8px; background:var(--accent); color:#fff;
  font-weight:600; font-size:15px;
}
.brand{font-size:17px; font-weight:600}
.wrap{max-width:880px; margin:0 auto; padding:24px}
.grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:var(--gap)}
.card{
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:var(--pad); box-shadow:var(--shadow);
  transition:background .15s ease, border-color .15s ease, transform .15s ease;
}
.card:hover{border-color:var(--accent)}
h1{font-size:28px; font-weight:600; line-height:1.2; margin:0 0 6px}
h2{font-size:19px; font-weight:600; line-height:1.2; margin:0 0 4px}
.sub{color:var(--muted); font-size:14px; margin:0 0 16px}
label{display:block; font-size:13px; color:var(--muted); margin:0 0 6px}
input,select,textarea{
  width:100%; background:var(--surface2); color:var(--text);
  border:1px solid var(--border); border-radius:8px;
  padding:10px 12px; font-size:15px; font-family:inherit;
  transition:border-color .15s ease, background .15s ease;
}
input:hover,select:hover{border-color:var(--muted)}
input:focus-visible,select:focus-visible,textarea:focus-visible,
button:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
.btn{
  border-radius:8px; padding:10px 16px; font-size:14px; font-weight:600;
  font-family:inherit; cursor:pointer; border:1px solid transparent;
  transition:background .15s ease, color .15s ease, transform .15s ease;
}
.btn.primary{background:var(--accent); color:#fff}
.btn.primary:hover{background:var(--accent-hover); transform:translateY(-1px)}
.btn.secondary{background:transparent; color:var(--text); border-color:var(--border)}
.btn.secondary:hover{background:var(--surface2)}
.switch{display:inline-flex; align-items:center; gap:8px; font-size:14px}
.switch input{
  appearance:none; -webkit-appearance:none; width:38px; height:22px;
  border-radius:999px; background:var(--surface2); position:relative;
  cursor:pointer; transition:background .15s ease;
}
.switch input::after{
  content:""; position:absolute; top:3px; left:3px; width:16px; height:16px;
  border-radius:50%; background:var(--muted); transition:transform .15s ease;
}
.switch input:checked{background:var(--accent)}
.switch input:checked::after{transform:translateX(16px); background:#fff}
.empty{padding:32px; text-align:center; color:var(--muted)}
.foot{padding:24px; text-align:center; font-size:13px; color:var(--muted)}
@media (max-width:720px){
  .wrap{padding:16px}
  .grid{grid-template-columns:1fr}
  h1{font-size:24px}
}
</style></head>
<body>
<header class="topbar"><span class="mark">P</span><span class="brand">Passit</span>
  <label class="switch" style="margin-left:auto"><input type="checkbox" id="dark">Dark</label>
</header>
<main class="wrap">
  <h1>Passit</h1><p class="sub">Offline password manager</p>
  <div class="grid">
    <section class="card"><h2>Passwords</h2>
      <p class="sub">Everything you save stays on this machine.</p>
      <div class="empty">No passwords yet. Use Add Password to store your first one.</div>
      <button class="btn primary" id="add">Add Password</button>
    </section>
    <section class="card"><h2>Settings</h2>
      <p class="sub">Take your data with you.</p>
      <button class="btn secondary" id="export">Export Data</button>
      <button class="btn secondary" id="import">Import Data</button>
    </section>
  </div>
</main>
<footer class="foot">Full edition</footer>
<script>
const K='app.v1';
const load=()=>{try{return JSON.parse(localStorage.getItem(K))||null}catch(e){return null}};
const save=v=>localStorage.setItem(K,JSON.stringify(v));
document.getElementById('add').addEventListener('click',function(){save(load()||[])});
document.getElementById('export').addEventListener('click',function(){});
document.getElementById('import').addEventListener('click',function(){});
document.getElementById('dark').addEventListener('change',function(e){
  document.documentElement.dataset.theme=e.target.checked?'light':'dark';
  localStorage.setItem('theme',e.target.checked?'light':'dark');
});
</script></body></html>"""


def main() -> int:
    print("THE APP THAT WAS ACTUALLY SOLD MUST FAIL\n")
    ugly = design_gate.lint(UGLY)
    for want in ("design token", "responsive", "focus state",
                 "grid or flex", "spacing scale", "characters of CSS"):
        check(f"rejects an app with no {want}",
              any(want in p for p in ugly), f"{len(ugly)} problem(s) total")

    print("\nA PAGE BUILT TO THE SPEC MUST PASS\n")
    good = design_gate.lint(GOOD)
    check("accepts a page built to APP_SPEC", not good,
          "; ".join(good[:3]))

    print("\nTHE GATE MUST NOT DEPEND ON A MODEL\n")
    check("check() with the review off still passes the good page",
          design_gate.check(GOOD, want_review=False) == [])
    check("check() with the review off still rejects the ugly page",
          bool(design_gate.check(UGLY, want_review=False)))
    try:
        got = design_gate.repair(UGLY, ["it looks cheap"], "sample")
        check("repair() without a provider returns empty instead of raising",
              got == "", repr(got)[:60])
    except SystemExit as e:  # a provider helper that exits rather than raises
        check("repair() without a provider returns empty instead of raising",
              False, f"it raised SystemExit: {e}")
    except Exception as e:  # noqa: BLE001
        check("repair() without a provider returns empty instead of raising",
              False, f"{type(e).__name__}: {e}")

    print("\nTHE CHECKS MUST AIM AT THE RIGHT THING\n")
    # The banner rule once matched any padding of 30px or more anywhere in the
    # file, so a comfortable card was reported as a title slab.
    padded = GOOD.replace("padding:var(--pad); ", "padding:40px; ")
    check("a card with 40px of padding is not called a banner",
          not any("banner" in p for p in design_gate.lint(padded)),
          "; ".join(p for p in design_gate.lint(padded) if "banner" in p))
    poster = GOOD.replace("font-size:28px", "font-size:72px")
    check("poster-sized text is rejected",
          any("poster-sized" in p for p in design_gate.lint(poster)))
    stock = GOOD.replace("appearance:none; -webkit-appearance:none; ", "")
    check("a browser-default checkbox is rejected",
          any("checkbox" in p for p in design_gate.lint(stock)))

    print()
    if fails:
        print(f"FAILURES: {len(fails)}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("FAILURES: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
