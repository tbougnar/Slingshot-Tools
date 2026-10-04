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

    exe = installer or (ROOT / "dist" / f"SlingshotTool-{slug}-Setup.exe")
    if not exe.exists():
        print(f"[paid] WARNING: no installer for {slug}; buyers would get nothing",
              flush=True)
        return False
    staged = dest / exe.name
    shutil.copy2(exe, staged)
    print(f"[paid] staged {slug}: {exe.name} ({staged.stat().st_size // 1024} KB)",
          flush=True)

    if upload(slug, staged, exe.name):
        return True
    print(f"[paid] WARNING: {slug} not published to the store", flush=True)
    return False


def upload(slug: str, path: Path, name: str = "") -> bool:
    """Put the installer in the Worker's private KV. Needs CF_API_TOKEN in CI."""
    if not (CF_TOKEN and NAMESPACE):
        print("[paid] no CF_API_TOKEN - skipping store upload", flush=True)
        return False
    url = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
           f"/storage/kv/namespaces/{NAMESPACE}/values/build:{slug}")
    req = urllib.request.Request(url, data=path.read_bytes(), method="PUT")
    req.add_header("Authorization", f"Bearer {CF_TOKEN}")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("X-Build-Name", name or path.name)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            ok = json.loads(r.read().decode()).get("success", False)
        print(f"[paid] published {slug} to the store: {ok}", flush=True)
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        print(f"[paid] store upload failed for {slug}: {str(e)[:120]}", flush=True)
        return False


def deliver(slug: str) -> Path | None:
    for p in sorted((PAID / slug).glob("*Setup.exe")) if (PAID / slug).exists() else []:
        return p
    return None