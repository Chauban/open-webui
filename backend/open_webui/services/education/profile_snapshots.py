import difflib
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.education import (
    Education,
    StudentProfileAssignmentItem,
    StudentProfileDataCompleteness,
    StudentProfileHelpTypeShift,
    StudentProfileReflectionQuality,
    StudentProfileResponse,
    StudentProfileRoundProgress,
    StudentProfileSnapshotPayload,
    StudentProfileTimelinePoint,
)
from open_webui.services.education.analysis import build_version_diffs
from open_webui.services.education.profile import (
    PROFILE_METRIC_VERSION,
    _PROFILE_TREND_KEYS,
    _build_profile_insights,
    _build_trend,
    _compute_collaboration_index,
    _compute_deadline_window_ratio,
    _compute_end_loaded_ratio,
    _compute_process_index,
    _compute_revision_depth,
    _estimate_active_writing_seconds,
    _profile_index_formula,
    _score_reflection,
    _slice_round_versions,
    _summarize_help_types,
)


def refresh_student_profile_snapshot(
    submission,
    assignment,
    db: Session,
    analysis_payload: Optional[dict] = None,
):
    """Create the immutable metric point for one submission, or update its grading fields.

    This function runs only on submission/review writes. Profile reads never reconstruct
    metrics from versions, operations, provenance, or analysis history.
    """
    session = Education.get_writing_session_by_id(submission.writing_session_id, db=db)
    if session is None:
        raise ValueError("Writing session is required for a profile snapshot")

    analysis = analysis_payload
    if analysis is None:
        stored_analysis = Education.get_analysis_result(
            session.id,
            "submission_analysis",
            submission_id=submission.id,
            db=db,
        )
        analysis = stored_analysis.payload_json if stored_analysis else None
    summary = (analysis or {}).get("summary") or {}

    rounds = sorted(
        Education.get_submission_rounds(submission.assignment_id, submission.student_id, db=db),
        key=lambda item: item.round_no,
    )
    previous_submission = next((item for item in rounds if item.round_no == submission.round_no - 1), None)
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    previous_review = (
        Education.get_submission_review_by_submission_id(previous_submission.id, db=db) if previous_submission else None
    )
    reflection = Education.get_micro_reflection_by_id(submission.micro_reflection_id, db=db)

    all_versions = Education.get_versions(session.id, db=db)
    final_version = next((item for item in all_versions if item.id == submission.final_version_id), None)
    previous_final_version = (
        next(
            (item for item in all_versions if item.id == previous_submission.final_version_id),
            None,
        )
        if previous_submission
        else None
    )
    round_versions = _slice_round_versions(
        all_versions,
        previous_submission.final_version_id if previous_submission else None,
        submission.final_version_id,
    )
    version_data_complete = final_version is not None and bool(round_versions)
    window_start_at = round_versions[0].created_at if round_versions else submission.submitted_at
    previous_final_text = (previous_final_version.note_snapshot_text or "") if previous_final_version else ""
    final_text = (final_version.note_snapshot_text or "") if final_version else ""
    version_diffs = build_version_diffs(round_versions, previous_final_text) if version_data_complete else []
    inserted_chars = sum(diff.get("inserted_length", 0) for diff in version_diffs) if version_data_complete else 0
    revised_chars = sum(diff.get("deleted_length", 0) for diff in version_diffs) if version_data_complete else 0
    revision_depth = _compute_revision_depth(revised_chars, inserted_chars) if version_data_complete else None

    operations = [
        operation
        for operation in Education.get_editor_operations(session.id, db=db)
        if window_start_at <= operation.created_at <= submission.submitted_at
    ]
    editor_operations_complete = bool(operations)
    active_writing_seconds = (
        _estimate_active_writing_seconds([operation.created_at for operation in operations])
        if editor_operations_complete
        else None
    )
    writing_span_seconds = max(submission.submitted_at - window_start_at, 0) if version_data_complete else 0
    round_due_at = (
        previous_review.resubmit_due_at
        if previous_review and previous_review.resubmit_due_at is not None
        else assignment.due_at
    )
    end_loaded_ratio = (
        _compute_end_loaded_ratio(version_diffs, window_start_at, submission.submitted_at)
        if version_data_complete
        else None
    )
    deadline_window_ratio = (
        _compute_deadline_window_ratio(version_diffs, round_due_at) if version_data_complete else None
    )

    source_tracking_complete = bool(summary.get("source_tracking_complete", False))
    ai_ratio = (
        round(
            float(summary.get("ai_inserted_ratio", 0)) + float(summary.get("ai_pasted_ratio", 0)),
            4,
        )
        if source_tracking_complete
        else None
    )
    typed_ratio = float(summary.get("typed_ratio", 0)) if source_tracking_complete else None
    unknown_ratio = float(summary.get("unknown_ratio", 0)) if source_tracking_complete else None
    digestion_ratio = int(summary.get("average_rewrite_ratio", 0)) if source_tracking_complete else None
    prompt_count = int(summary.get("prompt_count", 0)) if analysis else None
    reflection_score = _score_reflection(reflection.reflection_json if reflection else None)
    ai_used = reflection.ai_used if reflection else False
    scoring_comparable = bool(review and review.score is not None and review.rubric_scores is not None)

    point = StudentProfileTimelinePoint(
        submission_id=submission.id,
        assignment_id=assignment.id,
        assignment_title=assignment.title,
        round_no=submission.round_no,
        is_current=submission.is_current == 1,
        submitted_at=submission.submitted_at,
        data_completeness=StudentProfileDataCompleteness(
            version_data_complete=version_data_complete,
            editor_operations_complete=editor_operations_complete,
            source_tracking_complete=source_tracking_complete,
            scoring_comparable=scoring_comparable,
        ),
        total_chars=len(final_text) if version_data_complete else int(summary.get("total_chars", 0)),
        score=review.score if scoring_comparable else None,
        score_max=assignment.score_max,
        normalized_score=(round(review.score / assignment.score_max * 100, 2) if scoring_comparable else None),
        rubric=review.rubric_scores if scoring_comparable else None,
        review_status=review.review_status if review else "pending",
        inserted_chars=inserted_chars,
        revised_chars=revised_chars,
        revision_depth=revision_depth,
        writing_span_seconds=writing_span_seconds,
        active_writing_seconds=active_writing_seconds,
        lead_time_seconds=(
            round_due_at - window_start_at if round_due_at is not None and version_data_complete else None
        ),
        end_loaded_ratio=end_loaded_ratio,
        deadline_window_ratio=deadline_window_ratio,
        process_index=(
            _compute_process_index(revision_depth, writing_span_seconds, end_loaded_ratio)
            if version_data_complete
            else None
        ),
        typed_ratio=typed_ratio,
        ai_ratio=ai_ratio,
        unknown_ratio=unknown_ratio,
        prompt_count=prompt_count,
        digestion_ratio=digestion_ratio,
        reflection_char_count=reflection_score["char_count"],
        reflection_quality=reflection_score["score"],
        ai_help_types=list(reflection.ai_help_types) if reflection else [],
        collaboration_index=_compute_collaboration_index(
            digestion_ratio,
            prompt_count,
            reflection_score["score"],
            ai_ratio,
            ai_used,
        ),
        burst_count=int(summary.get("burst_count", 0)) if analysis else 0,
        suspected_unmarked_import_count=(
            int(summary.get("suspected_unmarked_import_count", 0)) if source_tracking_complete else 0
        ),
    )

    round_progress = None
    if previous_submission and final_version and previous_final_version:
        similarity = difflib.SequenceMatcher(None, previous_final_text, final_text).ratio()
        round_progress = StudentProfileRoundProgress(
            assignment_id=assignment.id,
            assignment_title=assignment.title,
            from_round=previous_submission.round_no,
            to_round=submission.round_no,
            char_delta=len(final_text) - len(previous_final_text),
            revision_ratio=int(round((1 - similarity) * 100)),
            score_delta=(
                review.score - previous_review.score
                if scoring_comparable and previous_review and previous_review.score is not None
                else None
            ),
            turnaround_seconds=(
                submission.submitted_at - previous_review.reviewed_at
                if previous_review and previous_review.reviewed_at
                else None
            ),
        )

    payload = StudentProfileSnapshotPayload(
        metric_version=PROFILE_METRIC_VERSION,
        point=point,
        round_progress=round_progress,
    )
    return Education.upsert_student_profile_snapshot(submission, PROFILE_METRIC_VERSION, payload, db=db)


async def build_student_profile(
    student,
    student_id: str,
    classroom,
    assignments: list,
    db: Session,
    *,
    start_at: Optional[int] = None,
    end_at: Optional[int] = None,
    assignment_id: Optional[str] = None,
    round_no: Optional[int] = None,
) -> StudentProfileResponse:
    assignment_by_id = {assignment.id: assignment for assignment in assignments}
    if assignment_id is not None:
        assignment_by_id = {key: value for key, value in assignment_by_id.items() if key == assignment_id}
    scoped_assignments = list(assignment_by_id.values())
    snapshots = Education.get_student_profile_snapshots(
        student_id,
        PROFILE_METRIC_VERSION,
        assignment_ids=list(assignment_by_id),
        start_at=start_at,
        end_at=end_at,
        round_no=round_no,
        db=db,
    )
    current_submissions = {
        submission.assignment_id: submission
        for submission in Education.get_current_submissions_by_student(
            student_id, list(assignment_by_id), db=db
        )
    }
    reviews = Education.get_submission_reviews_by_submission_ids(
        [submission.id for submission in current_submissions.values()], db=db
    )

    timeline = [
        snapshot.snapshot_json.point.model_copy(
            update={
                "is_current": current_submissions.get(snapshot.assignment_id) is not None
                and current_submissions[snapshot.assignment_id].id == snapshot.submission_id
            }
        )
        for snapshot in snapshots
    ]
    timeline.sort(key=lambda point: (point.submitted_at, point.round_no))
    round_progress = [
        snapshot.snapshot_json.round_progress
        for snapshot in snapshots
        if snapshot.snapshot_json.round_progress is not None
    ]

    trends = {}
    for key in _PROFILE_TREND_KEYS:
        trend = _build_trend(key, [getattr(point, key) for point in timeline])
        if trend is not None:
            trends[key] = trend

    half = len(timeline) // 2
    early_help = _summarize_help_types(timeline[:half] if half else [])
    recent_help = _summarize_help_types(timeline[half:] if half else timeline)
    help_shift = StudentProfileHelpTypeShift(
        early=early_help,
        recent=recent_help,
        refining_ratio_delta=(
            round(recent_help.refining_ratio - early_help.refining_ratio, 4)
            if early_help.refining_ratio is not None and recent_help.refining_ratio is not None
            else None
        ),
    )

    help_distribution = {}
    for point in timeline:
        for help_type in point.ai_help_types:
            help_distribution[help_type] = help_distribution.get(help_type, 0) + 1
    reflection_scores = [point.reflection_quality for point in timeline]
    reflection_quality = StudentProfileReflectionQuality(
        count=len(reflection_scores),
        average_score=(int(round(sum(reflection_scores) / len(reflection_scores))) if reflection_scores else None),
        average_chars=(
            int(round(sum(point.reflection_char_count for point in timeline) / len(timeline))) if timeline else None
        ),
    )

    assignment_items = []
    submitted_count = reviewed_count = returned_count = 0
    normalized_scores = []
    for assignment in scoped_assignments:
        current = current_submissions.get(assignment.id)
        if current is None:
            assignment_items.append(StudentProfileAssignmentItem(assignment=assignment))
            continue
        review = reviews.get(current.id)
        review_status = review.review_status if review else "pending"
        submitted_count += 1
        reviewed_count += int(review_status == "reviewed")
        returned_count += int(review_status == "returned")
        if review_status == "reviewed" and review and review.score is not None:
            normalized_scores.append(review.score / assignment.score_max * 100)
        assignment_items.append(
            StudentProfileAssignmentItem(
                assignment=assignment,
                submission_id=current.id,
                submitted_at=current.submitted_at,
                round_no=current.round_no,
                review_status=review_status,
                score=review.score if review_status == "reviewed" and review else None,
            )
        )

    return StudentProfileResponse(
        metric_version=PROFILE_METRIC_VERSION,
        student_id=student_id,
        student_name=student.name if student else student_id,
        student_email=student.email if student else None,
        classroom=classroom,
        assignment_count=len(scoped_assignments),
        submitted_count=submitted_count,
        unsubmitted_count=len(scoped_assignments) - submitted_count,
        reviewed_count=reviewed_count,
        returned_count=returned_count,
        average_score_percent=(
            round(sum(normalized_scores) / len(normalized_scores), 1) if normalized_scores else None
        ),
        assignments=assignment_items,
        timeline=timeline,
        round_progress=round_progress,
        trends=list(trends.values()),
        ai_help_type_distribution=help_distribution,
        ai_help_type_shift=help_shift,
        reflection_quality=reflection_quality,
        index_formula=_profile_index_formula(),
        insights=_build_profile_insights(timeline, round_progress, trends, help_shift, reflection_quality),
    )
