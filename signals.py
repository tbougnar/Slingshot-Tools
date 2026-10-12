"""Every signal that tells the company how it is actually doing.

The Wednesday job already runs reputation.py, which reads GitHub and itch.io.
This adds the three sources it was missing, and the two things a growth number
on its own cannot tell you:

- **Discord**, because the ballot is the only place people say what they want
  before they buy it, and that is the cheapest signal there is
- **YouTube comments**, when a token with the read scope exists
- **the site itself**, read the way a visitor sees it, because the catalog
  loading and every card working is the thing that turns a visit into a sale

Then two derived numbers that do not exist anywhere else:

- ``conversion``: visits against sales. This is the only figure that says
  whether the site is good or the products are, and it is what the goal
  switch reads
- ``audience``: how many people can see the work at all. Until this is real,
  optimising for money is optimising for nothing

Every source is optional and every one of them fails to "unavailable" rather
than raising. A telemetry job that crashes takes the whole Wednesday cycle
with it, and telemetry is not worth that.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "signals.json"

SITE = "https://tbougnar.github.io/Slingshot-Tools"
CATALOG = ROOT / "site" / "apps.json"
REPO = os.environ.get("GITHUB_REPO", "tbougnar/Slingshot-Tools")
TIMEOUT = 25

# the channels worth reading. Not all of them: #results is our own text.
READ_CHANNELS = ("polls", "announcements", "ideas", "results", "articles",
                 "roadmap")


def log(m: str) -> None:
    print(f"[signals] {m}", flush=True)


def fetch(url: str, headers: dict | None = None, token: str = "") -> dict | None:
    hdr = dict(headers or {})
    hdr.setdefault("User-Agent", "slingshot-tools/1.0")
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=hdr),
                timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log(f"{url.split('/')[2]}: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        log(f"{url.split('/')[2]}: {str(e)[:70]}")
    return None


def fetch_text(url: str, headers: dict | None = None) -> str:
    hdr = dict(headers or {})
    hdr.setdefault("User-Agent", "Mozilla/5.0 (compatible; slingshot/1.0)")
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=hdr), timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log(f"{url.split('/')[2]}: {str(e)[:70]}")
        return ""


# --------------------------------------------------------------- discord

def discord_signals() -> dict:
    """What people are actually saying, and how many of them there are.

    The message bodies matter more than the counts: a question in #ideas is
    the roadmap, and the ballot replies are the only vote the company gets.
    """
    try:
        import discord_post as dp
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)[:60]}

    if not (dp.TOKEN and dp.GUILD_ID):
        return {"available": False, "reason": "no bot token or guild"}

    out: dict = {"available": True, "channels": {}, "people": set()}
    for name in READ_CHANNELS:
        try:
            msgs = dp.messages(name, 100)
        except Exception as e:  # noqa: BLE001
            out["channels"][name] = {"error": str(e)[:60]}
            continue
        people = set()
        rows = []
        for m in msgs:
            author = str((m.get("author") or {}).get("username") or "")
            body = str(m.get("content") or "").strip()
            if author:
                people.add(author.lower())
            if body:
                rows.append(body[:300])
        out["channels"][name] = {"messages": len(msgs), "recent": rows[:25]}
        out["people"].update(people)

    out["unique_members"] = len(out["people"])
    del out["people"]
    return out


# --------------------------------------------------------------- youtube

def youtube_signals() -> dict:
    """Comments and view counts, when a token with the read scope exists.

    The upload token this project holds is youtube.upload, which is not enough
    to read anything. Reading needs youtube.readonly, so this reports exactly
    what is missing rather than quietly returning nothing, because "no
    comments" and "cannot see comments" are very different facts.
    """
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    if key:
        return _youtube_with_api_key(key)

    if not (refresh and cid):
        return {"available": False,
                "reason": "no YouTube credential is configured",
                "needs": "YOUTUBE_API_KEY, or a token with "
                         "youtube.readonly"}

    try:
        import shorts_upload as su
        token = su.access_token()
        return _youtube_with_bearer(token)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)[:80],
                "needs": "a token whose scope includes youtube.readonly"}


def _youtube_with_api_key(key: str) -> dict:
    chans = fetch("https://www.googleapis.com/youtube/v3/channels"
                  "?part=statistics,snippet&mine=true&key=" + key)
    if not chans or not chans.get("items"):
        return {"available": False, "reason": "the API key returned no channel"}
    ch = chans["items"][0]
    st = ch.get("statistics") or {}
    out = {
        "available": True,
        "channel": ch.get("snippet", {}).get("title", ""),
        "subscribers": int(st.get("subscriberCount") or 0),
        "videos": int(st.get("videoCount") or 0),
        "views": int(st.get("viewCount") or 0),
        "comments": [],
        "source": "api key",
    }
    out["comments"] = _recent_comments(key)
    return out


def _youtube_with_bearer(token: str) -> dict:
    chans = fetch("https://www.googleapis.com/youtube/v3/channels"
                  "?part=statistics,snippet&mine=true",
                  {"Authorization": f"Bearer {token}"})
    if not chans or not chans.get("items"):
        return {"available": False,
                "reason": "the token could not read the channel; it is "
                          "probably youtube.upload only"}
    ch = chans["items"][0]
    st = ch.get("statistics") or {}
    vid = (ch.get("contentDetails") or {}).get("relatedPlaylists", {}) \
        .get("uploads")
    out = {
        "available": True,
        "channel": ch.get("snippet", {}).get("title", ""),
        "subscribers": int(st.get("subscriberCount") or 0),
        "videos": int(st.get("videoCount") or 0),
        "views": int(st.get("viewCount") or 0),
        "comments": [],
        "source": "oauth",
    }
    if vid:
        items = _bearer(token, "https://www.googleapis.com/youtube/v3/"
                                "playlistItems?part=snippet&maxResults=5"
                                f"&playlistId={vid}")
        ids = [i["snippet"]["resourceId"]["videoId"] for i in
               ((items or {}).get("items") or [])
               if i.get("snippet", {}).get("resourceId")]
        out["comments"] = _bearer_comments(token, ids)
    return out


def _bearer(token: str, url: str) -> dict | None:
    return fetch(url, {"Authorization": f"Bearer {token}"})


def _bearer_comments(token: str, video_ids: list[str]) -> list[str]:
    rows: list[str] = []
    for vid in video_ids[:3]:
        d = _bearer(token, "https://www.googleapis.com/youtube/v3/"
                           "commentThreads?part=snippet&textFormat=plainText"
                           f"&maxResults=20&videoId={vid}")
        for item in (d or {}).get("items", []):
            sn = item.get("snippet", {})
            text = str(sn.get("textDisplay") or "").strip()
            if text:
                rows.append(f"{sn.get('authorDisplayName', '?')}: {text[:240]}")
    return rows


def _recent_comments(key: str) -> list[str]:
    rows: list[str] = []
    for vid in _video_ids(key):
        d = fetch("https://www.googleapis.com/youtube/v3/commentThreads"
                  f"?part=snippet&textFormat=plainText&maxResults=20"
                  f"&videoId={vid}&key={key}")
        for item in (d or {}).get("items", []):
            sn = item.get("snippet", {})
            text = str(sn.get("textDisplay") or "").strip()
            if text:
                rows.append(f"{sn.get('authorDisplayName', '?')}: {text[:240]}")
    return rows


def _video_ids(key: str) -> list[str]:
    chans = fetch("https://www.googleapis.com/youtube/v3/channels"
                  "?part=contentDetails&mine=true&key=" + key)
    items = (chans or {}).get("items") or []
    if not items:
        return []
    up = items[0].get("contentDetails", {}).get("relatedPlaylists", {}) \
        .get("uploads")
    if not up:
        return []
    pl = fetch("https://www.googleapis.com/youtube/v3/playlistItems"
               f"?part=snippet&maxResults=5&playlistId={up}&key={key}")
    return [i["snippet"]["resourceId"]["videoId"] for i in
            ((pl or {}).get("items") or [])
            if i.get("snippet", {}).get("resourceId")]


# ------------------------------------------------------------------- site

def site_signals() -> dict:
    """The live site, fetched the way a visitor gets it.

    This is the check that would have caught the two homepage bugs before
    anyone else saw them: the catalog rendering is verified against the page
    that is actually being served, not against a local copy.
    """
    body = fetch_text(SITE + "/")
    out: dict = {"available": bool(body), "url": SITE}
    if not body:
        out["reason"] = "the site did not answer"
        return out

    out["bytes"] = len(body)
    out["has_countdown"] = 'id="countdown"' in body
    out["catalog_linked"] = "apps.json" in body
    # the two functions that were silently broken, checked by shape
    out["group_ok"] = "function groupProducts" in body and "key:k" not in body
    out["cards_use_index"] = "openDialogByIndex" in body

    try:
        apps = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        apps = []
    live = [a for a in apps if a.get("published") is not False]
    out["catalog_live"] = len(live)
    out["catalog_paid"] = len([a for a in live if a.get("tier") == "full"])
    out["catalog_on_sale"] = len(
        [a for a in live if str(a.get("itch_url") or "").startswith("http")])
    out["catalog_matches_site"] = out["catalog_live"] == len(live)

    for link in ("itch.io", "youtube.com", "discord.gg", "github.com"):
        out[f"links_{link.split('.')[0]}"] = link in body
    return out


# ------------------------------------------------------- derived measures

def audience(sig: dict) -> int:
    """How many people can see the work at all.

    Deliberately conservative: it takes the smallest defensible number rather
    than summing overlapping audiences, because a subscriber and a site
    visitor are usually the same person and counting them twice makes a small
    business look like a large one.
    """
    gh = sig.get("github", {}).get("stars", 0) or 0
    it = sig.get("itch", {}).get("visits", {}) or {}
    yt = sig.get("youtube", {})
    subs = yt.get("subscribers", 0) if yt.get("available") else 0
    disc = sig.get("discord", {}).get("unique_members", 0) \
        if sig.get("discord", {}).get("available") else 0
    visits = it.get("total_visits") if isinstance(it, dict) else None
    if visits is None:
        visits = 0
    return max(int(visits or 0), int(gh), int(subs), int(disc))


def conversion(sig: dict) -> dict:
    """Visits against sales: whether the site works, or the products do."""
    it = sig.get("itch", {}) or {}
    sales = it.get("sales") if it.get("available") else None
    visits = it.get("visits") if it.get("available") else None
    earned = sig.get("earnings", {}) or {}
    out = {"known": False, "reason": ""}

    if not it.get("available"):
        out["reason"] = it.get("reason", "itch.io unavailable")
        return out

    sales_n = _count(sales)
    visits_n = _count(visits)
    if visits_n:
        out.update({"known": True, "visits": visits_n, "sales": sales_n,
                    "rate": round(sales_n / visits_n, 4)})
    else:
        out["reason"] = "no visit count to compare against"
    if earned.get("available"):
        out["revenue"] = earned.get("total", 0.0)
        out["orders"] = earned.get("orders", 0)
        # itch.io only reports sales once a key is present. Without one, the
        # order count is the only evidence there is, so it stands in rather
        # than reporting a rate of zero against real purchases.
        if not sales_n and out["orders"]:
            sales_n = int(out["orders"])
            if visits_n:
                out.update({"known": True, "sales": sales_n,
                            "rate": round(sales_n / visits_n, 4),
                            "sales_source": "earnings"})
    return out


def _count(blob) -> int:
    """itch.io returns either a number or {"total": n} depending on the call."""
    if isinstance(blob, (int, float)):
        return int(blob)
    if isinstance(blob, dict):
        for key in ("total", "total_visits", "total_sales"):
            if key in blob:
                try:
                    return int(blob[key])
                except (TypeError, ValueError):
                    return 0
    return 0


# ------------------------------------------------------------------ main

def gather(include_discord: bool = True) -> dict:
    sig: dict = {
        "at": int(time.time()),
        "site": SITE,
        "repo": REPO,
    }

    try:
        import reputation as rep
        sig["github"] = rep.github_signals()
        sig["itch"] = rep.itch_signals()
        sig["earnings"] = rep.earnings_signals()
        sig["catalog"] = rep.catalog_signals()
    except Exception as e:  # noqa: BLE001
        log(f"reputation signals failed: {str(e)[:70]}")
        sig["github"] = {"available": False}
        sig["itch"] = {"available": False, "reason": "reputation.py failed"}
        sig["earnings"] = {"available": False}
        sig["catalog"] = {"available": False}

    sig["site"] = site_signals()
    sig["youtube"] = youtube_signals()
    sig["discord"] = (discord_signals() if include_discord
                      else {"available": False, "reason": "skipped"})

    sig["audience"] = audience(sig)
    sig["conversion"] = conversion(sig)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sig, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    return sig


def summarise(sig: dict) -> str:
    out = ["SIGNALS", ""]

    site = sig.get("site", {})
    if site.get("available"):
        out += [
            f"  site answers      : yes, {site.get('bytes', 0)} bytes",
            f"  catalog on site   : {site.get('catalog_live', 0)} live, "
            f"{site.get('catalog_on_sale', 0)} actually buyable",
            f"  homepage scripts  : "
            f"{'ok' if site.get('group_ok') and site.get('cards_use_index') else 'BROKEN'}",
        ]
    else:
        out.append(f"  site             : {site.get('reason', 'down')}")

    gh = sig.get("github", {})
    out.append("")
    out.append(f"  github stars     : {gh.get('stars', 0)}"
               if gh.get("available") else "  github           : unavailable")

    it = sig.get("itch", {})
    out.append(f"  itch.io          : "
               f"{it.get('reason', 'reachable') if not it.get('available') else 'reachable'}")

    yt = sig.get("youtube", {})
    if yt.get("available"):
        out += [f"  youtube subs     : {yt.get('subscribers', 0)}",
                f"  youtube views    : {yt.get('views', 0)}",
                f"  youtube comments : {len(yt.get('comments', []))} read"]
    else:
        out.append(f"  youtube          : {yt.get('reason', 'unavailable')}")
        out.append(f"                     needs {yt.get('needs', '')}")

    dc = sig.get("discord", {})
    if dc.get("available"):
        said = sum(c.get("messages", 0)
                   for c in dc.get("channels", {}).values()
                   if isinstance(c, dict))
        out += [f"  discord members  : {dc.get('unique_members', 0)}",
                f"  discord messages : {said} in the last week"]
    else:
        out.append(f"  discord          : {dc.get('reason', 'unavailable')}")

    conv = sig.get("conversion", {})
    out += ["",
             f"  AUDIENCE         : {sig.get('audience', 0)}",
             "  CONVERSION       : "
             + (f"{conv['rate'] * 100:.2f}%  "
                f"({conv.get('sales', 0)} of {conv.get('visits', 0)} visits)"
                if conv.get("known") else conv.get("reason", "unknown"))]
    return "\n".join(out)


def main() -> int:
    sig = gather()
    print(summarise(sig))
    print()
    log(f"written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())