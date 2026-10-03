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
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAID = ROOT / "paid"
PAID.mkdir(exist_ok=True)

WORKER = os.environ.get("PAY_WORKER") or "https://slingshot-pay.bougnartaha2.workers.dev"
CF_TOKEN = os.environ.get("CF_API_TOKEN") or ""
NAMESPACE = os.environ.get("CF_BUILDS_NAMESPACE") or "3d55488f7d384ce3ad51c0ba34afeade"
ACCOUNT = os.environ.get("CF_ACCOUNT_ID") or ""


def stage(app_dir: Path, slug: str) -> bool:
    """Copy a full build into paid/<slug>, zip it, and upload to the Worker."""
    dest = PAID / slug
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(app_dir, dest)

    files = sorted(p for p in dest.rglob("*") if p.is_file())
    manifest = {
        "slug": slug,
        "files": [{"path": str(p.relative_to(dest)).replace("\\", "/"),
                   "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in files],
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    zpath = PAID / f"{slug}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(dest).as_posix())
    size = zpath.stat().st_size
    print(f"[paid] staged {slug}: {len(files)} file(s), {size // 1024} KB", flush=True)

    if upload(slug, zpath):
        return True
    print(f"[paid] WARNING: {slug} built but not published to the store; "
          f"buyers would get nothing", flush=True)
    return False


def upload(slug: str, zpath: Path) -> bool:
    """Put the zip in the Worker's private KV. Needs CF_API_TOKEN in CI."""
    if not (CF_TOKEN and NAMESPACE):
        print("[paid] no CF_API_TOKEN - skipping store upload", flush=True)
        return False
    url = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
           f"/storage/kv/namespaces/{NAMESPACE}/values/build:{slug}")
    req = urllib.request.Request(url, data=zpath.read_bytes(), method="PUT")
    req.add_header("Authorization", f"Bearer {CF_TOKEN}")
    req.add_header("Content-Type", "application/zip")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            ok = json.loads(r.read().decode()).get("success", False)
        print(f"[paid] published {slug} to the store: {ok}", flush=True)
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        print(f"[paid] store upload failed for {slug}: {str(e)[:120]}", flush=True)
        return False


def key_for(slug: str) -> str:
    """Kept only for the pre-existing paid folders from earlier runs."""
    return ""


def deliver(slug: str) -> Path | None:
    z = PAID / f"{slug}.zip"
    return z if z.exists() else None