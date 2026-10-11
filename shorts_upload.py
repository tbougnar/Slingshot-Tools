"""Publish the rendered Short to YouTube, once the OAuth refresh token exists.

Google's upload endpoint wants a resumable upload, which is why this is not a
one-line request: a 30 second clip is small, but a failure halfway through
should not mean starting over.

Nothing here runs unless both YOUTUBE_CLIENT_ID and YOUTUBE_REFRESH_TOKEN are
present, so the pipeline is safe to have wired up before the credentials land.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK = 8 * 1024 * 1024


def log(m: str) -> None:
    print(f"[youtube] {m}", flush=True)


def configured() -> bool:
    return bool(os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
                and os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip())


def access_token() -> str:
    """Exchange the long-lived refresh token for a short-lived access token."""
    body = urllib.parse.urlencode({
        "client_id": os.environ["YOUTUBE_CLIENT_ID"].strip(),
        "client_secret": os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))["access_token"]


def privacy() -> str:
    """How visible the upload is, refusing anything unrecognised.

    The safe answer when the setting is missing is private, not public. A
    typo in a variable name would otherwise publish every video to the world
    without anyone noticing until it was up.
    """
    raw = (os.environ.get("YOUTUBE_PRIVACY", "") or "").strip().lower()
    if not raw:
        return "private"
    if raw in ("private", "unlisted", "public"):
        return raw
    log(f"YOUTUBE_PRIVACY is {raw!r}, which YouTube will reject; "
        f"falling back to private")
    log("valid values are private, unlisted, public")
    return "private"


def title(script: dict, name: str) -> str:
    """The one line YouTube shows in the feed, written to be clicked.

    This is the hook, not the product name. A Short's title is read on a phone
    before anybody has decided to watch, so it has to say the same promise the
    first spoken line makes; naming the app instead spends the one line on
    something the viewer has no reason to care about yet.
    """
    hook = str((script.get("beats") or {}).get("hook") or "").strip()
    raw = hook or str(script.get("blurb") or "").strip() or name

    # one line, no trailing punctuation, no shouting. A question mark or an
    # exclamation is left alone: on a hook they are the tone, and a title that
    # asks a question gets read as one.
    line = " ".join(raw.split()).strip(" .,;:-—")
    if line:
        line = line[0].upper() + line[1:]
    return (line or name)[:100]


def metadata(script: dict) -> dict:
    """Title, description and tags built from the same source as the video.

    Every link the brand has goes into the description, because the viewer's
    next move after watching is to open one of them and guessing which is the
    loss. All of it comes from links.py, so the description can never name a
    different address than the website does.
    """
    import links

    name = script.get("name") or "Slingshot Tool"
    price = script.get("price") or ""
    blurb = (script.get("blurb") or "").strip()

    desc = links.youtube_description(name, str(price), blurb)

    return {
        "snippet": {
            "title": title(script, name),
            "description": desc[:5000],
            "tags": ["shorts", "productivity", "desktop app",
                     "software", name.lower()][:500],
            "categoryId": "27",          # Science & Technology
            # Shorts are vertical and the recommendation engine treats them
            # differently; selfDeclaredMadeForKids stays false
            "selfDeclaredMadeForKids": False,
        },
        "status": {
            "privacyStatus": privacy(),
            "selfDeclaredMadeForAds": False,
        },
    }


def video_id(location: str, token: str, last_body: bytes) -> str:
    """The new video's id, taken from the upload's own final response.

    The last chunk of a resumable upload returns the whole video resource, so
    the id is already in hand. Re-reading the session URL afterwards does not
    work: YouTube closes it and answers 404, which is how an upload can
    succeed and still appear to have gone nowhere.
    """
    try:
        d = json.loads((last_body or b"").decode("utf-8", "replace"))
        if isinstance(d, dict) and d.get("id"):
            return str(d["id"])
    except (json.JSONDecodeError, ValueError):
        pass

    # fallback: ask the API for the most recent upload on the channel
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/videos"
            "?part=id,snippet&mine=true&maxResults=1",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=45) as r:
            items = json.loads(r.read().decode("utf-8")).get("items") or []
            if items:
                return str(items[0].get("id", ""))
    except Exception as e:  # noqa: BLE001
        log(f"could not confirm the video id: {str(e)[:70]}")
    return ""


def upload_thumbnail(video_id: str, token: str, image: Path) -> bool:
    """Set the thumbnail YouTube shows in the feed and on the watch page.

    Shorts do get a custom thumbnail, and the default first frame is whatever
    the renderer happened to produce first, which is usually a half faded
    headline. This replaces it with the composed card.
    """
    if not video_id or not image.exists():
        return False
    req = urllib.request.Request(
        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
        f"?videoId={urllib.parse.quote(video_id)}",
        data=image.read_bytes(), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "image/jpeg"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        return True
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:140]
        except Exception:  # noqa: BLE001
            pass
        log(f"thumbnail refused: HTTP {e.code} {detail}")
    except Exception as e:  # noqa: BLE001
        log(f"thumbnail failed: {str(e)[:70]}")
    return False


def main() -> int:
    # checked first, before anything else, so a dry run can never upload
    if (os.environ.get("DRY_RUN", "") or "").strip().lower() in ("1", "true",
                                                                "yes"):
        vpath = ROOT / "data" / "shorts_video.json"
        if vpath.exists():
            info = json.loads(vpath.read_text(encoding="utf-8"))
            log(f"dry run: {Path(info['file']).name} was rendered but not "
                f"uploaded")
        else:
            log("dry run: nothing was rendered, and nothing was uploaded")
        return 0

    if not configured():
        log("no YouTube credentials, so nothing was uploaded")
        log("set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and "
            "YOUTUBE_REFRESH_TOKEN to enable this")
        return 0

    vpath = ROOT / "data" / "shorts_video.json"
    if not vpath.exists():
        raise SystemExit("[youtube] run shorts_mux.py first")
    vinfo = json.loads(vpath.read_text(encoding="utf-8"))
    video = Path(vinfo["file"])
    if not video.exists():
        raise SystemExit(f"[youtube] {video} is missing")

    script = json.loads((ROOT / "data" / "shorts_script.json")
                        .read_text(encoding="utf-8"))

    token = access_token()
    log("token ok")
    meta = metadata(script)

    start = urllib.request.Request(
        f"{UPLOAD}?uploadType=resumable&part=snippet,status",
        data=json.dumps({"snippet": meta["snippet"],
                         "status": meta["status"]}).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(video.stat().st_size),
                 "X-Upload-Content-Type": "video/mp4"})
    with urllib.request.urlopen(start, timeout=60) as r:
        location = r.headers.get("Location") or r.headers.get("location")
    if not location:
        raise SystemExit("[youtube] no upload URL")

    total = video.stat().st_size
    sent = 0
    tail = b""
    with video.open("rb") as f:
        while sent < total:
            piece = f.read(CHUNK)
            if not piece:
                break
            end = sent + len(piece) - 1
            req = urllib.request.Request(
                location, data=piece, method="PUT",
                headers={"Content-Type": "video/mp4",
                         "Content-Range": f"bytes {sent}-{end}/{total}"})
            with urllib.request.urlopen(req, timeout=300) as r:
                tail = r.read()          # the last reply carries the resource
            sent += len(piece)
            log(f"  {sent * 100 / total:5.1f}%")

    vid = video_id(location, token, tail)
    url = f"https://youtu.be/{vid}" if vid else "(id not returned)"

    # The composed card, then the published URL. Visibility is not changed
    # here: status.privacyStatus goes out with the insert, which the
    # youtube.upload scope allows. videos.update would need a broader scope
    # and answers 403, so asking afterwards was a call that could never work.
    thumb = ROOT / "data" / "shorts_thumb.json"
    if vid and thumb.exists():
        try:
            info = json.loads(thumb.read_text(encoding="utf-8"))
            if upload_thumbnail(vid, token, Path(info["file"])):
                log("thumbnail set")
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    log(f"published {url} as {privacy()}")

    (ROOT / "data" / "shorts_published.json").write_text(
        json.dumps({"id": vid, "url": url,
                    "title": meta["snippet"]["title"],
                    "slug": vinfo.get("slug")}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())