"""Stage the paid build and publish it to the Cloudflare Worker store.

The public site never contains a paid edition. The paid zip is uploaded to the
Worker's private KV and handed to a buyer only after PayPal confirms payment.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request

import build_exe
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAID = ROOT / "paid"
PAID.mkdir(exist_ok=True)

WORKER = os.environ.get("PAY_WORKER") or "https://slingshot-pay.bougnartaha2.workers.dev"
CF_TOKEN = os.environ.get("CF_API_TOKEN") or ""
NAMESPACE = os.environ.get("CF_BUILDS_NAMESPACE") or "3d55488f7d384ce3ad51c0ba34afeade"
ACCOUNT = os.environ.get("CF_ACCOUNT_ID") or ""


def stage(app_dir: Path, slug: str, installer: Path | None = None) -> bool:
    """Publish the Windows installer for a paid build.

    The buyer gets exactly one thing: the real .exe installer. The app HTML and
    icon stay on the server, so there is no loose file to hand around and no
    way to run the paid app without installing it.
    """
    dest = PAID / slug
    # write_app already writes the paid build straight into paid/<slug>, so in
    # the normal path source and destination are the same directory and there
    # is nothing to copy.
    same = dest.exists() and app_dir.resolve() == dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if same:
        for p in list(dest.rglob("*Setup.exe")):
            p.unlink()
    else:
        for p in app_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(app_dir)
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out)

    # Build a real standalone exe so the customer needs no Python or pywebview.
    title = dest.name
    exe = None
    try:
        exe = build_exe.build_exe(dest, title)
    except Exception as e:  # noqa: BLE001
        print(f"[paid] standalone build failed for {slug}: {str(e)[:120]}", flush=True)
    if not exe:
        print(f"[paid] WARNING: no exe for {slug}; buyers would get nothing",
              flush=True)
        return False
    # The standalone exe is ~28 MB, above the 25 MB limit of the store, so it
    # ships as one zip that contains exactly one file: the exe.
    print(f"[paid] staged {slug}: {exe.name} "
          f"({exe.stat().st_size // 1024 // 1024} MB standalone exe)", flush=True)

    if upload(slug, exe, exe.name):
        return True
    print(f"[paid] WARNING: {slug} not published to the store", flush=True)
    return False


CHUNK = 14 * 1024 * 1024  # KV rejects any single value above 25 MB


def upload(slug: str, path: Path, name: str = "") -> bool:
    """Store the installer in the Worker's private KV, split into chunks.

    The store rejects a single value above 25 MB and a standalone exe is larger
    than that, so the file is cut into pieces. The Worker joins them back
    together before replying, so the customer still gets one complete exe.
    """
    if not (CF_TOKEN and NAMESPACE):
        print("[paid] no CF_API_TOKEN - skipping store upload", flush=True)
        return False
    url = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
           f"/storage/kv/namespaces/{NAMESPACE}/values/build:{slug}")
    blob = path.read_bytes()
    parts = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)] or [b""]

    # clear any earlier copy so stale chunks cannot be joined in
    for stale in range(1, len(parts) + 4):
        _put(f"{url}:{stale}", b"")

    for n, part in enumerate(parts, start=1):
        if not _put(f"{url}:{n}", part):
            print(f"[paid] store upload failed for {slug} chunk {n}", flush=True)
            return False
    print(f"[paid] published {slug}: {len(parts)} chunk(s), "
          f"{len(blob) // 1024 // 1024} MB", flush=True)
    return True


def _put(url: str, data: bytes) -> bool:
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {CF_TOKEN}")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return bool(json.loads(r.read().decode()).get("success", False))
    except Exception as e:  # noqa: BLE001
        print(f"[paid] put failed: {str(e)[:110]}", flush=True)
        return False


def deliver(slug: str) -> Path | None:
    for p in sorted((PAID / slug).glob("*Setup.exe")) if (PAID / slug).exists() else []:
        return p
    return None