"""No app may unlock its paid features from the address bar.

Twenty-five of the free editions were generated with this:

    const PAID = new URLSearchParams(location.search).has('paid');
    const LIM = PAID ? {unlimited} : {basic limits};

The paid edition was then the same file with nothing else changed, so the only
thing standing between a visitor and the full product was a query parameter.
Adding ``?paid`` to the free app's own URL unlocked it. Every one of those
twenty-five apps is a paid product, and two of them - password-manager and
base64-tool - are on the store for $3, so this was live and free to anyone who
guessed.

The current generator bakes the edition into the file instead: ``TIER`` is
either "basic" or "full", set at build time, and ``rebuild_paid.py`` produces
the paid edition by flipping that one constant. There is no runtime switch, so
there is nothing for a URL to reach.

This checks the property directly, because it is a text property and text is
what shipped the bug:

1. no app gates anything on the query string,
2. the free editions are actually limited, not just labelled basic,
3. flipping TIER still produces the full edition, so the paid build is the
   full product and not the limited one.

    python tier_gate_selftest.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
APPS = ROOT / "site" / "apps"

import make_app

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


SOURCES = sorted(APPS.glob("*/app/index.html"))
# The standalone single-file copy the site actually links to for a free app is
# <app>/index.html, a copy of <app>/app/index.html made at generation time. It
# is the file served at the catalogue's URL, so it is the one a visitor can put
# ?paid on. It carries the same gate and has to be checked too - fixing only
# app/index.html left the live exploit in place.
OUTER = sorted(APPS.glob("*/index.html"))
ALL = SOURCES + OUTER
check("there are free editions to check", len(SOURCES) > 0,
      f"{len(SOURCES)} found under site/apps")
check("and the standalone copies are checked too", len(OUTER) == len(SOURCES),
      f"{len(OUTER)} outer index.html files against {len(SOURCES)} app ones")

# ------------------------------------------------- no query-string unlocking
# A URLSearchParams read on location.search that feeds a limit, a tier or a
# feature is the defect. A search param used for something genuinely cosmetic
# is not, so this only fires when the result reaches the access decision.
QLOCK = re.compile(
    r"(TIER|LIMITS?|PAID|tier|limits?)\s*=\s*[^;]*"
    r"URLSearchParams\s*\(\s*location\.search\s*\)",
)
unlockers = []
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if QLOCK.search(s):
        unlockers.append(name)
check("no app unlocks anything from the query string",
      not unlockers,
      f"{len(unlockers)} still do: {unlockers[:5]}")

# ----------------------------------------------- free editions are limited
# TIER="basic" has to come with a real limitation. An app labelled basic that
# reads all limits from the unlimited table is the free tier selling itself.
UNLIMITED = ('{maxItems:Infinity', "{maxItems: 0", 'max:Infinity',
             'max: Infinity')
LIMITED_MARK = ("BASIC_LIMITS", "maxItems:3", "maxItems: 3",
                "export:false", "export: false", "max:3", "max: 3",
                "false}/", "'one'", '"one"')
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if 'TIER="basic"' not in s and "TIER='basic'" not in s:
        check(f"{name} declares its edition", False,
              "no TIER constant, so the edition is unknown at runtime")
        continue
    if not any(m in s for m in LIMITED_MARK):
        check(f"{name} is genuinely limited", False,
              "no basic limit table found, so the free edition may be full")
        continue
    # flipping to full must change the access decision
    full = make_app._set_tier(s, "full")
    if 'TIER="full"' not in full and "TIER='full'" not in full:
        check(f"{name} flips to full", False,
              "set_tier did not produce a full edition")
        continue
    # ...and the full edition must differ from the basic one
    if full == s:
        check(f"{name} full edition differs", False,
              "flipping TIER changed nothing, so paid equals free")
        continue

# ------------------------------------------------ the script has to parse
# The chess-board app was served with one stray brace in its script, so the
# whole file failed to parse and the app did nothing at all: no board, no
# buttons, no error the visitor could see. It was live for as long as it was
# in the catalogue, and nothing caught it, because the validator that refuses
# a broken app could not read a template literal and reported eleven good
# apps as broken instead.
unparseable = []
for p in ALL:
    s = p.read_text(encoding="utf-8", errors="ignore")
    errs = make_app.js_syntax_errors(s)
    if errs:
        unparseable.append(f"{p.parent.parent.name} ({errs[0][:50]})")
check("every app's script parses", not unparseable,
      f"{len(unparseable)} do not: {unparseable[:4]}")

# ------------------------------------------------------- the gate is a gate
# A paid feature has to be reachable in the paid edition and refused in the
# free one. The mistakes here are quiet: an export control created only in the
# free edition, a limit key that LIM never defines, and a comparison that can
# never be true.
for p in SOURCES:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    for m in re.finditer(r"!\s*TIER\s*===\s*'full'", s):
        check(f"{name} has a working tier comparison", False,
              "'!TIER==='full' can never be true, so the check never fires")
        break
    m = re.search(r"const LIM=TIER==='full'\?\{([^}]*)\}", s)
    if m:
        defined = {k.split(":")[0].strip()
                   for k in m.group(1).split(",") if ":" in k}
        for k in sorted(set(re.findall(r"LIM\.([A-Za-z_]\w*)", s))):
            if k not in defined:
                check(f"{name} defines LIM.{k}", False,
                      f"LIM.{k} is used but LIM never defines it, so it is "
                      "always undefined and the control it hides is always "
                      "hidden")
                break
    # A feature gated on LIM.max is the mistake: max is the limit, not the
    # capability, so asking whether it is unlimited decides which edition gets
    # the feature, and it is the wrong way round. Using LIM.max to limit how
    # much is produced is correct, so only a block that creates or reveals a
    # control counts.
    for m in re.finditer(r"if\(LIM\.max\s*!==\s*Infinity\)\s*\{", s):
        depth, k = 0, m.end() - 1
        for k in range(m.end() - 1, len(s)):
            if s[k] == "{":
                depth += 1
            elif s[k] == "}":
                depth -= 1
                if depth == 0:
                    break
        block = s[m.end():k]
        if ("createElement('button'" in block or 'createElement("button"' in block
                or "createElement('input'" in block
                or 'createElement("input"' in block
                or "style.display" in block):
            check(f"{name} gates a feature on the right thing", False,
                  "a feature is gated on LIM.max, which is the limit and not "
                  "the capability, so it appears in the wrong edition")
            break

# ------------------------------------------------- what the paid edition has
# The shop asks for three dollars and has to say what the three dollars are
# for. The answer is in the app's own limit table, and it was never read:
# the paid edition was published with the same description as the free one
# and an empty differences list, so every product looked identical to the
# one next to it.
no_features = []
for p in SOURCES:
    s = p.read_text(encoding="utf-8", errors="ignore")
    name = p.parent.parent.name
    if not make_app.paid_features(s):
        no_features.append(name)
check("every product's paid edition has something the free one does not",
      not no_features,
      f"{len(no_features)} have none: {no_features[:5]}")

# The catalogue has to agree with the apps, or the shop describes a product
# that is not the one being sold.
import json as _json

try:
    _cat = _json.loads((ROOT / "site" / "apps.json").read_text(encoding="utf-8"))
except (OSError, ValueError) as _e:
    _cat = []
    check("the catalogue can be read", False, str(_e)[:60])
if _cat:
    _fams = {}
    for _e in _cat:
        _fams.setdefault(_e.get("base_slug") or _e.get("slug"), {})[
            _e.get("tier")] = _e
    _drift = []
    for _base, _pair in _fams.items():
        _full, _basic = _pair.get("full"), _pair.get("basic")
        if not _full or not _basic:
            _drift.append(f"{_base}: an edition is missing")
            continue
        _src = APPS / f"{_base}-basic" / "app" / "index.html"
        if not _src.exists():
            continue
        _real = make_app.paid_features(_src.read_text(encoding="utf-8"))
        if _full.get("differences") != _real:
            _drift.append(f"{_base}: says {_full.get('differences')} and the "
                          f"app has {_real}")
        if _full.get("blurb") == _basic.get("blurb"):
            _drift.append(f"{_base}: both editions say the same thing")
    check("the catalogue says what each paid edition really adds",
          not _drift,
          f"{len(_drift)} disagree: {_drift[:3]}")

print(f"\nchecked {len(SOURCES)} free editions for a paid-tier bypass")
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
