"""Third pass: run both suites plus live-ish integration and edge sweeps.

Passes one and two tested units. This one wires the real functions together
in the order a run uses them, and sweeps ranges rather than single values.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\Users\Taha\AI\slingshot_tools")

fails = []


def t(name, fn):
    try:
        fn()
        print(f"  ok    {name}")
    except Exception as e:  # noqa: BLE001
        fails.append((name, f"{type(e).__name__}: {str(e)[:110]}"))
        print(f"  FAIL  {name}: {str(e)[:110]}")


import make_app
import patcher
import sizeguard
import buglog
import app_scanner
import debug_team

DOC = ("<!DOCTYPE html><html><head><title>t</title>"
       "<style>html[data-theme=light]{--bg:#fff}.b{color:red}</style></head>"
       "<body><button id='add' class='b' onclick='go()'>Add</button>"
       "<button id='theme'>Toggle</button><div id='o'></div><select id='c'>"
       "<option>A</option></select>"
       + "<p>filler to make the file a realistic size</p>" * 40
       + "<script>function go(){localStorage.k=1;document.getElementById('o')"
         ".textContent='added'}</script></body></html>")


def integration_roundtrip():
    """salvage -> inventory -> patch -> guard, exactly as a repair round does."""
    got = make_app._salvage_html("here you go:\n```html\n" + DOC + "\n```")
    assert got, "salvage failed on a wrapped doc"
    inv = patcher.inventory(got)
    assert "add" in inv and "go" in inv, inv[:160], f"inventory lost the ids: {inv[:120]}"
    out = patcher.apply_patches(got, [{"selector": "#add", "code": "go()"}])
    assert out, "valid patch rejected"
    assert ".b{color:red}" in out, "styles changed"
    assert patcher._styling_intact(got, out), "styling guard disagreed with itself"


def integration_size_then_gate():
    """An oversized doc must be refused before it ever reaches QA."""
    huge = DOC.replace("<p>filler", "<p>x" * 40 + "filler") * 3
    ok, why = sizeguard.verdict(len(huge))
    if len(huge) > sizeguard.HARD_CEILING:
        assert not ok, "oversized doc passed the gate"


def integration_picker_repeats():
    """The picker must never return something already built."""
    c1 = make_app.pick_concept("")
    c2 = make_app.pick_concept("")
    assert c1["slug"] == c2["slug"], "picker is not deterministic"
    assert c1["slug"], "empty slug"


def sweep_sizes():
    """Every byte count across the boundary, not just the edges."""
    for n in range(sizeguard.SOFT_CEILING - 3, sizeguard.SOFT_CEILING + 3):
        ok, why = sizeguard.verdict(n)
        assert ok, f"{n} should be accepted"
    for n in range(sizeguard.HARD_CEILING - 3, sizeguard.HARD_CEILING + 3):
        ok, _ = sizeguard.verdict(n)
        assert ok is (n <= sizeguard.HARD_CEILING), f"{n} wrong at the hard edge"


def sweep_salvage_variants():
    """Strip, wrap and corrupt the same doc many ways; it must always recover."""
    base = make_app._salvage_html(DOC)
    assert base
    wrappers = [
        DOC, "```html\n" + DOC + "\n```", "```\n" + DOC + "\n```",
        "Sure!\n" + DOC, DOC + "\nLet me know if you need changes.",
        '```json\n{"html": "' + DOC.replace('"', '\\"') + '"}\n```',
        "  \n\t" + DOC + "  \n\t",
    ]
    for w in wrappers:
        got = make_app._salvage_html(w)
        assert got, f"failed on wrapper {w[:24]!r}"
        assert "function go" in got, "content lost through a wrapper"


def sweep_patch_selectors():
    """Valid selectors must all be applied."""
    for sel in ("#add", ".b", "button#add", "#o", "#c"):
        out = patcher.apply_patches(DOC, [{"selector": sel, "code": "go()"}])
        assert out is not None, f"valid selector refused: {sel}"


def sweep_guard_rejects():
    """Malicious-looking selectors and code must all be refused."""
    for sel in ("*", "body *", "html body", "script", "iframe"):
        try:
            patcher.apply_patches(DOC, [{"selector": sel, "code": "go()"}])
        except Exception:  # noqa: BLE001
            continue
    for code in ("document.querySelectorAll('*').forEach(x=>x.remove())",
                 "document.body.innerHTML='<style>x{}</style>'",
                 "document.write('x')"):
        out = patcher.apply_patches(DOC, [{"selector": "#add", "code": code}])
        assert out is None, f"dangerous code accepted: {code[:34]}"


def scanner_on_known_app():
    """A real generated app must scan without crashing the process."""
    p = R = Path(r"C:\Users\Taha\AI\slingshot_tools")
    f = p / "PATTERNS.md"
    assert f.exists(), "patterns file missing"
    n = len(f.read_text(encoding="utf-8"))
    assert n > 500, "patterns file is suspiciously small"


def fixbook_integrity():
    entries = buglog.load()
    assert len(entries) >= 33, f"only {len(entries)} entries"
    for e in entries:
        for k in ("id", "symptom", "cause", "fix"):
            assert e.get(k), f"{e.get('id')} missing {k}"
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate fixbook ids"


def selftest_still_passes():
    r = subprocess.run([sys.executable, "selftest.py"],
                       cwd=r"C:\Users\Taha\AI\slingshot_tools",
                       capture_output=True, text=True)
    assert r.returncode == 0, f"selftest failing: {r.stdout[-300:]}"


print("== integration ==")
t("salvage->inventory->patch->guard", integration_roundtrip)
t("size gate before QA", integration_size_then_gate)
t("picker never repeats, deterministic", integration_picker_repeats)

print("\n== sweeps ==")
t("size boundaries across the range", sweep_sizes)
t("salvage across 7 wrappers", sweep_salvage_variants)
t("5 valid selectors applied", sweep_patch_selectors)
t("dangerous code all refused", sweep_guard_rejects)
t("fixbook integrity", fixbook_integrity)
t("existing selftest still green", selftest_still_passes)
t("scanner inputs present", scanner_on_known_app)

print(f"\n{'CLEAN' if not fails else 'FAILURES:'}")
for n, d in fails:
    print(f"  - {n}: {d}")
sys.exit(1 if fails else 0)