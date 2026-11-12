"""Submission timing comes only from the evidence frozen for that submission."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from open_webui.models.education import Education, ProfileEvidencePayload, SubmissionTiming


def build_submission_timing(evidence: ProfileEvidencePayload) -> SubmissionTiming:
    due_at = evidence.assignment.effective_due_at
    return SubmissionTiming(
        effective_due_at=due_at,
        is_late=due_at is not None and evidence.submitted_at >= due_at,
    )


def get_submission_timing(submission_id: str, db: Session) -> SubmissionTiming:
    snapshot = Education.get_latest_profile_evidence_snapshot(submission_id, db=db)
    if snapshot is None:
        raise HTTPException(409, 'Submission evidence snapshot is missing')
    return build_submission_timing(snapshot.evidence_json)
