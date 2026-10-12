"""Post the monthly release to Discord as a real event, not just a message.

A message scrolls away. An event sits in the server with a live countdown and
shows up on the calendar, which is the difference between telling people a
date and having them turn up for it.

Nothing like this existed before: the rest of the codebase posts embeds and
reads replies, and this is the first thing to call the guild scheduled-events
endpoint. That has consequences worth writing down:

- **The bot needs the Create Events permission.** It is not in the default set,
  so a missing permission shows up as 403 with an audit-log reason, not as a
  silent no-op. The error body is logged for exactly that reason.
- **Events are keyed by an id, not a name.** Re-running this must not create a
  second event for the same release, so the id is stored in the update state
  and reused.
- **Never raises.** Same rule as the rest of discord_post: Discord being down
  must not stop a release.

    python update_discord.py            create or update the event
    python update_discord.py --delete   remove the event for this release
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import discord_post as dp
import update_state as us

# Where on the calendar the event points. Discord requires either an entity (a
# voice channel) or a plain location string; there is no venue for a software
# release, so it gets the public site.
LOCATION = "Online — https://tbougnar.github.io/Slingshot-Tools/"


def log(m: str) -> None:
    print(f"[event] {m}", flush=True)


def _iso(state: dict) -> str | None:
    raw = state.get("next_major")
    if not raw:
        return None
    try:
        # Discord accepts RFC 3339 and wants an explicit offset
        return datetime.fromisoformat(str(raw)).astimezone(
            timezone.utc).isoformat()
    except ValueError:
        return None


def description(state: dict) -> str:
    """The event body: what is coming, in the order people read it."""
    title = state.get("next_major_title") or "A new major update"
    notes = [str(n) for n in (state.get("next_major_notes") or []) if str(n)]
    out = [f"**{title}**", ""]
    for n in notes[:5]:
        out.append(f"- {n}")
    out += ["", f"Running {state.get('version')} today.",
            "Free, as always. Existing installs get a normal update."]
    return "\n".join(out)[:1000]


def existing(state: dict) -> str | None:
    return (state.get("discord_event_id") or "").strip() or None


def delete(state: dict) -> bool:
    """Remove the stored event, if there is one and if we can."""
    eid = existing(state)
    if not eid:
        log("no event id stored, so there is nothing to delete")
        return False
    if not dp.TOKEN or not dp.GUILD_ID:
        log("no bot token or guild, so the event cannot be deleted")
        return False
    st, data = dp._rest("DELETE", f"/guilds/{dp.GUILD_ID}"
                               f"/scheduled-events/{eid}")
    if st in (200, 204):
        log(f"deleted event {eid}")
        state["discord_event_id"] = None
        us.save(state)
        return True
    log(f"could not delete the event: HTTP {st} {str(data)[:140]}")
    return False


def upsert(state: dict) -> bool:
    """Create the event, or correct the one that already exists.

    A run that happens twice has to end with one event, not two, so the stored
    id is the thing that decides: same id means patch, no id means create.
    """
    when = _iso(state)
    if not when:
        log("no next_major date is set, so there is nothing to announce")
        return False
    if not dp.TOKEN or not dp.GUILD_ID:
        log("no bot token or guild, so the event cannot be created")
        log("the bot also needs the Create Events permission, which is not "
            "granted by default")
        return False

    title = str(state.get("next_major_title") or "Major update")
    name = f"{title}"[:100]
    body = {
        "name": name,
        "description": description(state),
        "scheduled_start_time": when,
        "scheduled_end_time": None,
        "privacy_level": 2,          # GUILD_ONLY
        "entity_type": 3,            # STAGE_INSTANCE is required with a location
        "location": LOCATION,
        "entity_metadata": {"location": LOCATION},
        "status": 1,                 # SCHEDULED
    }
    # a null end time is rejected, so give it two hours
    from datetime import timedelta
    end = datetime.fromisoformat(when) + timedelta(hours=2)
    body["scheduled_end_time"] = end.isoformat()

    eid = existing(state)
    if eid:
        st, data = dp._rest("PATCH", f"/guilds/{dp.GUILD_ID}"
                                  f"/scheduled-events/{eid}", body)
        if st in (200, 201):
            log(f"updated event {eid}: {name}")
            return True
        log(f"could not update event {eid}: HTTP {st} {str(data)[:160]}")
        # a stored id that no longer exists (deleted by hand) must not wedge
        # the release forever, so fall through and try to create a new one
        log("trying to create a fresh event instead")
        state["discord_event_id"] = None

    st, data = dp._rest("POST", f"/guilds/{dp.GUILD_ID}"
                             f"/scheduled-events", body)
    if st in (200, 201) and isinstance(data, dict) and data.get("id"):
        state["discord_event_id"] = str(data["id"])
        us.save(state)
        log(f"created event {data['id']} for {when}: {name}")
        return True

    log(f"discord refused the event: HTTP {st} {str(data)[:200]}")
    if st == 403:
        log("403 usually means the bot is missing the Create Events "
            "permission on this server")
    if st == 400:
        log("400 usually means scheduled_end_time or entity_type is wrong")
    return False


def announce(state: dict) -> bool:
    """Also drop a plain message in #announcements.

    An event only reaches people who browse the server; the announcement
    reaches everyone who reads the channel. Both, because they fail in
    different ways.
    """
    if not state.get("next_major_title"):
        log("no plan is set, so there is nothing to announce")
        return False
    title = state.get("next_major_title")
    notes = [str(n) for n in (state.get("next_major_notes") or []) if str(n)]
    lines = "\n".join(f"- {n}" for n in notes[:4])
    when = (state.get("next_major") or "")[:10]
    payload = dp.embed_message({
        "title": f"Coming {when}: {title}",
        "description": f"{lines}\n\nFree, as always. The event is on the "
                       f"calendar with a live countdown.",
        "url": "https://tbougnar.github.io/Slingshot-Tools/",
        "color": dp.BRAND,
        "footer": {"text": "slingshot.tools"},
    })
    ok = dp.post("announcements", payload)
    log("announced" if ok else "the announcement did not send")
    return ok


def main() -> int:
    state = us.load()
    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        return 0 if delete(state) else 1

    made = upsert(state)
    told = announce(state)
    if made or told:
        log("the release is on the calendar")
        return 0
    log("nothing was announced, but the release itself is unaffected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())