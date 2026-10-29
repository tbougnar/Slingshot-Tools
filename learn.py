"""Friday coach: look at the catalog and any real usage signals we can see,
then write concrete lessons that Monday's build will read and apply."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CATALOG = SITE / "apps.json"
# Its own file, not data/lessons.txt. That path belongs to buglog, which
# appends the fixbook entries to it, and this script used to rewrite the whole
# file in its own format: the Wednesday coach run would have deleted all 110
# recorded bugs every week. The two are separate records and now live apart.
LESSONS = ROOT / "data" / "coach_lessons.txt"
STATS = ROOT / "data" / "stats.json"

# The model backend, its base URL, key and free-model chain all live in
# providers.py (OpenRouter first, Groq as fallback). This file used to carry
# its own Groq URL and key, which is why a provider change meant editing ten
# files and why a stale model id failed only at run time.
ITCH_PAGE = (os.environ.get("ITCH_PAGE") or "").strip() or "slingshot-tools"


def log(m):
    print(f"[coach] {m}", flush=True)


def groq_json(system, user, max_tokens=1200, temperature=0.4):
    """Structured reply from the live backend. Returns {} on any failure.

    providers.chat walks the free-model chain and handles a per-day cap, so
    the retry loop that used to sleep here is gone.
    """
    try:
        import providers
        raw = providers.chat(providers.best_model("chat"), system, user,
                             temperature, max_tokens, role="debug")
    except Exception as e:  # noqa: BLE001
        log(f"coach model unavailable: {str(e)[:120]}")
        return {}
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except (json.JSONDecodeError, ValueError):
        return {}


def itch_signals():
    """Real usage signals, from the one place that already collects them.

    This used to make its own request to {page}.itch.io/embed-stats, which is
    a game-level endpoint that answers 404 for an account, and it returned a
    different shape from the account-level api/1/x/stats/* that reputation.py
    uses. So the coach had been reporting no usage data for weeks, while the
    same numbers were being gathered a moment later by signals.py and thrown
    away. One fetch, one place, one shape.
    """
    try:
        import reputation
        got = reputation.itch_signals()
    except Exception as e:  # noqa: BLE001
        log(f"usage signals unavailable: {str(e)[:80]}")
        return None
    if not got.get("available"):
        return None
    return {"sales": got.get("sales"), "visits": got.get("visits")}


def main():
    apps = []
    if CATALOG.exists():
        try:
            apps = json.loads(CATALOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            apps = []
    signals = itch_signals()
    if STATS.exists():
        try:
            # read for the side effect of proving the file parses; the values
            # are only ever written, never compared
            json.loads(STATS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    now = {a["slug"]: a.get("date", "") for a in apps}
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(now, indent=2), encoding="utf-8")

    week = date.today() - timedelta(days=7)
    fresh = [a for a in apps if a.get("date", "") >= week.isoformat()]

    previous_lessons = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""

    system = ("You are the product coach for Slingshot Tools, a one-person studio that "
              "ships one small useful web app every Monday and improves it on Friday. "
              "You are specific, never flattering, never inventing data. Return JSON only.")
    user = (
        f"Catalog right now ({len(apps)} apps):\n"
        f"{json.dumps([{k: a.get(k) for k in ('slug','title','tag','blurb','date')} for a in apps], indent=1)}\n\n"
        f"Shipped in the last 7 days: {[a['title'] for a in fresh] or 'none'}\n\n"
        f"Real usage signals available: {json.dumps(signals) if signals else 'NONE YET - no installs/downloads data is wired up, so reason from the catalog only and do not invent numbers.'}\n\n"
        f"Lessons carried over from last week:\n{previous_lessons or '(none)'}\n\n"
        "Write this week's lessons for the NEXT app. Focus on: picking a problem people "
        "genuinely feel daily, one clear job per app, a real empty state, and making the "
        "app feel premium in CSS. Drop any lesson that no longer applies.\n\n"
        'Return JSON only: {"keep":["short durable lessons"],"add":["new lessons for next app"],'
        '"drop":["lessons to retire"],"next_concepts":["6 kebab-case tool ideas for daily life"]}'
    )
    d = groq_json(system, user)
    if not d:
        log("no coach output; lessons unchanged")
        return 0

    keep = [str(x) for x in (d.get("keep") or [])][:6]
    add = [str(x) for x in (d.get("add") or [])][:6]
    drop = {str(x) for x in (d.get("drop") or [])}
    old = [l for l in previous_lessons.splitlines()
           if l.strip().startswith("- ")]
    if keep:
        # The model has already rewritten the list in its own words, so its
        # "keep" is the answer. This used to be computed and thrown away,
        # which meant the two disagreeing fields were silently resolved in
        # favour of one of them.
        kept = [f"- {k}" for k in keep]
        log(f"using the model's {len(kept)} kept lesson(s)")
    else:
        kept = [l for l in old if not any(k[:20] in l for k in drop)]
        log(f"no keep list; subtracting {len(drop)} dropped from "
            f"{len(old)} carried over")
    lines = kept + add
    text = ("# Slingshot Tools lessons (updated %s)\n\n" % date.today()
            + "\n".join(f"- {l}" for l in lines[:14]) + "\n")
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    LESSONS.write_text(text, encoding="utf-8")
    log(f"wrote {len(lines[:14])} lessons")

    ideas = ROOT / "data" / "next_concepts.json"
    ideas.write_text(json.dumps(d.get("next_concepts") or [], indent=2), encoding="utf-8")
    log(f"saved {len(d.get('next_concepts') or [])} future concepts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
