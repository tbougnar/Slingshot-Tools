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


def metadata(script: dict) -> dict:
    """Title, description and tags built from the same source as the video."""
    name = script.get("name") or "Slingshot Tool"
    price = script.get("price") or ""
    link = os.environ.get("SITE_URL", "").strip() or \
        "https://tbougnar.github.io/Slingshot-Tools/"
    blurb = (script.get("blurb") or "").strip()

    desc = "\n\n".join(x for x in [
        blurb,
        f"Price: {price}" if price else "",
        "Full details and the download link are on the site.",
        link,
        "#shorts",
    ] if x)

    return {
        "snippet": {
            "title": f"{name} in 30 seconds"[:100],
            "description": desc[:5000],
            "tags": ["shorts", "productivity", "desktop app",
                     "software", name.lower()][:500],
            "categoryId": "27",          # Science & Technology
            # Shorts are vertical and the recommendation engine treats them
            # differently; selfDeclaredMadeForKids stays false
            "selfDeclaredMadeForKids": False,
        },
        "status": {
            "privacyStatus": (os.environ.get("YOUTUBE_PRIVACY",
                                             "public").strip()),
            "selfDeclaredMadeForAds": False,
        },
    }


def final_id(location: str, token: str) -> str:
    """Ask for the finished resource so the id is certain, not assumed."""
    req = urllib.request.Request(
        location, method="GET",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8")).get("id", "")
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
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
                r.read()
            sent += len(piece)
            log(f"  {sent * 100 / total:5.1f}%")

    vid = final_id(location, token)
    url = f"https://youtu.be/{vid}" if vid else "(id not returned)"
    log(f"published {url}")

    (ROOT / "data" / "shorts_published.json").write_text(
        json.dumps({"id": vid, "url": url,
                    "title": meta["snippet"]["title"],
                    "slug": vinfo.get("slug")}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())