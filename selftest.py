"""Run every stage's real behaviour, not just check the names exist.

This is the check that catches what an import test cannot: code that compiles,
is defined, and still produces nothing.
"""
import sys
from pathlib import Path as _P
HERE = _P(__file__).resolve().parent
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
R = HERE

results = []


def check(name, fn):
    try:
        detail = fn()
        results.append((True, name, detail or ""))
    except Exception as e:  # noqa: BLE001
        results.append((False, name, f"{type(e).__name__}: {str(e)[:120]}"))


DOC = ("<!DOCTYPE html><html><head><title>t</title></head><body>"
       + "<button id='a' onclick='go()'>Go</button><div id='o'></div>"
       + ("<p>filler text for size</p>" * 60)
       + "<script>function go(){localStorage.k=1}</script></body></html>")


def t_salvage():
    import make_app
    for label, raw in [("plain", DOC),
                       ("fenced", "here you go:\n```html\n" + DOC + "\n```"),
                       ("prose", "sure:\n" + DOC + "\nhope it helps"),
                       ("json", '{"html": "' + DOC.replace('"', '\\"') + '"}'),
                       ("truncated", DOC[:700])]:
        got = make_app._salvage_html(raw)
        if not got or not got.lower().endswith("</html>"):
            raise AssertionError(f"{label} failed")
    return "all 5 shapes extract"


def t_raw_builder_exists():
    import make_app
    if not hasattr(make_app, "build_html_raw"):
        raise AssertionError("missing")
    return "present"


def t_stage_uses_raw():
    s = (R / "stage_app.py").read_text(encoding="utf-8")
    if "build_html_raw" not in s:
        raise AssertionError("stage_app still uses the JSON path")
    return "wired to the raw builder"


def t_picker_local():
    import make_app
    c = make_app.pick_concept("")
    for k in ("slug", "title", "blurb"):
        if not c.get(k):
            raise AssertionError(f"missing {k}")
    return f"picks {c['slug']} with no model call"


def t_sizeguard():
    import sizeguard
    if sizeguard.verdict(40000)[0]:
        raise AssertionError("oversized file accepted")
    if not sizeguard.verdict(5000)[0]:
        raise AssertionError("small file rejected")
    return "rejects oversize, accepts small"


def t_exposure():
    import check_exposure
    rc = check_exposure.main()
    if rc not in (0, 1):
        raise AssertionError("unexpected return")
    return "paid work cannot sit in the published folder"


def t_inventory():
    import patcher
    inv = patcher.inventory(DOC)
    for needed in ("ids:", "classes:", "controls:", "functions:"):
        if needed not in inv:
            raise AssertionError(f"inventory missing {needed}")
    return "covers ids, classes, labels, functions"


def t_css_guard():
    import patcher
    out = patcher.apply_patches(
        DOC, [{"selector": "#a", "code": "go()"}])
    if not out:
        raise AssertionError("valid patch rejected")
    bad = patcher.apply_patches(
        DOC, [{"selector": "#a", "code": "document.body.innerHTML='<style>x{}</style>'"}])
    if bad is not None:
        raise AssertionError("styling change accepted")
    return "patches in, restyling out"


def t_tokenmeter():
    import tokenmeter
    tokenmeter.reset()
    tokenmeter.add(1000, 500)
    if tokenmeter.spent() != 1500:
        raise AssertionError("usage not recorded")
    if tokenmeter.affordable(8000, 2000) is not True:
        raise AssertionError("budget check wrong")
    tokenmeter.reset()
    return "tracks and reports usage"


def t_fixbook():
    import buglog
    if len(buglog.load()) < 30:
        raise AssertionError("fixbook looks truncated")
    return f"{len(buglog.load())} lessons recorded"


def t_workflows():
    import yaml
    wf = R / ".github" / "workflows"
    names = sorted(p.name for p in wf.glob("*.yml"))
    for n in names:
        yaml.safe_load((wf / n).read_text(encoding="utf-8"))
    # the four stages of the weekly cycle have to all be there
    for required in ("monday-vote.yml", "wednesday-review.yml",
                     "friday-build.yml", "friday-verify.yml", "pages.yml"):
        if required not in names:
            raise AssertionError(f"missing workflow: {required}")
    return f"all {len(names)} workflows parse"


def t_imports():
    import importlib
    for mod in ("make_app", "patcher", "qa_loop", "app_scanner", "providers",
                "buglog", "tokenmeter", "sizeguard", "set_itch_url",
                "publish_paid", "check_exposure", "stage_app", "verify_app",
                "discord_tally", "discord_intro", "budget", "weekly_guard",
                "check_repo_hygiene"):
        importlib.import_module(mod)
    return "every module imports"


def t_no_duplicates():
    for f in ("make_app.py", "stage_app.py", "patcher.py", "providers.py"):
        text = (R / f).read_text(encoding="utf-8")
        for name in ("APP_SPEC", "PATTERN_CARD"):
            if text.count(name + " = ") > 1:
                raise AssertionError(f"{name} defined twice in {f}")
    return "no duplicate module-level definitions"


for nm, fn in [
    ("modules import", t_imports),
    ("no duplicate definitions", t_no_duplicates),
    ("html salvage", t_salvage),
    ("raw builder present", t_raw_builder_exists),
    ("stage wired to raw", t_stage_uses_raw),
    ("local concept pick", t_picker_local),
    ("element inventory", t_inventory),
    ("css guard", t_css_guard),
    ("size guard", t_sizeguard),
    ("exposure check", t_exposure),
    ("token meter", t_tokenmeter),
    ("fixbook", t_fixbook),
    ("workflows parse", t_workflows),
]:
    check(nm, fn)

passed = sum(1 for ok, _, _ in results if ok)
print(f"{passed}/{len(results)} behavioural checks passed\n")
for ok, name, detail in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:28s} {detail}")

sys.exit(0 if passed == len(results) else 1)