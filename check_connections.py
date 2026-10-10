"""Check every credential the weekly cycle depends on.

Run this after changing a secret. It answers one question: is each connection
actually usable, right now, without building or posting anything.

Values are never printed, only whether they work and, where useful, what they
belong to. A credential that fails is reported with what to do about it, not
just that it failed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 30

# Cloudflare refuses requests that look like a bare script, answering 403 with
# code 1010 to anything using urllib's default User-Agent. That is a refusal of
# the fingerprint, not of the address, and it looks exactly like a blocked IP.
# Presenting an ordinary browser string gets through and lets a real 401 or 403
# mean what it says.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def get(url: str, headers: dict | None = None, data: bytes | None = None,
         timeout: int = TIMEOUT):
    """urllib with the User-Agent Cloudflare expects.

    Discord rate limits hard, and answers a burst with 429. Waiting out the
    retry_after it asks for is the difference between a truthful report and a
    cascade of 403s that look like a permissions fault.
    """
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)

    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            try:
                raw = json.loads(e.read().decode("utf-8", "replace"))
                wait = min(float(raw.get("retry_after", 1.0)) + 0.2, 8.0)
            except Exception:  # noqa: BLE001
                wait = 1.5 * (attempt + 1)
            time.sleep(wait)
            # a 429 body is consumed, so rebuild the request
            req = urllib.request.Request(url, data=data, headers=h)
    # out of retries: let the caller see the original condition
    raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)


def log(msg: str) -> None:
    print(f"[check] {msg}", flush=True)


def ok(label: str, detail: str = "") -> bool:
    print(f"  PASS  {label}" + (f" - {detail}" if detail else ""))
    return True


def bad(label: str, why: str, fix: str = "") -> bool:
    print(f"  FAIL  {label} - {why}")
    if fix:
        print(f"        {fix}")
    return False


# --------------------------------------------------------------------- groq

def blocked_by_cloudflare(e: urllib.error.HTTPError) -> bool:
    """Still a 403/1010? Then something upstream is refusing, not the key.

    With a browser User-Agent in place this should not happen for the common
    services, so treat it as a network-level block rather than a bad secret.
    """
    try:
        body = e.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return e.code == 403
    return e.code == 403 and ("1010" in body or "banned" in body.lower())


PLACEHOLDERS = {
    "paste", "<paste>", "your_real", "your real", "changeme", "change_me",
    "todo", "xxx", "test", "example", "placeholder", "none", "null",
    "here", "replace_me", "your_token", "your_key", "token_here",
}


def looks_fake(value: str) -> bool:
    """Catch a copied example that was never replaced with a real value.

    Far too easy to paste the sample line out of the instructions and spend
    an hour debugging a 403 for a credential that was never really there.
    """
    v = value.strip().lower()
    if not v:
        return False
    if any(p in v for p in PLACEHOLDERS):
        return True
    # a real key is long and dense; an example is short or dashed prose
    if len(v) < 20:
        return True
    if v.count("_") > 2 or "your" in v:
        return True
    return False


def require_real(name: str, value: str, how: str) -> bool:
    if not value.strip():
        return bad(name, "not set", how)
    if looks_fake(value):
        print(f"  FAIL  {name} - this is still the example text, not a real "
              f"value")
        print(f"        {how}")
        return False
    return True


def check_groq() -> bool:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not require_real("groq", key,
                        "gh secret set GROQ_API_KEY --repo "
                        "tbougnar/Slingshot-Tools"):
        return False
    try:
        with get("https://api.groq.com/openai/v1/models",
                 {"Authorization": f"Bearer {key}"}) as r:
            data = json.loads(r.read().decode("utf-8"))
        return ok("groq", f"{len(data.get('data') or [])} models reachable")
    except urllib.error.HTTPError as e:
        if blocked_by_cloudflare(e):
            return bad("groq",
                       "refused by Cloudflare (403/1010) even with a browser "
                       "header",
                       "this is a network block on the way out, not a bad "
                       "key")
        if e.code in (401, 403):
            return bad("groq", "the key was rejected",
                       "make a new one at https://console.groq.com/keys, then "
                       "gh secret set GROQ_API_KEY --repo "
                       "tbougnar/Slingshot-Tools")
        return bad("groq", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return bad("groq", str(e)[:80])


# -------------------------------------------------------------------- itch

def check_itch_api() -> bool:
    key = os.environ.get("ITCH_API_KEY", "").strip()
    if not require_real("itch.io api", key,
                        "https://itch.io/settings/user, then "
                        "gh secret set ITCH_API_KEY --repo "
                        "tbougnar/Slingshot-Tools"):
        return False
    try:
        with get("https://api.itch.io/profile",
                 {"Authorization": f"Bearer {key}"}) as r:
            user = json.loads(r.read().decode("utf-8"))["user"]
        name = user.get("username", "?")
        detail = f"account {name}"
        if not user.get("developer"):
            detail += " (not a developer account yet)"
        return ok("itch.io api", detail)
    except urllib.error.HTTPError as e:
        if blocked_by_cloudflare(e):
            return bad("itch.io api", "refused by Cloudflare (403/1010)")
        if e.code in (401, 403):
            return bad("itch.io api", "the key was rejected",
                       "make a new one at https://itch.io/settings/user, then "
                       "gh secret set ITCH_API_KEY --repo "
                       "tbougnar/Slingshot-Tools")
        return bad("itch.io api", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return bad("itch.io api", str(e)[:80])


def check_itch_session() -> bool:
    """Only matters for creating a project; uploads do not need it."""
    raw = os.environ.get("ITCH_SESSION_COOKIE", "").strip()
    if not require_real("itch.io session", raw,
                        "log in at itch.io, F12, Console, "
                        "document.cookie, copy the itchio_token= part, then "
                        "gh secret set ITCH_SESSION_COOKIE --repo "
                        "tbougnar/Slingshot-Tools"):
        return False

    cookie = ""
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith("itchio_token="):
            cookie = part.split("=", 1)[1].strip()
            break
        if "=" not in part and len(part) > 20:
            cookie = part
            break
    if not cookie:
        return bad("itch.io session", "no itchio_token found in the value",
                   "copy only the itchio_token cookie from the browser")

    try:
        with get("https://itch.io/settings/mine/new/game",
                 {"Cookie": f"itchio_token={cookie}"}) as r:
            r.read()
            landed = r.geturl()
    except urllib.error.HTTPError as e:
        # a 404 on the new-game form means the cookie worked and that page
        # moved; the sign-in page is the only real failure
        if e.code == 404:
            return ok("itch.io session", "accepted (the form moved)")
        return bad("itch.io session", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return bad("itch.io session", str(e)[:80])

    if "/login" in landed:
        return bad("itch.io session",
                   "the cookie was refused, so it has expired",
                   "log out and in at itch.io, then "
                   "gh secret set ITCH_SESSION_COOKIE --repo "
                   "tbougnar/Slingshot-Tools")
    return ok("itch.io session", "can create projects")


def check_itch_user() -> bool:
    user = os.environ.get("ITCH_USER", "").strip()
    if not user:
        return bad("itch.io user", "ITCH_USER is not set",
                   "gh variable set ITCH_USER --body <yoursubdomain> "
                   "--repo tbougnar/Slingshot-Tools")
    if user != user.lower():
        return bad("itch.io user", f"{user!r} is not lowercase",
                   "butler targets are lowercase; reset the variable")
    return ok("itch.io user", user)


# ----------------------------------------------------------------- discord

def check_discord() -> bool:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild = os.environ.get("DISCORD_GUILD_ID", "").strip()

    if not require_real("discord bot", token,
                        "the Discord Developer Portal, your app, Bot, "
                        "Reset Token; then gh secret set "
                        "DISCORD_BOT_TOKEN --repo tbougnar/Slingshot-Tools"):
        return False
    if not guild:
        return bad("discord server", "DISCORD_GUILD_ID is not set",
                   "right-click the server name, Copy Server ID, then "
                   "gh secret set DISCORD_GUILD_ID --repo "
                   "tbougnar/Slingshot-Tools")

    head = {"Authorization": f"Bot {token}"}
    try:
        with get("https://discord.com/api/v10/users/@me", head) as r:
            me = json.loads(r.read().decode("utf-8"))
        if not ok("discord bot", f"{me['username']}#{me['discriminator']}"):
            return False
    except urllib.error.HTTPError as e:
        if blocked_by_cloudflare(e):
            return bad("discord bot", "refused by Cloudflare (403/1010)")
        if e.code == 401:
            return bad("discord bot", "the token was rejected (401)",
                       "reset it in the Developer Portal under Bot, then "
                       "gh secret set DISCORD_BOT_TOKEN --repo "
                       "tbougnar/Slingshot-Tools")
        return bad("discord bot", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return bad("discord bot", str(e)[:80])

    try:
        with get("https://discord.com/api/v10/users/@me/guilds",
                 head) as r:
            guilds = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return bad("discord server", str(e)[:80])

    names = {g["id"]: g["name"] for g in guilds}
    if guild not in names:
        return bad("discord server", f"the bot is not in {guild}",
                   f"it is in: {', '.join(names.values()) or 'nothing'}")
    if not ok("discord server", names[guild]):
        return False

    # the channels the pipeline posts into
    try:
        with get(f"https://discord.com/api/v10/guilds/{guild}/channels",
                 head) as r:
            chans = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        if code == 403:
            bad("discord channels",
                "the bot is in the server but cannot list its channels")
            describe_discord_permissions(token, guild)
            return False
        return bad("discord channels", str(e)[:80])

    import discord_post as dp
    wanted = ("announcements", "polls", "results", "articles", "catalog",
              "roadmap")
    missing = [w for w in wanted if not dp.find_channel(w, fresh=True)]
    if missing:
        return bad("discord channels",
                   f"not found: {', '.join(missing)}",
                   "python discord_setup_server.py rebuilds the layout")
    return ok("discord channels", f"all {len(wanted)} found")


# ------------------------------------------------------------------- site

def check_site() -> bool:
    url = "https://tbougnar.github.io/Slingshot-Tools/"
    try:
        with get(url) as r:
            body = r.read().decode("utf-8", "replace")
        return ok("website", f"{r.status}, {len(body)} bytes")
    except Exception as e:  # noqa: BLE001
        return bad("website", str(e)[:80])


def describe_discord_permissions(token: str, guild: str) -> None:
    """Print what Discord actually says, instead of inferring a cause.

    Guessing wrong here wastes the user's time: they grant permissions that
    were never the problem, see no change, and lose faith in the report. Every
    endpoint below is called with the status and body recorded, so the next
    round of guessing is grounded in what the API returned.
    """
    head = {"Authorization": f"Bot {token}"}
    base = "https://discord.com/api/v10"

    print("        --- what discord actually returned ---")

    def probe(label: str, path: str) -> object | None:
        time.sleep(1.2)  # Discord's limit is tight; stay well under it
        try:
            with get(f"{base}{path}", head) as r:
                body = r.read().decode("utf-8", "replace")
                print(f"        {label}: {r.status}")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = ""
            print(f"        {label}: HTTP {e.code} {body[:120]}")
        except Exception as e:  # noqa: BLE001
            print(f"        {label}: {str(e)[:90]}")
        return None

    gs = probe("guilds this token belongs to", "/users/@me/guilds")
    if isinstance(gs, list):
        print(f"          count: {len(gs)}")
        for g in gs:
            mark = "   <- the guild the secret names" \
                if g.get("id") == guild else ""
            print(f"          {g.get('id')}  {g.get('name')}{mark}")

    probe("bot member record (users route)",
          f"/users/@me/guilds/{guild}/member")
    probe("bot member record (guild route)",
          f"/guilds/{guild}/members/@me")
    probe("channel list", f"/guilds/{guild}/channels")
    probe("role list", f"/guilds/{guild}/roles")
    print("        --- end ---")


def check_webhook() -> bool:
    """The webhook path, which needs no bot permissions at all.

    Worth checking separately from the bot: it is the transport that works
    while Discord's guild endpoints are failing, so a green bot and a red
    webhook would be the wrong way round.
    """
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        log("DISCORD_WEBHOOK_URL is not set; announcements fall back to "
            "the bot")
        return True
    if not require_real("discord webhook", url,
                        "Server Settings, edit the channel, Integrations, "
                        "Webhooks, New Webhook, Copy URL"):
        return False

    # read the webhook itself rather than posting: this proves the URL and
    # token are good without putting a test message in front of the members
    try:
        with get(url) as r:
            data = json.loads(r.read().decode("utf-8"))
        return ok("discord webhook",
                  f"posts as {data.get('name', '?')} in "
                  f"#{data.get('channel_id', '?')}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return bad("discord webhook",
                       "rejected (404)",
                       "the webhook was deleted; make a new one and "
                       "gh secret set DISCORD_WEBHOOK_URL")
        return bad("discord webhook", f"HTTP {e.code}",
                   "the URL is wrong or the token was rotated")
    except Exception as e:  # noqa: BLE001
        return bad("discord webhook", str(e)[:80])


def check_paid_build() -> bool:
    """Is there an installer ready for itch.io?

    Worth knowing before Friday: a product with no build cannot be published,
    and the paid tier stays hidden until one exists.
    """
    try:
        import itch_publish as ip
    except ImportError:
        return bad("installer", "itch_publish.py could not be imported")

    stage = ROOT / "data" / "published.json"
    if not stage.exists():
        return ok("installer", "nothing built yet, which is expected "
                               "between releases")
    try:
        slug = json.loads(stage.read_text(encoding="utf-8"))["slug"]
    except (json.JSONDecodeError, KeyError, OSError):
        return ok("installer", "no readable build record")

    found = ip.find_installer(slug)
    if found:
        mb = found.stat().st_size / 1024 / 1024
        return ok("installer", f"{found.name} ({mb:.1f} MB)")
    return ok("installer",
              f"{slug} has no installer yet; Friday's run builds it")


ROOT = Path(__file__).resolve().parent


def main() -> int:
    log("checking every connection the weekly cycle needs")
    log("")

    results = {
        "groq": check_groq(),
        "itch user": check_itch_user(),
        "itch api": check_itch_api(),
        "itch session": check_itch_session(),
        "discord": check_discord(),
        "webhook": check_webhook(),
        "website": check_site(),
        "installer": check_paid_build(),
    }

    log("")
    failed = [k for k, v in results.items() if not v]
    if failed:
        log(f"{len(failed)} connection(s) need attention: "
            f"{', '.join(failed)}")
        return 1
    log("everything is connected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())