"""Verify a fresh YouTube OAuth pair and store it as GitHub Actions secrets.

The Shorts upload cannot be fixed from the repository: Google mints the refresh
token only after a person presses Allow. Run shorts_auth.py first, put the
client id, client secret and new refresh token in the gitignored .env, then run
this script. It proves the three values work together and then encrypts them
with the repository's Actions public key, so no secret ever appears in a log or
in a chat message.

    python set_youtube_secrets.py
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REPO = "/repos/tbougnar/Slingshot-Tools"
NAMES = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def log(msg: str) -> None:
    print(f"[yt-secrets] {msg}", flush=True)


def local_values() -> dict[str, str]:
    """Process environment wins; .env supplies anything not exported."""
    out: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for name in NAMES:
        if os.environ.get(name):
            out[name] = os.environ[name].strip()
    return out


def token() -> str:
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, timeout=30, cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit("[yt-secrets] no GitHub credential is available")
    values = {}
    for line in p.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            values[k] = v
    value = values.get("password", "").strip()
    if not value:
        raise SystemExit("[yt-secrets] no GitHub token in the credential manager")
    return value


def api(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "slingshot-youtube-secret-setter",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request("https://api.github.com" + path, data=data,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw.strip() else raw
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def prove(cid: str, csec: str, refresh: str) -> None:
    body = urllib.parse.urlencode({
        "client_id": cid, "client_secret": csec, "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token",
                                 data=body,
                                 headers={"Content-Type":
                                          "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        if not d.get("access_token"):
            raise RuntimeError("Google returned no access token")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"[yt-secrets] Google refused the pair (HTTP {e.code}): "
                         f"{raw}. Nothing was stored.") from None
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[yt-secrets] the pair could not be checked: {e}. "
                         "Nothing was stored.") from None
    log("Google accepted the pair; the Shorts workflow will be able to upload")


def store(name: str, value: str, key: dict) -> bool:
    from nacl.public import PublicKey, SealedBox
    public = PublicKey(base64.b64decode(key["key"]))
    sealed = SealedBox(public).encrypt(value.encode("utf-8"))
    status, result = api("PUT", f"{REPO}/actions/secrets/{name}", {
        "encrypted_value": base64.b64encode(sealed).decode("ascii"),
        "key_id": key["key_id"],
    })
    if status not in (200, 201, 204):
        print(f"[yt-secrets] FAILED to store {name}: HTTP {status} "
              f"{str(result)[:200]}")
        return False
    log(f"stored {name}")
    return True


def main() -> int:
    values = local_values()
    missing = [name for name in NAMES if not values.get(name)]
    if missing:
        log("missing from the environment and .env: " + ", ".join(missing))
        log("put the client id, secret and new refresh token in .env first, "
            "or export them before running this script")
        return 1

    prove(values["YOUTUBE_CLIENT_ID"], values["YOUTUBE_CLIENT_SECRET"],
          values["YOUTUBE_REFRESH_TOKEN"])

    status, key = api("GET", f"{REPO}/actions/secrets/public-key")
    if status != 200 or not isinstance(key, dict) or not key.get("key"):
        print(f"[yt-secrets] could not read the Actions public key: HTTP "
              f"{status} {str(key)[:200]}")
        return 1
    ok = True
    for name in NAMES:
        ok = store(name, values[name], key) and ok
    if not ok:
        return 1
    log("done; rerun the connection check to confirm YouTube")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
