"""Rebuild and re-upload the paid edition of a product that already exists.

The pipeline generates one new product per run, so a product whose build is
missing has no way back: its paid source lives in paid/, which is gitignored
and never committed, and nothing regenerates a product that already exists.

This closes that gap from the private artifact the verifier uploads on every
release. The repository is public and the paid source is deliberately never
committed, so an earlier design that rebuilt from a committed free edition
could not work in a paid-only catalog: there is no free edition to copy from.
The Windows workflow restores the paid-build artifact before calling this
script; the script only rebuilds from that real source and never invents one.

    python rebuild_paid.py chess-clock --no-upload
    # in GitHub Actions, with source_run_id pointing at the verify run

It refuses to touch a product whose paid source is absent or whose price is
outside the floor and ceiling, and it says plainly when the store refuses the
upload rather than claiming the product is back on sale.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PAID = ROOT / "paid"
CATALOG = ROOT / "site" / "apps.json"

PRICE_FLOOR = float(__import__("os").environ.get("PRICE_FLOOR", "1.00"))
PRICE_CEILING = float(__import__("os").environ.get("PRICE_CEILING", "10.00"))

def log(msg: str) -> None:
    print(f"[rebuild] {msg}", flush=True)


def entry_for(slug: str) -> dict:
    try:
        apps = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[rebuild] cannot read the catalogue: {e}")
    if not isinstance(apps, list):
        raise SystemExit("[rebuild] the catalogue is not a list")
    for e in apps:
        if e.get("tier") == "full" and (e.get("base_slug") or e.get("slug")) == slug:
            return e
    raise SystemExit(f"[rebuild] {slug} is not a paid product in the catalogue")


def project_for(entry: dict, slug: str) -> str:
    """The butler project for this product, never the old shared page.

    A rebuild must replace this product's build on this product's page. The
    catalog's per-product itch_url is the authority; if it still points at the
    shared project, the page has to be corrected before anything is uploaded.
    """
    url = str(entry.get("itch_url") or "").strip()
    parts = [p for p in urlparse(url).path.split("/") if p]
    project = parts[0].lower() if parts else ""
    if project in ("", "slingshot-tools") or project != slug.lower():
        raise SystemExit(
            f"[rebuild] {slug} has no own itch.io project in the catalogue "
            f"(found {url or '(nothing)'}). Create "
            f"https://slingshot-tools.itch.io/{slug} and run "
            f"python set_itch_url.py {slug} "
            f"https://slingshot-tools.itch.io/{slug} first")
    return project


def reconstruct(slug: str, concept: dict) -> Path:
    """Use the paid source restored from the verifier's private artifact.

    The artifact is the only copy of the exact file customers bought. Rebuilding
    it from a free edition would change the product, and with a paid-only
    catalog there is no free edition anyway. Nothing is guessed here.
    """
    out = PAID / slug
    src = out / "app" / "index.html"
    if not src.exists():
        raise SystemExit(
            f"[rebuild] no paid source for {slug} at "
            f"{src.relative_to(ROOT)}. Download the verifier's paid-build "
            f"artifact (source_run_id) into paid/ first; the paid source is "
            f"never committed to this public repository.")

    # Keep the real source unchanged. Only fill in metadata the artifact may
    # not carry, so the catalog's title and price stay the authority.
    meta_path = out / "concept.json"
    if not meta_path.exists():
        meta = {**concept, "slug": slug, "tier": "full", "base_slug": slug}
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    upload = "--no-upload" not in sys.argv
    if len(args) != 1:
        print(__doc__)
        print("usage: python rebuild_paid.py <slug> [--no-upload]")
        return 1
    slug = args[0].strip()

    concept = entry_for(slug)
    price = float(concept.get("price") or 0)
    if not (PRICE_FLOOR <= price <= PRICE_CEILING):
        raise SystemExit(
            f"[rebuild] {slug} is priced at ${price:.2f}, outside the "
            f"${PRICE_FLOOR:.2f}-${PRICE_CEILING:.2f} rule. Refusing.")

    out = reconstruct(slug, concept)
    log(f"{slug} reconstructed at {out.relative_to(ROOT)} "
        f"({len((out / 'app' / 'index.html').read_text(encoding='utf-8'))} bytes)")
    log(f"title: {concept.get('title')!r}  price: ${price:.2f}")

    if not upload:
        log("not uploading, because --no-upload was given")
        return 0

    # Build the installer. build_paid_only.build() is the path the Friday
    # installer job uses, and it is the one that has been exercised: it
    # compiles the app with PyInstaller, wraps it in an NSIS installer and
    # keeps the result beside the paid app, which is where itch_publish looks
    # first.
    #
    # This used to call build_exe.main(), which does not exist. build_exe
    # exposes make_ico() and build_app() and nothing else, so the call raised
    # AttributeError after the product had already been reconstructed, and
    # the tool that exists to bring a dead product back on sale died with a
    # traceback instead of saying the installer did not build.
    import build_paid_only

    built = build_paid_only.build({}, out)
    if not built:
        log("the installer did not build, so this product stays off sale")
        return 1
    installer = Path(built)

    # Prove the file being offered is this product's, before anything is sent
    # to a customer. A shared dist/ folder holds other products' installers.
    import itch_publish as ip
    found = ip.find_installer(slug, title=concept.get("title"))
    if not found:
        log(f"no installer for {slug} could be identified after building, so "
            "nothing is uploaded. dist/ holds other products' installers and "
            "one of them will not be passed off as this one.")
        return 1
    # The installer is named after the product's title, not its slug, so
    # "password-manager" is "Offline password manager-Setup.exe". Comparing
    # the slug against the file name therefore refused the correct installer
    # for every product, and no product could ever be brought back on sale.
    # The name is compared the way itch_publish and build_paid_only compare
    # it, and the title is checked as well as the slug.
    def _norm(text: str) -> str:
        return "".join(ch for ch in str(text or "").lower()
                       if ch.isalnum())

    stem = _norm(installer.name)
    if _norm(slug) not in stem and _norm(concept.get("title")) not in stem:
        log(f"refusing: the installer found is {installer.name}, which is not "
            f"{slug}'s. Uploading it would sell one tool as another.")
        return 1
    log(f"verified the installer is this product's: {installer.name}")

    # butler wants the project's slug, not its URL. The target is
    # user/project:channel, and a URL in the project part is not a project.
    project = project_for(concept, slug)
    if not ip.upload(installer, slug, "", project=project):
        log("the upload did not finish, so this product stays off sale")
        return 1
    log(f"{slug} is uploaded. itch_publish advertises it only once its own "
        f"installer is listed on the project page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())