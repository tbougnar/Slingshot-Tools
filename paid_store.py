"""Stage paid products for delivery after payment.

The public site/ folder must never contain the paid app or installer, so paid
builds are written to paid/<slug>/ and only released to a buyer once PayPal
confirms the order. Nothing here is a download link: it is a staging folder.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import paypal

ROOT = Path(__file__).resolve().parent
PAID = ROOT / "paid"
PAID.mkdir(exist_ok=True)


def stage(app_dir: Path, slug: str) -> bool:
    """Copy a full build into paid/<slug> and record a manifest. Returns True
    when the paid tier is ready for sale."""
    dest = PAID / slug
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(app_dir, dest)

    files = sorted(p for p in dest.rglob("*") if p.is_file())
    manifest = {
        "slug": slug,
        "title": (json.loads((app_dir / "app.json").read_text(encoding="utf-8-sig"))
                  .get("title", slug) if (app_dir / "app.json").exists() else slug),
        "files": [{"path": str(p.relative_to(dest)).replace("\\", "/"),
                   "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in files],
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    # A zip makes delivery a single file the buyer can save anywhere.
    zpath = PAID / f"{slug}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(dest).as_posix())
    print(f"[paid] staged {slug}: {len(files)} file(s), "
          f"{zpath.stat().st_size // 1024} KB zip -> {zpath}", flush=True)
    return True


def deliver(slug: str) -> Path | None:
    """Return the paid zip for a slug, only after the caller has confirmed
    payment. Nothing in here grants access on its own."""
    z = PAID / f"{slug}.zip"
    return z if z.exists() else None


def key_for(slug: str) -> str:
    """A key for this product, reusing an existing one if already issued."""
    existing = paypal.public_key(slug)
    if existing and paypal.verify_key(existing, slug):
        return existing
    return paypal.new_key(slug)


def issue(slug: str, order_id: str, email: str = "") -> str:
    """Confirm the order is paid, then mint and record the key."""
    if not paypal.order_paid(order_id):
        raise RuntimeError(f"order {order_id} is not paid")
    key = key_for(slug)
    paypal.save_key(slug, key, order_id, email)
    return key


if __name__ == "__main__":
    for d in sorted(PAID.glob("*")):
        print(d.name, "->", "dir" if d.is_dir() else f"{d.stat().st_size // 1024} KB")