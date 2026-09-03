import argparse
import time
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.internal.db import SessionLocal
from open_webui.models.education import (
    Education,
    ProfileProjectionRun,
)
from open_webui.services.education.profile import PROFILE_METRIC_VERSION
from open_webui.services.education.profile_aggregates import (
    refresh_student_profile_aggregates,
)
from open_webui.services.education.profile_evidence import (
    canonical_json_hash,
    ensure_current_profile_algorithm_release,
    profile_algorithm_code_checksum,
    profile_code_commit_sha,
    project_profile_evidence,
)


def recompute_profile_projections(
    db: Session,
    *,
    requested_by: str,
    student_id: Optional[str] = None,
    assignment_id: Optional[str] = None,
    activate: bool = False,
    batch_size: int = 200,
) -> str:
    """Explicitly materialize the current algorithm from immutable evidence.

    Reads never call this function. A failed run leaves the previous active release
    untouched and records exact evidence failures for an explicit retry.
    """

    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    if activate and (student_id is not None or assignment_id is not None):
        raise ValueError("Only a full projection run can activate an algorithm release")
    ensure_current_profile_algorithm_release(db, created_by=requested_by)
    expected_count = Education.count_latest_profile_evidence_snapshots(
        student_id=student_id,
        assignment_id=assignment_id,
        db=db,
    )

    now = int(time.time())
    scope = {
        "student_id": student_id,
        "assignment_id": assignment_id,
        "batch_size": batch_size,
    }
    run = ProfileProjectionRun(
        id=str(uuid.uuid4()),
        metric_version=PROFILE_METRIC_VERSION,
        scope_json=scope,
        expected_count=expected_count,
        succeeded_count=0,
        failed_count=0,
        error_json=[],
        status="running",
        requested_by=requested_by,
        code_commit_sha=profile_code_commit_sha(),
        config_hash=canonical_json_hash(
            {
                "metric_version": PROFILE_METRIC_VERSION,
                "algorithm_checksum": profile_algorithm_code_checksum(),
            }
        ),
        started_at=now,
        finished_at=None,
        created_at=now,
    )
    db.add(run)
    db.commit()

    failures = []
    succeeded = 0
    affected_student_ids = set()
    after_id = None
    while True:
        batch = Education.get_latest_profile_evidence_batch(
            student_id=student_id,
            assignment_id=assignment_id,
            after_id=after_id,
            limit=batch_size,
            db=db,
        )
        if not batch:
            break
        for evidence in batch:
            try:
                with db.begin_nested():
                    review = Education.get_latest_submission_review_event(
                        evidence.submission_id,
                        evidence_snapshot_id=evidence.id,
                        db=db,
                    )
                    project_profile_evidence(
                        evidence,
                        review,
                        db,
                        run_id=run.id,
                        commit=False,
                    )
                    affected_student_ids.add(evidence.student_id)
                succeeded += 1
            except Exception as exc:  # run audit must retain per-item failure
                failures.append(
                    {
                        "evidence_snapshot_id": evidence.id,
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:500],
                    }
                )
        db.commit()
        after_id = batch[-1].id

    for affected_student_id in sorted(affected_student_ids):
        try:
            with db.begin_nested():
                refresh_student_profile_aggregates(
                    affected_student_id,
                    PROFILE_METRIC_VERSION,
                    db,
                    run_id=run.id,
                    commit=False,
                )
        except Exception as exc:
            failures.append(
                {
                    "student_id": affected_student_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:500],
                }
            )
    db.commit()

    run = db.get(ProfileProjectionRun, run.id)
    run.succeeded_count = succeeded
    run.failed_count = len(failures)
    run.error_json = failures
    run.status = "completed" if not failures else "failed"
    run.finished_at = int(time.time())
    db.commit()
    if activate:
        if failures or succeeded != expected_count:
            raise RuntimeError(
                "Projection coverage is incomplete; release was not activated"
            )
        Education.activate_profile_algorithm_release(PROFILE_METRIC_VERSION, db=db)
        db.commit()
    return run.id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly rebuild writing growth profile projections"
    )
    parser.add_argument("--requested-by", required=True)
    parser.add_argument("--student-id")
    parser.add_argument("--assignment-id")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        run_id = recompute_profile_projections(
            db,
            requested_by=args.requested_by,
            student_id=args.student_id,
            assignment_id=args.assignment_id,
            activate=args.activate,
            batch_size=args.batch_size,
        )
    print(run_id)


if __name__ == "__main__":
    main()
