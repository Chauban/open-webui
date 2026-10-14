"""Assignment writing state and effective deadlines shared by writing entry points."""

import time
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from open_webui.models.education import Education


def load_submission_rounds_with_reviews(assignment, student_id: str, db=None):
    rounds = Education.get_submission_rounds(assignment.id, student_id, db=db)
    reviews = Education.get_submission_reviews_by_submission_ids([submission.id for submission in rounds], db=db)
    return rounds, reviews


def resolve_effective_due_at(
    assignment, rounds: list, reviews: dict, extension_due_at: Optional[int] = None
) -> Optional[int]:
    """Personal extensions take precedence over return and assignment deadlines."""
    if extension_due_at is not None:
        return extension_due_at
    for submission in rounds:
        review = reviews.get(submission.id)
        if review is None or review.review_status == 'pending':
            continue
        if review.review_status == 'returned' and review.resubmit_due_at:
            return review.resubmit_due_at
        break
    return assignment.due_at


def get_effective_due_at(assignment, student_id: str, db=None) -> Optional[int]:
    rounds, reviews = load_submission_rounds_with_reviews(assignment, student_id, db)
    extension = Education.get_assignment_extension(assignment.id, student_id, db=db)
    return resolve_effective_due_at(assignment, rounds, reviews, extension.due_at if extension else None)


def ensure_writing_session_writable(session, db: Optional[Session] = None) -> None:
    if session.scope != 'assignment':
        return
    assignment = Education.get_assignment_by_id(session.assignment_id, db=db)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Assignment not found')
    rounds, reviews = load_submission_rounds_with_reviews(assignment, session.owner_user_id, db)
    current = next((item for item in rounds if item.is_current == 1), None)
    review = reviews.get(current.id) if current else None
    if review is not None and review.review_status == 'reviewed':
        raise HTTPException(status.HTTP_409_CONFLICT, 'Submission has already been reviewed')
    extension = Education.get_assignment_extension(assignment.id, session.owner_user_id, db=db)
    due_at = resolve_effective_due_at(assignment, rounds, reviews, extension.due_at if extension else None)
    if due_at is not None and due_at <= int(time.time()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Assignment due time has passed')
