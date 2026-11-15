"""Read the week's signals and write them into the fixbook.

Every Wednesday, after the ballot has had a few days to collect votes and after
Friday's release has had a few days to be bought, this reads:

- the Discord ballot: what the community asked for, and what actually won
- the public reputation report from reputation.py
- recorded revenue
- every lesson the pipeline has learned while building

and writes a short review into data/fixbook.json. That review is what the next
build reads as coaching, so it has to be concrete and honest rather than
cheerful. A week with no sales is reported as a week with no sales.

This job only ever writes lessons. It cannot change the site, a price, or
remove anything; weekly_guard.py enforces that.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIXBOOK = DATA / "fixbook.json"
REPORT = DATA / "reputation.json"
EARNINGS = DATA / "earnings.json"
POLLS = DATA / "polls.json"
CATALOG = ROOT / "site" / "apps.json"
WEEKLY = DATA / "weekly_review.md"

# The model backend (OpenRouter first, Groq fallback) lives in providers.py.
# This file used to carry its own Groq URL, key and model.


def log(msg: str) -> None:
    print(f"[weekly] {msg}", flush=True)


def load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def week_key() -> str:
    t = datetime.now(timezone.utc)
    # ISO week, so the file name sorts chronologically
    y, w, _ = t.isocalendar()
    return f"{y}-W{w:02d}"


def ballot_state() -> dict:
    """The open ballot and the most recent winner."""
    polls = load(POLLS, {})
    if not isinstance(polls, dict):
        return {"open": None, "closed": []}
    closed = [p for p in polls.values()
              if isinstance(p, dict) and p.get("status") == "closed"]
    closed.sort(key=lambda p: p.get("closed") or 0, reverse=True)
    live = [p for p in polls.values()
            if isinstance(p, dict) and p.get("status") == "open"]
    live.sort(key=lambda p: p.get("created") or 0, reverse=True)
    return {"open": live[0] if live else None, "closed": closed[:5]}


def _write(path: Path, text: str) -> None:
    """Replace a tracked file atomically.

    These are committed files. A crash during a plain write_text left a
    truncated fixbook or review history, and the next build read it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def revenue() -> dict:
    """This week's money, from the file pricing.py actually writes.

    pricing.py writes {"revenue": total, "products": [{sales, revenue}, ...]}.
    This used to look for a list or an "orders" key and therefore reported
    $0.00 and 0 orders on every run, even when the file was full of sales.
    """
    data = load(EARNINGS, None)
    if data is None:
        return {"orders": 0, "total": 0.0, "available": False}
    if isinstance(data, list):
        total = 0.0
        for o in data:
            if isinstance(o, dict):
                try:
                    total += float(o.get("price") or o.get("amount") or 0)
                except (TypeError, ValueError):
                    continue
        return {"orders": len(data), "total": round(total, 2), "available": True}
    if isinstance(data, dict):
        orders = data.get("orders")
        if isinstance(orders, list):
            total = 0.0
            for o in orders:
                if isinstance(o, dict):
                    try:
                        total += float(o.get("price") or o.get("amount") or 0)
                    except (TypeError, ValueError):
                        continue
            return {"orders": len(orders), "total": round(total, 2),
                    "available": True}
        rows = data.get("products")
        if isinstance(rows, list):
            count = sum(int(r.get("sales") or 0)
                        for r in rows if isinstance(r, dict))
            if data.get("revenue") is not None:
                try:
                    total = float(data["revenue"])
                except (TypeError, ValueError):
                    total = 0.0
            else:
                total = sum(float(r.get("revenue") or 0)
                            for r in rows if isinstance(r, dict))
            return {"orders": count, "total": round(total, 2),
                    "available": True}
    return {"orders": 0, "total": 0.0, "available": True}


def live_products() -> list:
    apps = load(CATALOG, [])
    out = []
    for a in apps if isinstance(apps, list) else []:
        if a.get("published") is False:
            continue
        out.append({"slug": a.get("base_slug") or a.get("slug"),
                    "title": a.get("title"),
                    "tier": a.get("tier"),
                    "price": a.get("price")})
    return out


def facts() -> dict:
    """Everything the review is allowed to reason about."""
    rep = load(REPORT, {})
    gh = rep.get("github") or {}
    ball = ballot_state()
    return {
        "week": week_key(),
        "ballot_open": bool(ball["open"]),
        "ballot_question": (ball["open"] or {}).get("question", ""),
        "ballot_votes": sum(
            len(o.get("voters", []))
            for o in (ball["open"] or {}).get("options", [])),
        "recent_winners": [
            {"question": p.get("question"), "winner": p.get("winner"),
             "slug": p.get("winner_slug"),
             "votes": (p.get("result") or [])}
            for p in ball["closed"][:3]],
        "stars": gh.get("stars"),
        "forks": gh.get("forks"),
        "watchers": gh.get("watchers"),
        "repo_days": gh.get("days_old"),
        "revenue": revenue(),
        "products": live_products(),
        "known_problems": len(load(FIXBOOK, [])),
    }


def web_search(query: str) -> str:
    """Search the web for solutions to problems. Returns relevant results."""
    try:
        # Use DuckDuckGo HTML search as a fallback that doesn't require API keys
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        # Extract snippets (basic)
        results = []
        # Look for result snippets
        import re
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        for s in snippets[:5]:
            s = re.sub(r'<[^>]+>', '', s)
            s = s.strip()
            if s and len(s) > 20:
                results.append(s)
        return "\n\n".join(results) if results else ""
    except Exception as e:
        log(f"web search failed: {str(e)[:80]}")
        return ""


def research_problem(problem: str) -> str:
    """Research a problem using web search to learn solutions."""
    try:
        queries = [
            f"how to solve {problem} indie game tools software",
            f"marketing strategies {problem} small tools product",
            f"community growth {problem} discord votes engagement"
        ]
        all_results = []
        for q in queries[:2]:  # Limit to avoid too many requests
            res = web_search(q)
            if res:
                all_results.append(res)
        return "\n\n---\n\n".join(all_results) if all_results else ""
    except Exception:
        return ""


def groq(system: str, user: str, max_tokens: int = 1200) -> str:
    """The review text from the live backend, or "" when it cannot answer."""
    try:
        import providers
        if not providers.configured():
            return ""
        return (providers.chat(providers.best_model("chat"), system, user,
                               0.35, max_tokens, role="chat") or "").strip()
    except Exception as e:  # noqa: BLE001
        log(f"the model was unavailable ({str(e)[:120]})")
        return ""


REVIEW_SYSTEM = (
    "You are the weekly reviewer and self-improving AI for a small tool company that ships one new "
    "desktop tool every week. You write for the person who reads this before "
    "the next build.\n"
    "Your goal is to LEARN and ADAPT. Use web research to find concrete solutions to problems. "
    "Be specific and honest. If a number is zero, say it is zero and do not "
    "dress it up. Never invent a fact that is not in the data you are given. "
    "Do not be encouraging for its own sake.\n"
    "When you see problems (zero votes, zero revenue, no engagement, bugs), research proven strategies "
    "and give actionable steps the system can take automatically next week.\n"
    "Answer with markdown only: a '## What happened' section, a '## What to "
    "change' section with at most five concrete changes (each should be implementable), and a '## Risk' "
    "section naming the biggest thing that could go wrong. Under 400 words."
)


def review(f: dict) -> str:
    """The review, from the model when available, else from the facts."""
    # Research solutions for problems
    research = ""
    if f.get("ballot_votes", 0) == 0 or f.get("revenue", {}).get("orders", 0) == 0:
        log("researching solutions for zero activity...")
        research = research_problem("zero user engagement indie software tools discord voting")
    if f.get("known_problems", 0) > 50:
        log("researching solutions for backlog management...")
        research += "\n\n" + research_problem("backlog triage prioritization small team")
    
    user_msg = "Here is this week's data as JSON:\n\n" + json.dumps(f, indent=2, ensure_ascii=False)
    if research:
        user_msg += "\n\n## Web Research (for learning):\n\n" + research
    
    body = groq(REVIEW_SYSTEM, user_msg)
    if body:
        return body

    rev = f["revenue"]
    lines = ["## What happened"]
    if f["ballot_open"]:
        lines.append(f"- A ballot is open: \"{f['ballot_question']}\" "
                     f"with {f['ballot_votes']} vote(s) so far.")
    else:
        lines.append("- No ballot is open, so nobody is choosing next week's "
                     "tool.")
    if f["recent_winners"]:
        w = f["recent_winners"][0]
        lines.append(f"- Last ballot: {w['winner'] or 'a tie'} "
                     f"({w['slug'] or 'no slug'}).")
    lines.append(f"- {len(f['products'])} product(s) on sale.")
    if rev.get("available") is False:
        lines.append("- Revenue data is not available in this checkout "
                     "(data/earnings.json was not produced), so the number of "
                     "sales is unknown rather than zero.")
    else:
        lines.append(f"- Revenue recorded: ${rev['total']:.2f} "
                     f"from {rev['orders']} order(s).")
    if f["stars"] is not None:
        lines.append(f"- Public interest: {f['stars']} stars, "
                     f"{f['forks']} forks.")

    lines += ["", "## What to change"]
    if rev.get("available") is not False and rev["orders"] == 0:
        lines.append("- No sales at all. Check that the checkout works end to "
                     "end before changing anything else.")
    if not f["ballot_votes"]:
        lines.append("- Nobody voted. The ballot may be posted where members "
                     "cannot see it.")
    lines.append("- Compare the winner of the last ballot against what was "
                 "actually built.")

    lines += ["", "## Risk"]
    lines.append("- The model that writes this review was unavailable, so "
                 "this one is generated from the raw numbers only.")
    return "\n".join(lines)


def next_id(entries: list) -> str:
    used = [int(e["id"][1:]) for e in entries
            if str(e.get("id", "")).startswith("B") and e["id"][1:].isdigit()]
    return f"B{max(used, default=0) + 1:03d}"


def record(f: dict, body: str) -> dict:
    """Store the review and add a fixbook entry pointing at it."""
    entries = load(FIXBOOK, [])
    if not isinstance(entries, list):
        entries = []

    f["text"] = body
    DATA.mkdir(parents=True, exist_ok=True)
    # Merge, do not replace. Writing {week: f} overwrote the file with a single
    # week and destroyed every earlier review, which is the history the next
    # build is supposed to read.
    history = load(DATA / "weekly_reviews.json", {})
    if not isinstance(history, dict):
        history = {}
    history[f["week"]] = f
    _write(DATA / "weekly_reviews.json",
           json.dumps(history, indent=2, ensure_ascii=False) + "\n")
    _write(WEEKLY, f"# Week {f['week']}\n\n{body}\n")

    rev = f["revenue"]
    cause = ""
    for line in body.splitlines():
        text = line.strip().lstrip("-* ").strip()
        if text and not text.startswith("#"):
            cause = text[:280]
            break
    entry = {
        "id": next_id(entries),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "symptom": (f"weekly review {f['week']}: "
                    f"{rev['orders']} order(s), ${rev['total']:.2f}, "
                    f"{f['stars']} star(s), "
                    f"{f['ballot_votes']} vote(s) on the open ballot"),
        "cause": cause,
        "fix": "read data/weekly_reviews.json before the next build; "
               "it carries this week's numbers and what to change",
        "files": ["data/weekly_reviews.json", "weekly_review.py"],
        "detects": "recurs every Wednesday; one entry per week is expected",
        "verified": False,
    }
    entries.append(entry)
    _write(FIXBOOK, json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    return entry


def main() -> int:
    f = facts()
    log(f"week {f['week']}: {len(f['products'])} product(s), "
        f"{f['revenue']['orders']} order(s), ${f['revenue']['total']:.2f}")
    if f["stars"] is not None:
        log(f"public: {f['stars']} star(s), {f['forks']} fork(s)")

    body = review(f)
    entry = record(f, body)
    log(f"recorded {entry['id']}")

    print()
    print(body)
    print()
    print(f"[weekly] written to {WEEKLY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())