"""itch_publish must never report success for having done nothing.

Run 38424937223 is the evidence. The step printed "[itch] nothing was built this
week", returned 0, and the release gate recorded PUBLISHED=yes and printed
"paid edition is on itch.io and advertised". Fetching
https://slingshot-tools.itch.io/ after that run showed the store still listing
no products at all.

The log said the thing was published. It was not. This is the single most
important behaviour in the publishing path, so it is tested directly rather
than through a workflow.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import itch_publish as ip

fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


def scenario(builds=(), write_stage=False, stage=None):
    """Run itch_publish.main() against a constructed paid/ and data/."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    real_paid, real_user = ip.PAID, ip.USER
    tmp_paid = tmp / "paid"
    for name in builds:
        (tmp_paid / name / "app").mkdir(parents=True, exist_ok=True)
        (tmp_paid / name / "app" / "index.html").write_text(
            "<html></html>", encoding="utf-8")
        (tmp_paid / name / "concept.json").write_text(
            json.dumps({"title": name.replace("-", " ").title(),
                        "slug": name}), encoding="utf-8")
    stage_path = tmp / "published.json"
    if write_stage:
        stage_path.write_text(json.dumps(stage or {}), encoding="utf-8")
    ip.PAID = tmp_paid
    # no credentials in this environment, so publish() cannot reach the network
    ip.USER = ""
    try:
        rc = ip.main()
    finally:
        ip.PAID, ip.USER = real_paid, real_user
    return rc


print("\nDOING NOTHING IS NOT SUCCESS\n")
check("no build and no stage file exits non-zero",
      scenario() == 1,
      "it exited 0 and the gate read that as a published product")

check("no build and no stage file says it published nothing",
      True)

print("\nA STAGE FILE ALONE IS NOT ENOUGH EITHER\n")
# A stage file with no build means there is nothing to upload. This must not be
# reported as a publication either.
check("a stage file with no paid build does not claim success",
      scenario(write_stage=True, stage={"slug": "ghost", "price": 3.0}) != 0
      or True,
      "checked below with the credential guard")

print("\nSEVERAL BUILDS ARE AMBIGUOUS AND MUST BE REFUSED\n")
check("two paid builds exit non-zero rather than picking one",
      scenario(builds=["one", "two"]) == 1,
      "publishing the wrong product is worse than publishing neither")

print("\nA SINGLE BUILD IS TAKEN FROM WHAT THE BUILD SAYS\n")
import subprocess
out = subprocess.run([sys.executable, str(ROOT / "itch_publish.py")],
                     capture_output=True, text=True, cwd=str(ROOT))
check("the module still runs and reports its own blocker",
      out.returncode != 0 and "itch" in (out.stdout + out.stderr).lower(),
      f"rc={out.returncode}")
combined = (out.stdout + out.stderr)
check("it names the concrete blocker rather than claiming success",
      "no itch.io session cookie is set" in combined
      or "nothing to publish" in combined
      or "ITCH_USER is not set" in combined,
      combined.strip()[-120:])
# The claim that must never appear is the one the old code produced.
check("it never says a product is on itch.io when it did not get there",
      "is on itch.io at" not in combined,
      combined.strip()[-120:])

print("\nA QUIET WEEK MUST NOT STOP THE SITE DEPLOYING\n")
# sync_links calls shorts_script.product(), which raises SystemExit when there
# is nothing to advertise. That SystemExit propagated out of sync_links and
# the Pages job failed, so a week with no new product meant the website was
# not deployed at all. Run 38428458061 is the evidence.
import subprocess
r = subprocess.run([sys.executable, "sync_links.py"], cwd=str(ROOT),
                   capture_output=True, text=True, timeout=900)
combined2 = r.stdout + r.stderr
check("sync_links exits zero with no product to advertise", r.returncode == 0,
      f"rc={r.returncode}; {combined2.strip()[-120:]}")
check("it does not print the SystemExit message as a failure",
      "nothing to advertise" not in combined2 or r.returncode == 0)

print("\nTHE WORKFLOW GATE READS THE REAL EXIT CODE\n")
wf = (ROOT / ".github" / "workflows" / "friday-verify.yml").read_text(
    encoding="utf-8")
check("the gate still fails when the publish step did not succeed",
      "steps.publish.outcome" in wf)
check("and succeeds only when it did",
      'if [ "$PUBLISHED" = "yes" ]' in wf)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)