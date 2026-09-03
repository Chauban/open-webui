from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.education import (
    Education,
    StudentProfileAssignmentItem,
    StudentProfileIndexFormula,
    StudentProfilePagination,
    StudentProfilePortfolioSummary,
    StudentProfileResponse,
    TeacherStudentProfileResponse,
)
from open_webui.services.education.profile import (
    PROFILE_METRIC_VERSION,
    _profile_index_formula,
)
from open_webui.services.education.profile_aggregates import (
    build_student_profile_aggregate,
)
from open_webui.services.education.profile_evidence import canonical_json_hash


async def build_student_profile(
    student,
    student_id: str,
    classrooms: list,
    assignments: list,
    db: Session,
    *,
    start_at: Optional[int] = None,
    end_at: Optional[int] = None,
    assignment_id: Optional[str] = None,
    round_no: Optional[int] = None,
    metric_version: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    teacher_notes: Optional[list] = None,
) -> StudentProfileResponse | TeacherStudentProfileResponse:
    assignment_by_id = {assignment.id: assignment for assignment in assignments}
    if assignment_id is not None:
        assignment_by_id = {
            key: value
            for key, value in assignment_by_id.items()
            if key == assignment_id
        }
    scoped_assignments = list(assignment_by_id.values())
    assignment_ids = list(assignment_by_id)
    available_metric_versions = Education.get_profile_metric_versions(
        student_id, assignment_ids=assignment_ids, db=db
    )
    if metric_version is not None and metric_version not in available_metric_versions:
        raise ValueError("Unknown or unavailable profile metric version")
    active_metric_version = (
        Education.get_active_profile_metric_version(db=db) or PROFILE_METRIC_VERSION
    )
    selected_metric_version = metric_version or active_metric_version
    if (
        selected_metric_version == active_metric_version
        and selected_metric_version not in available_metric_versions
    ):
        available_metric_versions = [
            selected_metric_version,
            *available_metric_versions,
        ]

    unfiltered_scope = all(
        value is None for value in (start_at, end_at, assignment_id, round_no)
    )
    if not unfiltered_scope and selected_metric_version != active_metric_version:
        raise ValueError(
            "Historical metric versions only support their materialized default scope"
        )
    scope_kind = (
        "classroom"
        if len(classrooms) == 1
        and all(
            assignment.classroom_id == classrooms[0].id
            for assignment in scoped_assignments
        )
        else "global"
    )
    scope_id = classrooms[0].id if scope_kind == "classroom" else "*"
    aggregate_record = (
        Education.get_latest_student_profile_aggregate_projection(
            student_id=student_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            metric_version=selected_metric_version,
            db=db,
        )
        if unfiltered_scope
        else None
    )
    if aggregate_record is not None:
        actual_aggregate_hash = canonical_json_hash(
            aggregate_record.aggregate_json.model_dump(mode="json")
        )
        if actual_aggregate_hash != aggregate_record.output_hash:
            raise ValueError("Profile aggregate hash verification failed")
        aggregate = aggregate_record.aggregate_json
        if aggregate.assignment_ids != sorted(assignment_ids):
            raise ValueError("Student profile aggregate scope is stale")
        total = aggregate_record.projection_count
        page_projections = Education.get_profile_metric_projections(
            student_id,
            selected_metric_version,
            assignment_ids=assignment_ids,
            limit=limit,
            offset=offset,
            db=db,
        )
        projections_to_verify = page_projections
    else:
        aggregate, _, _, all_projections = build_student_profile_aggregate(
            student_id=student_id,
            assignment_ids=assignment_ids,
            metric_version=selected_metric_version,
            start_at=start_at,
            end_at=end_at,
            round_no=round_no,
            db=db,
        )
        if unfiltered_scope and all_projections:
            raise ValueError("Student profile aggregate is not materialized")
        total = len(all_projections)
        page_projections = all_projections[offset : offset + limit]
        projections_to_verify = all_projections

    for projection in projections_to_verify:
        actual_output_hash = canonical_json_hash(
            projection.projection_json.model_dump(mode="json")
        )
        if actual_output_hash != projection.output_hash:
            raise ValueError("Profile projection hash verification failed")
    excluded_snapshot_count = sum(
        Education.count_profile_metric_projections(
            student_id,
            version,
            assignment_ids=assignment_ids,
            start_at=start_at,
            end_at=end_at,
            round_no=round_no,
            db=db,
        )
        for version in available_metric_versions
        if version != selected_metric_version
    )
    current_submissions = {
        submission.assignment_id: submission
        for submission in Education.get_current_submissions_by_student(
            student_id, assignment_ids, db=db
        )
    }
    reviews = Education.get_submission_reviews_by_submission_ids(
        [submission.id for submission in current_submissions.values()], db=db
    )

    timeline = [
        projection.projection_json.point.model_copy(
            update={
                "is_current": current_submissions.get(projection.assignment_id)
                is not None
                and current_submissions[projection.assignment_id].id
                == projection.submission_id
            }
        )
        for projection in page_projections
    ]
    page_round_progress = [
        projection.projection_json.round_progress
        for projection in page_projections
        if projection.projection_json.round_progress is not None
    ]

    assignment_items = []
    submitted_count = reviewed_count = returned_count = 0
    portfolio_scores = []
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
            portfolio_scores.append(review.score / assignment.score_max * 100)
        assignment_items.append(
            StudentProfileAssignmentItem(
                assignment=assignment,
                submission_id=current.id,
                submitted_at=current.submitted_at,
                round_no=current.round_no,
                review_status=review_status,
                score=(
                    review.score if review_status == "reviewed" and review else None
                ),
            )
        )

    response_data = dict(
        metric_version=selected_metric_version,
        active_metric_version=active_metric_version,
        insight_version=aggregate.insight_version,
        aggregate_materialized=aggregate_record is not None,
        aggregate_revision=(
            aggregate_record.aggregate_revision
            if aggregate_record is not None
            else None
        ),
        available_metric_versions=available_metric_versions,
        excluded_snapshot_count=excluded_snapshot_count,
        student_id=student_id,
        student_name=student.name if student else student_id,
        student_email=student.email if student else None,
        classrooms=classrooms,
        portfolio_summary=StudentProfilePortfolioSummary(
            assignment_count=len(scoped_assignments),
            submitted_count=submitted_count,
            unsubmitted_count=len(scoped_assignments) - submitted_count,
            reviewed_count=reviewed_count,
            returned_count=returned_count,
            average_score_percent=(
                round(sum(portfolio_scores) / len(portfolio_scores), 1)
                if portfolio_scores
                else None
            ),
        ),
        filtered_summary=aggregate.filtered_summary,
        filters_applied=any(
            value is not None
            for value in (
                start_at,
                end_at,
                assignment_id,
                round_no,
                metric_version,
            )
        )
        or offset > 0,
        timeline_pagination=StudentProfilePagination(
            total=total,
            limit=limit,
            offset=offset,
        ),
        assignments=assignment_items,
        timeline=timeline,
        cross_assignment_timeline=aggregate.cross_assignment_timeline,
        round_progress=page_round_progress,
        trends=aggregate.trends,
        ai_help_type_distribution=aggregate.ai_help_type_distribution,
        ai_help_type_shift=aggregate.ai_help_type_shift,
        reflection_quality=aggregate.reflection_quality,
        index_formula=StudentProfileIndexFormula.model_validate(
            Education.get_profile_formula_config(selected_metric_version, db=db)
            or _profile_index_formula().model_dump(mode="json")
        ),
        insights=aggregate.insights,
        data_completeness=aggregate.data_completeness,
        growth_goals=Education.get_student_growth_goals(
            student_id,
            classroom_ids=[classroom.id for classroom in classrooms],
            limit=100,
            db=db,
        ),
    )
    if teacher_notes is not None:
        return TeacherStudentProfileResponse(
            **response_data,
            teacher_notes=teacher_notes,
        )
    return StudentProfileResponse(**response_data)
