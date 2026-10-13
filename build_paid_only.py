"""Build the paid Windows installer, and publish it to itch.io.

This used to check for an installer that somebody else had to build, and when
there wasn't one it printed six lines telling a human what to do. That is why
nothing has ever been sellable: the automation was built to check, not to act,
and the gap between those two is exactly where the business died.

It does the whole path now:

1. compile the paid app to a .exe with PyInstaller
2. wrap that in an NSIS installer
3. hand both to itch_publish.py, which creates or finds the itch.io project,
   uploads the file, confirms the page answers, and only then flips the site
   to published

The order is deliberate and it is the same order itch_publish.py uses: nothing
is advertised until something can be bought. A buy button that leads nowhere
is worse than no button.

    python build_paid_only.py            build it
    python build_paid_only.py --publish  build it and put it on sale
    python build_paid_only.py --check    report, change nothing
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import auditlog

sys.path.insert(0, str(Path(__file__).resolve().parent))


def log(m: str) -> None:
    print(f"[installer] {m}", flush=True)


# An installer that does not actually contain the app. NSIS happily produces a
# 110 KB stub when the compiled exe was missing, and dist/ has a dozen of them
# from earlier runs. Accepting one of those would mean uploading an installer
# that installs nothing, which is worse than having none.
MIN_INSTALLER_BYTES = 2 * 1024 * 1024


def plausible(path: Path) -> bool:
    """Big enough to contain a compiled app, and actually a PE file."""
    try:
        if path.stat().st_size < MIN_INSTALLER_BYTES:
            return False
        with path.open("rb") as fh:
            return fh.read(2) == b"MZ"
    except OSError:
        return False


def find_existing(paid: Path) -> Path | None:
    """An installer that already exists and is worth keeping.

    A stub is reported rather than silently skipped, because a run of these is
    the clearest evidence that something upstream is building empty installers.
    """
    candidates = sorted(paid.rglob("*Setup.exe"))
    for exe in sorted(Path("dist").glob("*-Setup.exe")) \
            if Path("dist").exists() else []:
        candidates.append(exe)

    stubs = []
    for c in candidates:
        if plausible(c):
            return c
        stubs.append(c)
    if stubs:
        for s in stubs[:3]:
            log(f"ignoring {s.name}: {s.stat().st_size / 1024:.0f} KB is a "
                f"stub with no app in it")
    return None


def _title_from_build(paid: Path) -> str:
    """The product's own name, from the concept.json that shipped with it."""
    try:
        meta = json.loads((paid / "concept.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(meta, dict):
        return str(meta.get("title") or meta.get("slug") or "").strip()
    return ""


def build(stage: dict, paid: Path) -> Path | None:
    """The .exe then the installer, or nothing."""
    # The title comes from the stage file when there is one, and from the
    # build itself otherwise. paid/<slug>/concept.json is written by
    # write_app and is the only description of the product that certainly
    # exists, because it travelled with the artifact. Reading stage["slug"]
    # unconditionally raised KeyError whenever the stage file was absent, which
    # is every installer job since that file was untracked.
    title = str(stage.get("title") or "").strip()
    if not title:
        title = _title_from_build(paid)
    if not title:
        log(f"no title for {paid.name}, and concept.json does not give one")
        return None

    try:
        import build_exe as be
    except Exception as e:  # noqa: BLE001
        log(f"pyinstaller is not available: {e}")
        return None

    # build_app wants <app_dir>/app/index.html, which is exactly what
    # write_app produced for the paid tier. An absolute path matters here:
    # PyInstaller resolves --add-data relative to --specpath when given one,
    # so a relative path silently becomes dist/_pyi/<path>.
    app_dir = paid.resolve()
    log(f"compiling the app: {app_dir}")
    try:
        built = be.build_app(app_dir, title)
    except Exception as e:  # noqa: BLE001
        log(f"pyinstaller failed: {str(e)[:90]}")
        return None
    if not built or not Path(built).exists():
        log("pyinstaller produced nothing")
        return None
    log(f"app compiled to {built}")

    try:
        import build_installer_app as bi
    except Exception as e:  # noqa: BLE001
        log(f"the installer builder is not available: {e}")
        return None

    log("wrapping it in an NSIS installer")
    try:
        setup = bi.build_installer(Path(built), title, app_dir)
    except Exception as e:  # noqa: BLE001
        log(f"NSIS failed: {str(e)[:90]}")
        return None

    if not setup or not Path(setup).exists():
        log("NSIS produced nothing")
        return None
    setup = Path(setup).resolve()
    if not plausible(setup):
        log(f"NSIS produced {setup.name} at "
            f"{setup.stat().st_size / 1024:.0f} KB, which contains no app. "
            f"The compiled exe was probably missing.")
        return None
    size = setup.stat().st_size / 1024 / 1024
    log(f"installer built: {setup.name} ({size:.1f} MB)")

    # keep it beside the paid app, which is where itch_publish.py looks first
    paid.mkdir(parents=True, exist_ok=True)
    kept = paid / setup.name
    if kept.resolve() != setup:
        shutil.copy2(setup, kept)
        log(f"kept at {kept.relative_to(Path.cwd())}")
    return kept


def publish(stage: dict, slug: str = "") -> bool:
    """Hand the finished installer to itch.io and flip the site on."""
    import itch_publish

    # The slug is the directory that was actually built, passed in by the
    # caller. Reading stage["slug"] here raised KeyError whenever the stage
    # file was absent, after the installer had already been built.
    slug = slug or str(stage.get("slug") or "")
    if not slug:
        log("no slug to publish under")
        return False
    log(f"publishing {slug} to itch.io")
    try:
        # itch_publish.main reads data/published.json and takes no arguments
        return itch_publish.publish(
            slug,
            stage.get("title") or slug,
            float(stage.get("price") or 0),
            stage.get("version") or "",
        )
    except Exception as e:  # noqa: BLE001
        log(f"itch.io could not be reached: {str(e)[:90]}")
        return False


def main() -> int:
    import make_app

    args = [a.strip().lower() for a in sys.argv[1:]]
    stage_file = make_app.DATA / "published.json"

    # What was actually built is in paid/, which arrived as an artifact. The
    # slug in published.json is only a hint, and it used to be the sole
    # authority: the file was untracked, so a fresh checkout had none of it,
    # this returned 0, and the step reported a successful build while
    # producing no installer at all. Nothing about that return value was true.
    builds = sorted(p for p in make_app.PAID_DIR.glob("*")
                    if p.is_dir() and (p / "app" / "index.html").exists()) \
        if make_app.PAID_DIR.is_dir() else []

    if not builds:
        log("no paid build was uploaded, so there is nothing to package")
        auditlog.blocked("build-paid", reason="paid/ held no app to build from",
                         evidence={"paid_dir": str(make_app.PAID_DIR)})
        return 1

    stage = {}
    if stage_file.exists():
        try:
            stage = json.loads(stage_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            stage = {}
    else:
        log("published.json is not present, which is expected: the artifact "
            "is the authority on what was built")
    named = str(stage.get("slug") or "")
    paid = make_app.PAID_DIR / named if named else None
    if paid is not None and paid.exists() and \
            (paid / "app" / "index.html").exists():
        pass
    elif len(builds) == 1:
        # Either published.json is absent or it names something that did not
        # arrive. A single real build is unambiguous, so it is used and the
        # mismatch is said out loud rather than being a silent substitution.
        paid = builds[0]
        log(f"published.json says {named or '(nothing)'}, which is not the "
            f"build that was uploaded; using {paid.name}")
        auditlog.retried("build-paid", job=paid.name,
                         reason="the recorded slug was absent or did not match "
                                "the uploaded build",
                         evidence={"named": named or "", "found": paid.name})
    else:
        log(f"{len(builds)} paid builds were uploaded, so none can be chosen "
            f"safely: {', '.join(p.name for p in builds)}")
        auditlog.blocked("build-paid",
                         reason="more than one paid build to choose from",
                         evidence={"builds": [p.name for p in builds]})
        return 1

    if "--check" in args:
        found = find_existing(paid)
        log(f"an installer exists: {found.name}" if found
            else "no installer exists, so nothing can be sold")
        return 0 if found else 1

    setup = find_existing(paid)
    if setup:
        log(f"an installer already exists: {setup.name}")
    else:
        log("there is no installer, so building one")
        setup = build(stage, paid)

    if not setup:
        log("no installer was produced, so there is nothing to sell")
        log("the free edition is unaffected and still ships")
        return 1

    size = setup.stat().st_size / 1024 / 1024
    log(f"ready for itch.io: {setup} ({size:.1f} MB)")

    if "--publish" in args:
        if publish(stage, paid.name):
            log("it is on sale")
            return 0
        log("the upload did not finish; the paid tier stays hidden")
        return 1

    log("built but not published. Add --publish to sell it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())