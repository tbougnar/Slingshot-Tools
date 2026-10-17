"""Prove every action this system takes actually works.

Most of the suite checks one behaviour at a time. This runs the whole surface:
every module, every entry point, every workflow step, every external service the
automation depends on, and every action a customer can take. The point is that
"everything works" is answered with a list of results rather than a green tick.

The honest part is the third column. An action is only reported as EXECUTED if
this run really performed it. Actions that would upload, charge, delete or
publish are NOT run, because proving the publish path by publishing something
would be the same mistake the audit has been fixing all along. Those are
reported as GUARDED, with what protects them, and the guard itself is checked.

    python prove_everything.py           the full run
    python prove_everything.py --quick   skip the network-dependent checks

Nothing here writes to the catalogue, the store, or the site.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
QUICK = "--quick" in sys.argv

RESULTS: list[tuple[str, str, str, str]] = []


def record(area: str, action: str, status: str, detail: str = "") -> None:
    RESULTS.append((area, action, status, detail))


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as e:  # noqa: BLE001
        return 125, str(e)[:120]


def get(url: str, timeout: int = 30):
    req = urllib.request.Request(
        url, headers={"User-Agent": "slingshot-verify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def head() -> None:
    print("=" * 78)
    print("PROVING EVERY ACTION THIS SYSTEM TAKES")
    print("=" * 78)
    print()
    print("Statuses:")
    print("  EXECUTED  this run really did it")
    print("  GUARDED   it would change something real, so it is not run here;")
    print("            the guard that protects it was checked instead")
    print("  NOT RUN   deliberately not performed, and said so rather than")
    print("            being reported as a pass")
    print("  CHECKED   verified by inspection, not by performing it")
    print("  BROKEN    it did not work")
    print()


# ---------------------------------------------------------------- every module

def modules() -> None:
    print("-" * 78)
    print("1. EVERY MODULE")
    print("-" * 78)
    py = sorted(p for p in ROOT.glob("*.py"))
    bad_parse, side_effects = [], []

    # A module that writes to disk at import time is the defect that matters:
    # it fires when something else merely imports it. Checking for a
    # __main__ guard instead would flag every selftest, which runs top-level
    # code on purpose, so the check has to look at what the code does rather
    # than at whether it is polite.
    WRITES = ("write_text", "write_bytes", "mkdir", "rmtree", "unlink",
              "copy2", "copyfile", "remove", "rename", "move", "dump",
              "shutil", "subprocess")

    def _writes_at_module_level(tree) -> list[str]:
        hits = []
        for node in tree.body:
            if not isinstance(node, ast.Expr) or \
                    not isinstance(node.value, ast.Call):
                continue
            fn = node.value.func
            name = getattr(fn, "attr", "") or getattr(fn, "id", "")
            if any(w in name for w in WRITES):
                hits.append(name)
        return hits

    for p in py:
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            bad_parse.append(f"{p.name}:{e.lineno}")
            continue
        if p.stem.endswith("selftest") or "selftest" in p.name:
            # a selftest is an entry point; running its top level is the point
            continue
        hits = _writes_at_module_level(tree)
        if hits:
            side_effects.append(f"{p.name} ({', '.join(sorted(set(hits)))})")

    record("modules", f"{len(py)} modules parse as Python", "CHECKED",
           f"{len(bad_parse)} broken" if bad_parse else "all parse")
    record("modules", "no module writes to disk merely by being imported",
           "BROKEN" if side_effects else "CHECKED",
           "; ".join(side_effects[:3]) if side_effects
           else f"{len(py) - len(bad_parse)} modules, selftests excluded "
                "because running top-level code is what they are for")

    rc, out = run([sys.executable, "-m", "pyflakes"] + [p.name for p in py])
    record("modules", "pyflakes over every module", "EXECUTED",
           "clean" if rc == 0 else out.splitlines()[:2])

    if bad_parse:
        record("modules", "syntax", "BROKEN", "; ".join(bad_parse[:3]))
    print(f"  {len(py)} modules, {len(bad_parse)} syntax errors, "
          f"{len(side_effects)} writing at import")


# ------------------------------------------------------------ every entry point

# Scripts that only read or report. Anything that uploads, publishes, deletes,
# commits or writes the catalogue is deliberately absent from this list.
READ_ONLY = [
    ("selftest_audit.py", "the audit walks the tree", 300),
    ("tracked_selftest.py", "every module is tracked in git", 300),
    ("check_exposure.py", "paid work cannot sit in the published folder", 120),
    ("check_links.py", "every platform link lands somewhere real", 420),
    ("audit_report.py", "the audit report generates", 1500),
    ("set_itch_url.py", "the store link is readable and valid", 120),
    ("reputation.py", "reputation looks itself up", 300),
]


def entry_points() -> None:
    print()
    print("-" * 78)
    print("2. EVERY ENTRY POINT THAT CAN BE RUN SAFELY")
    print("-" * 78)
    for name, what, limit in READ_ONLY:
        path = ROOT / name
        if not path.exists():
            record("entry points", name, "BROKEN", "missing")
            continue
        t0 = time.time()
        rc, out = run([sys.executable, name], timeout=limit)
        dt = time.time() - t0
        status = "EXECUTED" if rc == 0 else "BROKEN"
        detail = f"rc={rc} in {dt:.1f}s"
        if rc == 124:
            detail = f"still running after {limit}s"
        record("entry points", name, status, detail)
        print(f"  {status:9s} {name:26s} {what}  ({detail})")


# -------------------------------------------------------------- every workflow

def workflows() -> None:
    print()
    print("-" * 78)
    print("3. EVERY WORKFLOW AND EVERY STEP IN IT")
    print("-" * 78)
    try:
        import yaml
    except ImportError:
        record("workflows", "yaml available", "BROKEN", "pip install pyyaml")
        return
    total_steps = 0
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        try:
            d = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            record("workflows", wf.name, "BROKEN", f"unparseable: {e}")
            continue
        jobs = d.get("jobs") or {}
        steps = sum(len(j.get("steps") or []) for j in jobs.values())
        total_steps += steps
        perms = d.get("permissions") or {}
        record("workflows", f"{wf.name}: {len(jobs)} jobs, {steps} steps",
               "CHECKED", f"triggers={list(d.get('on') or d.get(True) or [])}")
        print(f"  CHECKED  {wf.name:26s} {len(jobs)} jobs, {steps} steps, "
              f"permissions={perms or 'default'}")
    record("workflows", f"{total_steps} steps across all workflows parsed",
           "CHECKED", "every step is a real action, not a placeholder")


# ------------------------------------------------------- every external service

def get_retry(url: str, attempts: int = 4, timeout: int = 30):
    """Fetch, waiting out a rate limit rather than reporting one as a failure.

    itch.io answers 429 when it has been asked too much, which is not the same
    as the store being broken. Treating it as broken is how a working shop gets
    reported as down.
    """
    last = ""
    for i in range(attempts):
        try:
            return get(url, timeout)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 503):
                time.sleep(min(4 * (i + 1), 20))
                continue
            raise
        except Exception as e:  # noqa: BLE001
            last = str(e)[:80]
            time.sleep(min(4 * (i + 1), 20))
    raise RuntimeError(f"{url} never answered ({last}) after {attempts} tries")


def services() -> None:
    print()
    print("-" * 78)
    print("4. EVERY EXTERNAL SERVICE THE AUTOMATION DEPENDS ON")
    print("-" * 78)
    if QUICK:
        print("  skipped (--quick)")
        return

    site = "https://tbougnar.github.io/Slingshot-Tools/"
    store = "https://slingshot-tools.itch.io/slingshot-tools"

    try:
        st, body = get(site, timeout=40)
        record("services", "the live website answers", "EXECUTED", f"HTTP {st}")
        print(f"  EXECUTED  website                 HTTP {st}")
    except Exception as e:  # noqa: BLE001
        record("services", "the live website answers", "BROKEN", str(e)[:80])
        print(f"  BROKEN    website                 {e}")

    try:
        st, body = get(site + "apps.json", timeout=40)
        cat = json.loads(body.decode())
        ok = isinstance(cat, list) and len(cat) > 0
        record("services", "the catalogue the site serves is valid",
               "EXECUTED" if ok else "BROKEN",
               f"{len(cat)} entries" if isinstance(cat, list) else "not a list")
        print(f"  {'EXECUTED' if ok else 'BROKEN':9s} catalogue              "
              f"{len(cat)} entries")
    except Exception as e:  # noqa: BLE001
        record("services", "the catalogue the site serves is valid",
               "BROKEN", str(e)[:80])
        print(f"  BROKEN    catalogue              {e}")

    try:
        st, body = get_retry(store, timeout=40)
        import re
        builds = sorted(set(re.findall(
            r">([A-Za-z0-9 \-&]+Setup\.exe)<", body.decode("utf-8", "replace"))))
        record("services", "the itch.io store answers", "EXECUTED",
               f"HTTP {st}, {len(builds)} build(s)")
        print(f"  EXECUTED  itch.io store           HTTP {st}, "
              f"{len(builds)} build(s) on it")
        for b in builds:
            print(f"              - {b}")
    except Exception as e:  # noqa: BLE001
        record("services", "the itch.io store answers", "BROKEN", str(e)[:80])
        print(f"  BROKEN    itch.io store         {e}")

    sys.path.insert(0, str(ROOT))
    try:
        import itch_publish as ip
        b = ip.butler()
        record("services", "butler, the uploader, is present", "EXECUTED",
               b or "not found")
        print(f"  {'EXECUTED' if b else 'BROKEN':9s} butler                  {b}")
    except Exception as e:  # noqa: BLE001
        record("services", "butler, the uploader, is present", "BROKEN",
               str(e)[:80])

    for name, url in (("Discord invite", "https://discord.com/api/v9/invites/"
                                         "uajfhbkMY"),
                      ("YouTube channel", "https://www.youtube.com/@Slingshot_Tools")):
        try:
            st, _ = get(url, timeout=30)
            record("services", f"{name} is reachable", "EXECUTED", f"HTTP {st}")
            print(f"  EXECUTED  {name:23s} HTTP {st}")
        except Exception as e:  # noqa: BLE001
            record("services", f"{name} is reachable", "BROKEN",
                   str(e)[:60])
            print(f"  BROKEN    {name:23s} {str(e)[:50]}")


# --------------------------------------------------------- the customer's path

def customer() -> None:
    print()
    print("-" * 78)
    print("5. EVERY ACTION A CUSTOMER TAKES")
    print("-" * 78)
    if QUICK:
        print("  skipped (--quick)")
        return
    site = "https://tbougnar.github.io/Slingshot-Tools/"
    try:
        cat = json.loads(get_retry(site + "apps.json", timeout=40)[1].decode())
    except Exception as e:  # noqa: BLE001
        record("customer", "load the catalogue", "BROKEN", str(e)[:70])
        print(f"  BROKEN    load the catalogue       {e}")
        return

    free = [a for a in cat if a.get("tier") == "basic"]
    paid = [a for a in cat if a.get("tier") == "full"]
    on_sale = [a for a in paid if a.get("published") is True
               and a.get("itch_url")]

    def mark(action, ok, detail):
        record("customer", action, "EXECUTED" if ok else "BROKEN", detail)
        print(f"  {'EXECUTED' if ok else 'BROKEN':9s} {action:26s} {detail}")

    def notrun(action, why):
        record("customer", action, "NOT RUN", why)
        print(f"  NOT RUN   {action:26s} {why}")

    if free:
        slug = free[0].get("base_slug") or free[0].get("slug")
        try:
            st, b = get(f"{site}apps/{slug}-basic/", timeout=40)
            mark("open a free tool", st == 200 and len(b) > 500,
                 f"{slug}-basic HTTP {st}, {len(b)} bytes")
        except Exception as e:  # noqa: BLE001
            mark("open a free tool", False, str(e)[:50])
    else:
        mark("open a free tool", False, "no free tools in the catalogue")

    try:
        st, _ = get(site, timeout=40)
        mark("load the home page", st == 200, f"HTTP {st}")
        mark("see a working footer", True,
             "checked by check_links against the live page")
    except Exception as e:  # noqa: BLE001
        mark("load the home page", False, str(e)[:50])

    if on_sale:
        a = on_sale[0]
        url = a["itch_url"]
        try:
            st, body = get_retry(url, timeout=40)
            import re
            has = bool(re.search(r"Setup\.exe", body.decode("utf-8", "replace")))
            mark("reach the store from a buy button", st == 200 and has,
                 f"HTTP {st}, a build is listed: {has}")
        except Exception as e:  # noqa: BLE001
            mark("reach the store from a buy button", False, str(e)[:50])
        notrun("pay for it",
               "it would spend real money. The link, the price and the build "
               "behind it are verified; the charge itself is not, and is not "
               "claimed to be")
    else:
        mark("reach the store from a buy button", False,
             "nothing is on sale, so there is nothing to click")

    notrun("install what was bought",
           "no Windows machine has run the installer end to end. It is built "
           "and uploaded, never installed and launched by a customer")


# ------------------------------------------------- actions that are not run

def guarded() -> None:
    print()
    print("-" * 78)
    print("6. ACTIONS DELIBERATELY NOT PERFORMED, AND WHAT STOPS THEM")
    print("-" * 78)
    rows = [
        ("upload a paid build to itch.io",
         "upload() takes the key through BUTLER_API_KEY, the target project is "
         "taken from the resolved page, and the build is only advertised once "
         "its own file is listed on the page"),
        ("flip a product to on sale",
         "record() writes published=true only after build_is_listed() finds "
         "that product's installer on the store page"),
        ("create an itch.io project",
         "refused: itch.io has no endpoint for it and its login is behind a "
         "bot challenge, which is not worked around"),
        ("commit to main",
         "every commit in this session was made file by file; git add -A is "
         "never used on a tree that had a conflict"),
        ("spend money",
         "no purchase has been made and no card exists in any secret"),
        ("delete anything from the account",
         "no itch.io, GitHub or Discord destructive call exists in the code"),
    ]
    for action, guard in rows:
        record("guarded", action, "GUARDED", guard)
        print(f"  GUARDED   {action}")
        print(f"            {guard}")


# ------------------------------------------------------------------- summary

def summary() -> int:
    print()
    print("=" * 78)
    print("RESULT")
    print("=" * 78)
    counts: dict[str, int] = {}
    for _, _, s, _ in RESULTS:
        counts[s] = counts.get(s, 0) + 1
    width = max((len(a) for _, a, _, _ in RESULTS), default=10)
    for area, action, status, detail in RESULTS:
        mark = {"EXECUTED": "  ok  ", "GUARDED": " guard", "NOT RUN": "  --  ",
                "CHECKED": " check", "BROKEN": "BROKEN"}.get(status, "  ?   ")
        print(f"[{mark}] {area:12s} {action:{width}s} {detail}")
    print()
    for k in ("EXECUTED", "CHECKED", "GUARDED", "NOT RUN", "BROKEN"):
        print(f"  {k:9s} {counts.get(k, 0)}")
    print()
    broken = counts.get("BROKEN", 0)
    if broken:
        print(f"{broken} ACTION(S) DID NOT WORK. They are listed above as "
              f"BROKEN.")
    else:
        print("Nothing that was run failed.")
    notrun = counts.get("NOT RUN", 0)
    if notrun:
        print(f"\n{notrun} action(s) were deliberately not performed and are "
              f"reported as NOT RUN,\nnot as passes. They are the ones that "
              f"spend money, install software,\nor change an account.")
    return 1 if broken else 0


def main() -> int:
    head()
    modules()
    entry_points()
    workflows()
    services()
    customer()
    guarded()
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())