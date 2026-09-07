from typing import Literal, Optional

from sqlalchemy.orm import Session

from open_webui.models.education import (
    Education,
    StudentProfileAggregatePayload,
    StudentProfileCompletenessSummary,
    StudentProfileFilteredSummary,
    StudentProfileHelpTypeShift,
    StudentProfileReflectionQuality,
)
from open_webui.services.education.profile import (
    PROFILE_INSIGHT_VERSION,
    _PROFILE_TREND_KEYS,
    _build_profile_insights,
    _build_trend,
    _summarize_help_types,
)
from open_webui.services.education.profile_evidence import canonical_json_hash


def build_student_profile_aggregate(
    *,
    student_id: str,
    assignment_ids: list[str],
    metric_version: str,
    db: Session,
    start_at: Optional[int] = None,
    end_at: Optional[int] = None,
    round_no: Optional[int] = None,
) -> tuple[StudentProfileAggregatePayload, str, str, list]:
    projections = Education.get_profile_metric_projections(
        student_id,
        metric_version,
        assignment_ids=assignment_ids,
        start_at=start_at,
        end_at=end_at,
        round_no=round_no,
        limit=None,
        db=db,
    )
    for projection in projections:
        if (
            canonical_json_hash(projection.projection_json.model_dump(mode="json"))
            != projection.output_hash
        ):
            raise ValueError("Profile projection hash verification failed")
    current_submissions = {
        submission.assignment_id: submission
        for submission in Education.get_current_submissions_by_student(
            student_id, assignment_ids, db=db
        )
    }
    timeline = [
        projection.projection_json.point.model_copy(
            update={
                "is_current": current_submissions.get(projection.assignment_id)
                is not None
                and current_submissions[projection.assignment_id].id
                == projection.submission_id
            }
        )
        for projection in projections
    ]
    cross_assignment_timeline = [point for point in timeline if point.is_current]
    round_progress = [
        projection.projection_json.round_progress
        for projection in projections
        if projection.projection_json.round_progress is not None
    ]

    trends = {}
    for key in _PROFILE_TREND_KEYS:
        trend = _build_trend(
            key,
            [getattr(point, key) for point in cross_assignment_timeline],
        )
        if trend is not None:
            trends[key] = trend

    half = len(cross_assignment_timeline) // 2
    early_help = _summarize_help_types(cross_assignment_timeline[:half] if half else [])
    recent_help = _summarize_help_types(
        cross_assignment_timeline[half:] if half else cross_assignment_timeline
    )
    help_shift = StudentProfileHelpTypeShift(
        early=early_help,
        recent=recent_help,
        refining_ratio_delta=(
            round(recent_help.refining_ratio - early_help.refining_ratio, 4)
            if early_help.refining_ratio is not None
            and recent_help.refining_ratio is not None
            else None
        ),
    )

    help_distribution = {}
    for point in cross_assignment_timeline:
        for help_type in point.ai_help_types:
            help_distribution[help_type] = help_distribution.get(help_type, 0) + 1
    # 只统计教师已批改的提交;未批改的反思还没有质量分,不能当 0 拉低平均。
    reflection_scores = [
        point.reflection_quality
        for point in cross_assignment_timeline
        if point.reflection_quality is not None
    ]
    reflection_quality = StudentProfileReflectionQuality(
        count=len(reflection_scores),
        average_score=(
            int(round(sum(reflection_scores) / len(reflection_scores)))
            if reflection_scores
            else None
        ),
    )

    def status_count(field: str, expected: str) -> int:
        return sum(
            getattr(point.data_completeness, field) == expected for point in timeline
        )

    applicable_statuses = []
    for point in timeline:
        applicable_statuses.extend(
            [
                point.data_completeness.version_data,
                point.data_completeness.editor_operations,
                point.data_completeness.source_tracking,
            ]
        )
        if point.data_completeness.scoring not in {
            "pending",
            "not_applicable",
        }:
            applicable_statuses.append(point.data_completeness.scoring)

    completeness = StudentProfileCompletenessSummary(
        point_count=len(timeline),
        version_complete_count=status_count("version_data", "complete"),
        version_missing_count=status_count("version_data", "missing"),
        editor_operations_complete_count=status_count("editor_operations", "complete"),
        editor_operations_missing_count=status_count("editor_operations", "missing"),
        source_tracking_complete_count=status_count("source_tracking", "complete"),
        source_tracking_missing_count=status_count("source_tracking", "missing"),
        scoring_comparable_count=status_count("scoring", "complete"),
        scoring_pending_count=status_count("scoring", "pending"),
        scoring_not_applicable_count=status_count("scoring", "not_applicable"),
        scoring_missing_count=status_count("scoring", "missing"),
        overall_ratio=(
            round(
                sum(status == "complete" for status in applicable_statuses)
                / len(applicable_statuses),
                4,
            )
            if applicable_statuses
            else None
        ),
    )
    filtered_scores = [
        point.normalized_score
        for point in timeline
        if point.normalized_score is not None
    ]
    filtered_summary = StudentProfileFilteredSummary(
        point_count=len(timeline),
        assignment_count=len({point.assignment_id for point in timeline}),
        reviewed_point_count=sum(
            point.normalized_score is not None for point in timeline
        ),
        average_score_percent=(
            round(sum(filtered_scores) / len(filtered_scores), 1)
            if filtered_scores
            else None
        ),
    )
    insight_version = (
        Education.get_profile_insight_version(metric_version, db=db)
        or PROFILE_INSIGHT_VERSION
    )
    payload = StudentProfileAggregatePayload(
        metric_version=metric_version,
        insight_version=insight_version,
        assignment_ids=sorted(assignment_ids),
        projection_count=len(projections),
        cross_assignment_timeline=cross_assignment_timeline,
        round_progress=round_progress,
        trends=list(trends.values()),
        ai_help_type_distribution=help_distribution,
        ai_help_type_shift=help_shift,
        reflection_quality=reflection_quality,
        insights=_build_profile_insights(
            cross_assignment_timeline,
            round_progress,
            trends,
            help_shift,
            reflection_quality,
        ),
        data_completeness=completeness,
        filtered_summary=filtered_summary,
    )
    input_hash = canonical_json_hash(
        {
            "metric_version": metric_version,
            "insight_version": insight_version,
            "assignment_ids": sorted(assignment_ids),
            "projections": [
                {
                    "id": projection.id,
                    "output_hash": projection.output_hash,
                }
                for projection in projections
            ],
            "current_submissions": sorted(
                submission.id for submission in current_submissions.values()
            ),
        }
    )
    output_hash = canonical_json_hash(payload.model_dump(mode="json"))
    return payload, input_hash, output_hash, projections


def materialize_student_profile_aggregate(
    *,
    student_id: str,
    assignment_ids: list[str],
    scope_kind: Literal["global", "classroom"],
    scope_id: str,
    metric_version: str,
    db: Session,
    run_id: Optional[str] = None,
    commit: bool = False,
):
    payload, input_hash, output_hash, _ = build_student_profile_aggregate(
        student_id=student_id,
        assignment_ids=assignment_ids,
        metric_version=metric_version,
        db=db,
    )
    return Education.insert_student_profile_aggregate_projection(
        student_id=student_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        metric_version=metric_version,
        input_hash=input_hash,
        output_hash=output_hash,
        payload=payload,
        run_id=run_id,
        commit=commit,
        db=db,
    )


def refresh_student_profile_aggregates(
    student_id: str,
    metric_version: str,
    db: Session,
    *,
    run_id: Optional[str] = None,
    commit: bool = False,
) -> None:
    assignments = Education.get_assignments_by_student(student_id, db=db)
    materialize_student_profile_aggregate(
        student_id=student_id,
        assignment_ids=[assignment.id for assignment in assignments],
        scope_kind="global",
        scope_id="*",
        metric_version=metric_version,
        run_id=run_id,
        commit=False,
        db=db,
    )
    classroom_ids = {
        assignment.classroom_id
        for assignment in assignments
        if assignment.classroom_id is not None
    }
    for classroom_id in classroom_ids:
        materialize_student_profile_aggregate(
            student_id=student_id,
            assignment_ids=[
                assignment.id
                for assignment in assignments
                if assignment.classroom_id == classroom_id
            ],
            scope_kind="classroom",
            scope_id=classroom_id,
            metric_version=metric_version,
            run_id=run_id,
            commit=False,
            db=db,
        )
    if commit:
        db.commit()
