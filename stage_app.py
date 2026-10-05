"""Generate an app and stage it for verification. Publishes nothing.

Kept apart from the QA step on purpose: one model call budget is shared per
minute, so generating and verifying in the same minute starves the debugger.
The verifier runs an hour later on a fresh allowance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import make_app
    import buglog
    import sizeguard

    lessons = ""
    if make_app.LESSONS.exists():
        lessons = make_app.LESSONS.read_text(encoding="utf-8")
    lessons = (lessons + "\n\nPAST BUGS - do not repeat these:\n"
               + buglog.brief(14))[:6000]
    money = ""
    earn = make_app.DATA / "earnings.json"
    if earn.exists():
        money = earn.read_text(encoding="utf-8")[:2500]

    concept = make_app.pick_concept(money)
    make_app.log(f"concept: {concept['title']} ({concept['slug']})")

    for attempt in range(1, 4):
        html, brand, diffs, free_blurb, paid_blurb = make_app.build_html(
            concept, lessons, attempt=attempt)
        issues = make_app.html_looks_fine(html)
        for note in getattr(make_app.html_looks_fine, "notes", []):
            make_app.log(f"note: {note}")
        if issues:
            make_app.log(f"attempt {attempt} rejected: {issues}")
            continue
        ok, why = sizeguard.verdict(len(html))
        if not ok:
            make_app.log(f"attempt {attempt} {why}")
            continue
        if why:
            make_app.log(f"attempt {attempt} warning: {why}")
        make_app.log(f"attempt {attempt} ok ({len(html)} bytes, brand={brand!r})")

        basic_meta = {**concept, "brand": brand,
                      "slug": f"{concept['slug']}-basic"}
        basic_dir = make_app.write_app(basic_meta, html, tier="basic")
        full_dir = make_app.write_app({**concept, "brand": brand}, html, tier="full")

        # The verifier needs the candidate on disk plus enough context to judge
        # it. Nothing goes near site/, which is the published folder.
        stage = {
            "slug": concept["slug"],
            "brand": brand,
            "title": concept["title"],
            "tag": concept.get("tag", "productivity"),
            "differences": diffs,
            "free_blurb": free_blurb,
            "paid_blurb": paid_blurb,
            "candidate": str((basic_dir / "app" / "index.html").resolve()),
            "paid_dir": str(full_dir.resolve()),
        }
        out = make_app.DATA / "candidate.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stage, indent=1), encoding="utf-8")
        make_app.log(f"candidate staged for verification: {out}")
        return 0

    make_app.log("could not produce a candidate this run")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())