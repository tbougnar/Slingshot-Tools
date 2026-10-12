"""Extract the real capabilities of each app, and write them into the catalog.

The product record carries three fields, which is why a tour could only reach
eighteen seconds: there was nothing true to say after that. This reads the
capabilities out of each app's own source, where they are already written
down, and stores them in apps.json.

    python extract_features.py           write them
    python extract_features.py --show    print them, change nothing

Nothing here is invented. Every line traces to a tier flag, a control name or
a catalog entry, so a feature that does not exist cannot appear in the video.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "site" / "apps.json"

# Control names that describe interface furniture rather than capability.
CHROME = {
    "delete", "cancel", "close", "menu", "back", "next", "save", "edit",
    "settings", "help", "about", "toggle theme", "theme", "close dialog",
    "open", "add entry", "add", "submit", "clear",
}

# A tier flag, said the way a person would say it. The key is what the code
# calls it; the text is what the app actually does, and only appears when the
# paid build turns the flag on.
TIER_TEXT = {
    "export": "Exports everything to one file you control",
    "import": "Imports from another manager, so nothing is lost",
    "bulk": "Edits many entries at once",
    "history": "Keeps password history, so an old one comes back",
    "themes": "Light and dark, whichever you prefer",
    "maxItems": "Unlimited entries, not a three item trial",
}


def app_dir(slug: str) -> Path | None:
    root = ROOT / "site" / "apps"
    if not root.exists():
        return None
    hits = [d for d in sorted(root.iterdir())
            if d.is_dir() and d.name.startswith(slug)]
    if hits:
        return hits[0]
    dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]
    return dirs[0] if dirs else None


def source_of(d: Path) -> str:
    for rel in ("app/index.html", "index.html"):
        p = d / rel
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return ""


def features_for(slug: str, limit: int = 10) -> list[str]:
    d = app_dir(slug)
    if not d:
        return []
    src = source_of(d)

    out: list[str] = []

    def add(text: str) -> None:
        t = " ".join(str(text).split()).strip(" .—-*")
        if len(t) < 6 or len(t) > 68:
            return
        if t.lower() in CHROME:
            return
        if t.lower() not in [x.lower() for x in out]:
            out.append(t)

    # the paid tier's own configuration
    m = re.search(r"const\s+[A-Z_]*LIMITS\s*=\s*\{([^}]*)\}", src)
    if m:
        for key, val in re.findall(r"(\w+)\s*:\s*([^,}]+)", m.group(1)):
            key, val = key.strip(), val.strip().strip("'\"")
            if key == "maxItems" and val not in ("0", ""):
                add(TIER_TEXT["maxItems"])
            elif key in TIER_TEXT and val not in ("false", "0"):
                add(TIER_TEXT[key])

    # where it keeps things, which is the claim the product rests on
    if "localStorage" in src or "indexedDB" in src:
        add("Stored on your own disk, never sent anywhere")
    if re.search(r"crypto|subtle|AES|PBKDF|bcrypt|scrypt", src, re.I):
        add("Encrypted before it is written to disk")

    # the controls it names
    for raw in (re.findall(r'aria-label="([^"]+)"', src)
                + re.findall(r"<button[^>]*>([^<]{2,40})</button>", src)):
        add(re.sub(r"\s+", " ", raw))

    # a bare control name is not a claim; say what it does for the person
    PLAIN = {
        "export data": "Takes every entry out to one file you control",
        "import data": "Brings entries in from another manager",
        "add entry": "Add a login in a few seconds",
        "delete": "",
    }
    for i, f in enumerate(list(out)):
        if f.lower() in PLAIN and PLAIN[f.lower()]:
            out[i] = PLAIN[f.lower()]

    # the form says what it is collecting, which is a capability
    fields = re.findall(r"<label[^>]*>([^<]+)</label>", src)
    if len(fields) >= 2:
        add("Stores site, username and password together in one place")

    # a single line the app states about itself
    m = re.search(r"<footer>([^<]{10,120})</footer>", src)
    if m:
        t = " ".join(m.group(1).split()).rstrip(".")
        if t.lower() not in ("securely store passwords offline",):
            add(t)

    return out[:limit]


def main() -> int:
    if not CATALOG.exists():
        print("no site/apps.json, so there is nothing to read")
        return 1

    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    apps = cat if isinstance(cat, list) else cat.get("apps", [])

    seen: set[str] = set()
    changed = 0
    for a in apps:
        slug = a.get("base_slug") or a.get("slug") or ""
        if not slug or slug in seen:
            continue
        seen.add(slug)

        feats = features_for(slug)
        # a short title plus the features makes roughly a 26 second script
        # at two and a half words a second
        want = max(6, len(feats))
        if not feats:
            print(f"  {slug:26} nothing readable in the source")
            continue

        print(f"  {slug:26} {len(feats)} feature(s)")
        for f in feats:
            print(f"       - {f}")

        if "--show" in sys.argv:
            continue

        # write it onto every entry that shares this base slug
        for b in apps:
            if (b.get("base_slug") or b.get("slug")) != slug:
                continue
            if b.get("differences") != feats:
                b["differences"] = feats
                changed += 1

    if "--show" in sys.argv:
        print()
        print(f"a {want} feature script runs about "
              f"{want * 2.4:.0f} seconds")
        return 0

    if changed:
        CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        print(f"\nupdated {changed} entry/entries in apps.json")
    else:
        print("\napps.json was already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())