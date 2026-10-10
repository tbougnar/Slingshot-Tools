"""Shared Discord state: ballots, votes, and per-tool articles.

Kept separate from the bot so the pipeline can read and write the same files
without importing a Discord library. Every function is safe to call with no
Discord configuration at all.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
# Ballots and votes stay on the machine that runs the bot: they hold Discord
# user ids, so they must never be committed to a public repository.
POLLS = DATA / "polls.json"
# Articles are public marketing copy, so they are tracked and readable wherever
# the bot runs.
ARTICLES = ROOT / "discord_articles.json"
CATALOG = ROOT / "site" / "apps.json"
PUBLISHED = DATA / "published.json"

SITE_URL = "https://tbougnar.github.io/Slingshot-Tools"

# ballot lifetime; after this a run may close the poll and report it
POLL_LIFETIME_DAYS = 21

# Ballots and votes hold Discord user ids, so they must stay off git. The
# catalog is public, but these are not.
GITIGNORE = ROOT / ".gitignore"
_IGNORED = {
    "data/polls.json",
    "data/discord_sent.json",
}


def ignored_paths() -> set:
    """Ballot and vote files that must never be committed."""
    return {p for p in _IGNORED if (ROOT / p).exists()}


def log(msg: str) -> None:
    print(f"[discord] {msg}", flush=True)


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def catalog() -> list:
    data = _load(CATALOG, [])
    return data if isinstance(data, list) else []


def live_tools() -> list:
    """Published product families, cheapest description first."""
    families: dict[str, dict] = {}
    for a in catalog():
        if a.get("published") is False:
            continue
        key = a.get("base_slug") or a.get("slug")
        fam = families.setdefault(key, {"base": key, "full": None, "basic": None})
        if a.get("tier") == "basic":
            fam["basic"] = a
        else:
            fam["full"] = a
    out = []
    for fam in families.values():
        head = fam["full"] or fam["basic"] or {}
        out.append({
            "base": fam["base"],
            "title": head.get("title", fam["base"]),
            "blurb": (fam["full"] or fam["basic"] or {}).get("blurb", ""),
            "tags": (fam["full"] or fam["basic"] or {}).get("tags", []),
            "free_url": (fam["basic"] or {}).get("url", ""),
            "price": float((fam["full"] or {}).get("price") or 0),
            "buy_url": (f"{SITE_URL}/checkout.html?slug={fam['base']}"
                        if (fam["full"] or {}).get("published") is True else ""),
        })
    out.sort(key=lambda t: t["title"].lower())
    return out


def tool_by_slug(slug: str) -> dict | None:
    slug = (slug or "").strip().lower()
    for t in live_tools():
        if slug in (t["base"].lower(), t["base"].lower() + "-basic"):
            return t
    return None


# --------------------------------------------------------------------- polls

def polls() -> dict:
    data = _load(POLLS, {})
    return data if isinstance(data, dict) else {}


def _save_polls(data: dict) -> None:
    _save(POLLS, data)


def open_polls() -> list:
    """Every ballot still open, newest last."""
    out = [p for p in polls().values()
           if isinstance(p, dict) and p.get("status") == "open"]
    out.sort(key=lambda p: p.get("created") or 0)
    return out


def open_poll() -> dict | None:
    """The ballot to show and vote on: the most recent one still open.

    Newest rather than first, because a stray second ballot must not shadow
    the live one.
    """
    live = open_polls()
    return live[-1] if live else None


def create_poll(pid: str, question: str, options: list, notes: str = "") -> dict:
    """Options are short strings; the slug is used to steer the next build."""
    data = polls()
    data[pid] = {
        "id": pid,
        "question": question,
        "notes": notes,
        "options": [{"label": str(o), "voters": []} for o in options],
        "status": "open",
        "created": int(time.time()),
        "closed": None,
    }
    _save_polls(data)
    log(f"opened poll {pid} with {len(options)} option(s)")
    return data[pid]


def vote(pid: str, label: str, user_id: str) -> str:
    """Record one vote. A member may only vote once per poll.

    Returns "ok", "changed", "closed" or "error:<reason>".
    """
    data = polls()
    poll = data.get(pid)
    if not isinstance(poll, dict):
        return "error:unknown poll"
    if poll.get("status") != "open":
        return "closed"
    for opt in poll.get("options", []):
        if opt.get("label") != label:
            continue
        voters = opt.setdefault("voters", [])
        elsewhere = any(str(user_id) in o.get("voters", [])
                        for o in poll["options"] if o is not opt)
        if str(user_id) in voters:
            if elsewhere:
                # move the vote instead of silently counting it twice
                for o in poll["options"]:
                    if o is not opt and str(user_id) in o.get("voters", []):
                        o["voters"].remove(str(user_id))
                voters.append(str(user_id))
                _save_polls(data)
                return "changed"
            return "ok"
        for o in poll["options"]:
            if o is not opt and str(user_id) in o.get("voters", []):
                o["voters"].remove(str(user_id))
        voters.append(str(user_id))
        _save_polls(data)
        return "ok"
    return "error:unknown option"


def tally(pid: str) -> list:
    poll = polls().get(pid) or {}
    rows = [{"label": o.get("label"), "votes": len(o.get("voters", []))}
            for o in poll.get("options", [])]
    rows.sort(key=lambda r: (-r["votes"], r["label"]))
    return rows


def winner(pid: str) -> str | None:
    rows = tally(pid)
    if not rows:
        return None
    top = rows[0]["votes"]
    if top <= 0:
        return None
    # a tie is not a mandate, so let the next ballot decide instead
    if len(rows) > 1 and rows[1]["votes"] == top:
        return None
    return rows[0]["label"]


def close_votes(pid: str, counts: dict, winner_label: str = "",
                tie_broken: bool = False,
                message_id: str = "") -> dict | None:
    """Close a ballot whose votes were counted from the replies.

    ``counts`` maps an option label to how many people voted for it. The
    winner is passed in because deciding it needs the tie-break, which lives
    with the tallying code, not here.
    """
    data = polls()
    poll = data.get(pid)
    if not isinstance(poll, dict) or poll.get("status") != "open":
        return None

    for opt in poll.get("options", []):
        n = int(counts.get(opt.get("label"), 0) or 0)
        opt["votes"] = n
        # keep the voters list the same length as the count so tally() agrees,
        # but label the entries so nobody mistakes them for real user ids
        opt["voters"] = [f"reply:{i}" for i in range(n)]

    if message_id:
        poll["message_id"] = message_id
    poll["counted_from"] = "replies"
    if tie_broken:
        poll["tie_broken"] = True

    poll["status"] = "closed"
    poll["closed"] = int(time.time())
    poll["result"] = [{"label": o.get("label"), "votes": o.get("votes", 0)}
                      for o in poll.get("options", [])]
    poll["result"].sort(key=lambda r: -r["votes"])
    poll["winner"] = winner_label or None

    _save_polls(data)
    log(f"closed poll {pid}; winner={poll['winner'] or 'no votes'}")
    return poll


def close_poll(pid: str) -> dict | None:
    data = polls()
    poll = data.get(pid)
    if not isinstance(poll, dict) or poll.get("status") != "open":
        return None
    poll["status"] = "closed"
    poll["closed"] = int(time.time())
    poll["result"] = tally(pid)
    poll["winner"] = winner(pid)
    _save_polls(data)
    log(f"closed poll {pid}; winner={poll['winner'] or 'tie'}")
    return poll


def expired(pid: str, days: int = POLL_LIFETIME_DAYS) -> bool:
    poll = polls().get(pid) or {}
    created = poll.get("created")
    if not created:
        return False
    return (time.time() - float(created)) > days * 86400


def recent_winners(limit: int = 5) -> list:
    """Closed-poll winners, most recent first, for steering the next build.

    Prefers the stored concept slug and falls back to the display label turned
    into a slug, so a ballot recorded by hand still steers a build.
    """
    data = polls()
    closed = [p for p in data.values()
              if isinstance(p, dict) and p.get("status") == "closed"
              and (p.get("winner") or p.get("winner_slug"))]
    closed.sort(key=lambda p: p.get("closed") or 0, reverse=True)
    out = []
    for p in closed[:limit]:
        slug = p.get("winner_slug") or str(p.get("winner") or "").strip().lower()
        slug = slug.replace(" ", "-").replace("_", "-")
        slug = re.sub(r"-+", "-", slug).strip("-")
        if slug and slug not in out:
            out.append(slug)
    return out


# ------------------------------------------------------------------ articles

def articles() -> dict:
    data = _load(ARTICLES, {})
    return data if isinstance(data, dict) else {}


def save_article(slug: str, body: str) -> None:
    data = articles()
    data[slug] = {"body": body.strip(), "written": int(time.time())}
    _save(ARTICLES, data)


def get_article(slug: str) -> str:
    entry = articles().get(slug)
    if isinstance(entry, dict):
        return entry.get("body", "")
    if isinstance(entry, str):
        return entry
    return ""
