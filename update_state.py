"""What version every app is on, and when the next big one is due.

Three separate things were being tracked in three separate places, which is why
none of them agreed:

- the installer hardcoded ``DisplayVersion "1.0.0"``, so a customer's app and
  the catalog could both claim a version that did not match reality
- the catalog had no version at all, so the site could not tell a customer
  their copy was behind
- nothing anywhere knew the next major release was coming, so a countdown
  would have had to be invented from scratch each time

This module is the single place that answers all three. Everything else reads
it and writes nothing of its own:

    python update_state.py             show the state
    python update_state.py --bump patch    raise every version by one step
    python update_state.py --set 2.0.0     force a version, for a real release

Semver, deliberately: MAJOR.MINOR.PATCH. A major bump is what the monthly
trailer and the Discord event are about; a patch bump is the weekly lane. The
distinction is the whole point, so it is stored rather than guessed later.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "update_state.json"
# The site reads this one. It is data, not markup, so regenerating it is not
# the same act as editing the published HTML.
PUBLIC = ROOT / "site" / "update.json"
CATALOG = ROOT / "site" / "apps.json"

# A major release is announced a week ahead, so the countdown and the Discord
# event have to exist before the day itself.
ANNOUNCE_LEAD_DAYS = 7
# How far ahead a countdown is allowed to be visible. Further out than this and
# it is a plan, not an event, and a plan does not belong in a banner.
COUNTDOWN_WINDOW_DAYS = 21

LEVELS = ("major", "minor", "patch")


def log(m: str) -> None:
    print(f"[update] {m}", flush=True)


def parse(version: str) -> tuple[int, int, int]:
    """A version as three integers, tolerating the usual junk around it.

    A version with fewer than three parts is padded with zeros. It used to
    return (1, 0, 0) for anything shorter, so `update_state.py --set 2.0`
    stored version 1.0.0, logged "version 1.0.0" and exited 0: the release
    state moved backwards and the run reported success. A version with no
    digits in it at all is still 1.0.0, which is the "unknown" the callers
    rely on.
    """
    nums = re.findall(r"\d+", str(version or ""))
    if not nums:
        return (1, 0, 0)
    parts = [int(n) for n in nums[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def format_version(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"


def bump(version: str, level: str) -> str:
    """The next version at this level.

    A patch bump that would land on 1.0.0 becomes 1.0.1, and a major bump
    always clears the minor and patch. Rolling 1.9.9 forward by a patch gives
    1.9.10, not 1.9.0, which is the bug a naive ``+ 1`` on the last number
    produces.
    """
    major, minor, patch = parse(version)
    level = (level or "patch").strip().lower()
    if level == "major":
        return format_version((major + 1, 0, 0))
    if level == "minor":
        return format_version((major, minor + 1, 0))
    return format_version((major, minor, patch + 1))


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a strictly higher version than ``current``.

    Compared as numbers rather than as strings, because "1.10.0" is newer than
    "1.9.0" and a string comparison says the opposite.
    """
    return parse(candidate) > parse(current)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _empty() -> dict:
    return {
        "version": "1.0.0",
        "updated": date.today().isoformat(),
        "next_major": None,
        "next_major_title": None,
        "next_major_notes": [],
        "discord_event_id": None,
        "last_trailer": None,
        "last_update_title": None,
        "last_update_description": "",
        "last_update_notes": [],
        "last_update_at": None,
        "apps": {},
    }


def load() -> dict:
    """The state, or a fresh one. Never raises on a bad file."""
    if not STATE.exists():
        return _empty()
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log("the state file is unreadable, starting from 1.0.0")
        return _empty()
    base = _empty()
    if isinstance(d, dict):
        base.update(d)
    # a state file written before a key existed must not make the rest fail.
    # apps is a dict of slug -> version/metadata and next_major_notes is a list.
    for key, want in (("apps", dict), ("next_major_notes", list),
                      ("last_update_notes", list)):
        if not isinstance(base.get(key), want):
            base[key] = want()
    return base


def save(state: dict) -> bool:
    """Write the state, and say plainly when it could not be written.

    This runs unattended, and a read-only file or a full disk raised an
    unhandled PermissionError/OSError straight through main(), so the job died
    on a traceback. It also used to log "saved" before checking anything, which
    is the worse half: a caller could not tell a real save from a claim of one.
    """
    state["updated"] = date.today().isoformat()
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as e:
        log(f"could not write {STATE.name}: {e}")
        log("the release state was NOT updated, so nothing that depends on it "
            "can be trusted this run")
        return False
    log(f"saved {state.get('version')} to {STATE.relative_to(ROOT)}")
    return True


def app_entry(state: dict, slug: str) -> dict:
    """Per-app update metadata, normalized to a dict."""
    got = (state.get("apps") or {}).get(str(slug))
    if isinstance(got, dict):
        out = dict(got)
    elif got:
        out = {"version": str(got)}
    else:
        out = {}
    if not out.get("version"):
        out["version"] = str(state.get("version") or "1.0.0")
    out["version"] = format_version(parse(out["version"]))
    return out


def app_version(state: dict, slug: str) -> str:
    """One app's version, falling back to the company-wide version."""
    return app_entry(state, slug)["version"]


def set_app_version(state: dict, slug: str, version: str) -> None:
    apps = state.setdefault("apps", {})
    cur = apps.get(str(slug))
    if isinstance(cur, dict):
        cur["version"] = format_version(parse(version))
        apps[str(slug)] = cur
    else:
        apps[str(slug)] = format_version(parse(version))


def set_app_update(state: dict, slug: str, *, version: str | None = None,
                   title: str | None = None, description: str | None = None,
                   notes: list | None = None, download_url: str | None = None,
                   restart_required: bool = True) -> dict:
    """Record a same-day update for one app."""
    apps = state.setdefault("apps", {})
    cur = apps.get(str(slug))
    entry = dict(cur) if isinstance(cur, dict) else ({"version": str(cur)} if cur else {})
    if version is not None:
        entry["version"] = format_version(parse(version))
    elif not entry.get("version"):
        entry["version"] = str(state.get("version") or "1.0.0")
    if title is not None:
        entry["title"] = str(title)
    if description is not None:
        entry["description"] = str(description)
    if notes is not None:
        entry["notes"] = [str(n) for n in notes if str(n).strip()][:12]
    if download_url is not None:
        entry["download_url"] = str(download_url)
    entry["restart_required"] = bool(restart_required)
    entry["released"] = date.today().isoformat()
    apps[str(slug)] = entry
    return entry


def next_major_date(state: dict) -> date | None:
    raw = state.get("next_major")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        return None


def days_until(state: dict, when: date | None = None) -> int | None:
    # Date arithmetic here uses the local calendar day, the same one
    # _empty() stamps into "updated" and the same one every other function in
    # this module reads. It used to use now().date(), which is UTC, so for one
    # hour a night in any positive-offset timezone the countdown was a day out
    # and phase() disagreed with the banner: on the release day itself phase
    # returned "announced" instead of "live", because the target was seen as one
    # day away. property_selftest.py caught it and could not pass on a clean
    # checkout for that hour.
    target = when or next_major_date(state)
    if target is None:
        return None
    return (target - date.today()).days


def phase(state: dict, when: date | None = None) -> str:
    """Where the company is in the month: idle, announced, or live.

    Named rather than tested as a pile of comparisons, because the banner, the
    Discord event and the trailer all have to agree on this, and three places
    each deciding "is it a week yet" is how they drift apart.
    """
    left = days_until(state, when)
    if left is None:
        return "idle"
    if left <= 0:
        return "live"
    if left <= ANNOUNCE_LEAD_DAYS:
        return "announced"
    if left <= COUNTDOWN_WINDOW_DAYS:
        return "countdown"
    return "idle"


def _public_app_entry(value) -> dict:
    if isinstance(value, dict):
        ver = format_version(parse(value.get("version") or "1.0.0"))
        out = {"version": ver}
        for key in ("title", "description", "download_url", "released"):
            if value.get(key):
                out[key] = str(value[key])
        notes = value.get("notes")
        if isinstance(notes, list):
            out["notes"] = [str(n) for n in notes if str(n).strip()][:12]
        if value.get("restart_required") is not None:
            out["restart_required"] = bool(value.get("restart_required"))
        return out
    return {"version": format_version(parse(value or "1.0.0"))}


def publish_public(state: dict) -> bool:
    """Write the small file the website and the apps read.

    Only fields the page actually needs, and nothing secret: this file is
    served publicly, so a token or an internal id must never end up in it.

    Returns whether it was written. site/ is the published folder and is
    regenerated during a deploy, so a failure here is not fatal to a release,
    but it must not be reported as a success.
    """
    ph = phase(state)
    left = days_until(state)
    when = next_major_date(state)
    raw_apps = state.get("apps") or {}
    apps_out = {}
    if isinstance(raw_apps, dict):
        for k, v in raw_apps.items():
            apps_out[str(k)] = _public_app_entry(v)
    out = {
        "version": state.get("version") or "1.0.0",
        "updated": state.get("updated"),
        # None rather than a stale date, so an old countdown cannot survive a
        # release by sitting in the page forever
        "phase": ph,
        "next_major": None if ph in ("idle", "live") else when.isoformat()
        if when else None,
        "days_left": None if ph in ("idle", "live") else left,
        "next_major_title": None if ph == "idle" else
        state.get("next_major_title"),
        "next_major_notes": [] if ph == "idle" else
        list(state.get("next_major_notes") or [])[:6],
        "trailer": state.get("last_trailer"),
        # Per-app update metadata for installed apps. Backward compatible:
        # each entry always includes a version string.
        "apps": apps_out,
        "latest_update": {
            "title": state.get("last_update_title"),
            "description": state.get("last_update_description") or "",
            "notes": list(state.get("last_update_notes") or [])[:12],
            "released": state.get("last_update_at") or state.get("updated"),
        },
    }
    try:
        PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        log(f"could not write {PUBLIC.name}: {e}")
        log("the countdown the homepage reads was NOT refreshed")
        return False
    log(f"public file says {ph}")
    return True


def main() -> int:
    state = load()
    args = [a.strip().lower() for a in sys.argv[1:]]

    if "--set" in args:
        i = args.index("--set")
        if i + 1 >= len(sys.argv):
            raise SystemExit("[update] --set needs a version, e.g. --set 2.0.0")
        state["version"] = format_version(parse(sys.argv[i + 1]))
    elif "--bump" in args:
        i = args.index("--bump")
        level = sys.argv[i + 1] if i + 1 < len(sys.argv) else "patch"
        if level not in LEVELS:
            log(f"{level!r} is not one of {LEVELS}, using patch")
            level = "patch"
        state["version"] = bump(state.get("version") or "1.0.0", level)
        log(f"bumped to {state['version']}")

    # both writes report whether they happened, so a run that changed nothing
    # exits non-zero instead of looking like a successful bump
    wrote = save(state)
    published = publish_public(state)

    log(f"version {state.get('version')}")
    log(f"phase {phase(state)}")
    when = next_major_date(state)
    if when:
        left = days_until(state)
        log(f"next major {when.isoformat()} ({left:+d} days)")
    print()
    print(json.dumps({"version": state.get("version"),
                      "phase": phase(state),
                      "days_left": days_until(state),
                      "apps": state.get("apps") or {}}, indent=2))
    if not (wrote and published):
        log("the run did not complete: at least one write failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())