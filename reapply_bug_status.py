"""Re-apply the status and verification notes that live outside the recorder.

record_audit_bugs.py is idempotent by symptom, so re-running it after a reset
restores the defects and their recorded evidence but not the two that were
promoted or annotated by hand afterwards. Keeping that in a script rather than
in a terminal command means it survives another reset.
"""
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0]
                if "\\" in __file__ else __file__.rsplit("/", 1)[0])

import bugtrack

UPDATES = [
    ("the paid publish outcome was recorded and then thrown away",
     dict(
         status="VERIFIED_FIXED",
         fix="The record step now has id: paid, writes the outcome to "
             "GITHUB_STEP_SUMMARY, and a final gate reads it. The gate runs "
             "after the free edition has been deployed, so one dead "
             "destination does not cost the customer the release that worked, "
             "but the job fails with a plain message. ALLOW_FREE_ONLY accepts "
             "the partial release deliberately.",
         regression_test="parsed friday-verify.yml; steps.paid exists and the "
                        "gate is the final step",
         verification="Run 38416539839 executed the gate and reported the paid "
                      "edition was not published, instead of reporting "
                      "success. That is the first evidence the gate runs.")),

    ("a debug backup file is committed to the published site",
     dict(
         status="VERIFIED_FIXED",
         fix="qa_loop writes per-round backups to data/qa_backups/ instead of "
             "beside the app, and check_exposure refuses to pass if any .bak, "
             ".trial.html, .py or .tmp reaches site/.",
         regression_test="planted index.r4.bak in the published tree; "
                         "check_exposure reported it",
         verification="check_exposure ok after removal; index.r3.bak "
                       "untracked and deleted")),
]


def main() -> int:
    bugs = {b["symptom"]: b for b in bugtrack.load()}
    changed = 0
    for symptom, fields in UPDATES:
        entry = bugs.get(symptom)
        if entry is None:
            print(f"MISSING  {symptom[:60]}")
            continue
        if entry.get("status") == fields.get("status") and \
                entry.get("verification") == fields.get("verification"):
            continue
        bugtrack.update(entry["id"], **fields)
        changed += 1
        print(f"updated {entry['id']}  {symptom[:56]}")
    print()
    print(f"{changed} updated")
    print(bugtrack.stats()["by_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())