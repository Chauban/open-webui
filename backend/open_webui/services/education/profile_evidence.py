import hashlib
import inspect
import json
import os
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.education import (
    Education,
    ProfileEvidenceAssignmentContext,
    ProfileEvidenceCaptureManifest,
    ProfileEvidenceCaptureStream,
    ProfileEvidenceConversationEvent,
    ProfileEvidenceDocument,
    ProfileEvidenceEditorEvent,
    ProfileEvidenceChallenge,
    ProfileEvidencePayload,
    ProfileEvidencePreviousRound,
    ProfileEvidenceProvenanceEvent,
    ProfileEvidenceReflection,
    ProfileEvidenceSnapshotModel,
    ProfileEvidenceVersionEvent,
    StudentProfileDataCompleteness,
    StudentProfileRoundProgress,
    ProfileMetricProjectionPayload,
    StudentProfileTimelinePoint,
    SubmissionEvidenceCompleteness,
    SubmissionReviewEventModel,
)
from open_webui.services.education.analysis import (
    build_submission_analysis,
    build_version_diffs,
)
from open_webui.services.education.profile import (
    PROFILE_INSIGHT_VERSION,
    PROFILE_METRIC_VERSION,
    _build_profile_insights,
    _build_trend,
    _compute_collaboration_index,
    _compute_deadline_window_ratio,
    _compute_end_loaded_ratio,
    _compute_process_index,
    _compute_revision_depth,
    _estimate_active_writing_seconds,
    _profile_index_formula,
    _reflection_quality_from_review,
    _slice_round_versions,
    _summarize_help_types,
)

PROFILE_EVIDENCE_SCHEMA_VERSION = "2026-09-08.1"
PROFILE_EVIDENCE_COLLECTOR_VERSION = "2026-09-03.1"


def canonical_json_hash(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _event_timestamp_seconds(value: object) -> int:
    timestamp = int(value or 0)
    while timestamp > 10_000_000_000:
        timestamp //= 1000
    return timestamp


def profile_algorithm_code_checksum() -> str:
    functions = (
        build_metric_projection,
        build_analysis_from_evidence,
        _evidence_versions,
        build_submission_analysis,
        build_version_diffs,
        _compute_collaboration_index,
        _compute_deadline_window_ratio,
        _compute_end_loaded_ratio,
        _compute_process_index,
        _compute_revision_depth,
        _estimate_active_writing_seconds,
        _reflection_quality_from_review,
        _build_profile_insights,
        _build_trend,
        _summarize_help_types,
    )
    return hashlib.sha256(
        "\n".join(inspect.getsource(function) for function in functions).encode("utf-8")
    ).hexdigest()


def profile_code_commit_sha() -> str:
    return os.getenv("WEBUI_BUILD_HASH", "dev-build")


def verify_profile_evidence(evidence: ProfileEvidenceSnapshotModel) -> None:
    actual_hash = canonical_json_hash(evidence.evidence_json.model_dump(mode="json"))
    if actual_hash != evidence.evidence_hash:
        raise ValueError("Profile evidence hash verification failed")


def ensure_current_profile_algorithm_release(
    db: Session, *, created_by: str = "system"
) -> None:
    formula = _profile_index_formula().model_dump(mode="json")
    Education.ensure_profile_algorithm_release(
        metric_version=PROFILE_METRIC_VERSION,
        insight_version=PROFILE_INSIGHT_VERSION,
        evidence_schema_version=PROFILE_EVIDENCE_SCHEMA_VERSION,
        formula_config=formula,
        code_commit_sha=profile_code_commit_sha(),
        code_checksum=profile_algorithm_code_checksum(),
        created_by=created_by,
        db=db,
    )


def capture_profile_evidence(
    *,
    submission,
    assignment,
    writing_session,
    final_version,
    reflection,
    versions: list,
    provenance_segments: list,
    operations: list,
    prompt_timeline: list[dict],
    effective_due_at: Optional[int],
    previous_submission,
    db: Session,
) -> ProfileEvidenceSnapshotModel:
    evidence_revision = Education.get_next_profile_evidence_revision(
        submission.id, db=db
    )
    previous_final = (
        Education.get_version_by_id(previous_submission.final_version_id, db=db)
        if previous_submission is not None
        else None
    )
    previous_review = (
        Education.get_submission_review_by_submission_id(previous_submission.id, db=db)
        if previous_submission is not None
        else None
    )
    round_versions = _slice_round_versions(
        versions,
        previous_submission.final_version_id if previous_submission else None,
        final_version.id,
    )
    version_window_started_at = (
        round_versions[0].created_at
        if round_versions
        else (
            previous_submission.submitted_at
            if previous_submission is not None
            else writing_session.created_at
        )
    )
    captured_from_at = (
        previous_submission.submitted_at
        if previous_submission is not None
        else writing_session.created_at
    )
    captured_until_at = submission.submitted_at
    round_operations = [
        operation
        for operation in operations
        if captured_from_at <= operation.occurred_at_ms // 1000 <= captured_until_at
    ]
    round_conversation = [
        message
        for message in prompt_timeline
        if captured_from_at
        <= _event_timestamp_seconds(message.get("created_at"))
        <= captured_until_at
    ]
    capture = SubmissionEvidenceCompleteness.model_validate(
        submission.stats_json["data_completeness"]
    )
    frozen_challenge = submission.stats_json.get("challenge") or {}
    revision = frozen_challenge.get("revision") or {}
    challenge = ProfileEvidenceChallenge(
        enabled=bool(frozen_challenge.get("enabled", False)),
        status=frozen_challenge.get("status"),
        planned_rounds=int(frozen_challenge.get("planned_rounds") or 0),
        answered_rounds=int(frozen_challenge.get("answered_rounds") or 0),
        unresolved_count=int(frozen_challenge.get("unresolved_count") or 0),
        focus_keys=list(frozen_challenge.get("focus_keys") or []),
        revised_after=revision.get("revised"),
        changed_spans=int(revision.get("changed_spans") or 0),
        total_spans=int(revision.get("total_spans") or 0),
    )

    payload = ProfileEvidencePayload(
        evidence_schema_version=PROFILE_EVIDENCE_SCHEMA_VERSION,
        submission_id=submission.id,
        student_id=submission.student_id,
        assignment_id=submission.assignment_id,
        writing_session_id=submission.writing_session_id,
        evidence_revision=evidence_revision,
        round_no=submission.round_no,
        submitted_at=submission.submitted_at,
        previous_submission_id=(
            previous_submission.id if previous_submission is not None else None
        ),
        previous_round=(
            ProfileEvidencePreviousRound(
                submission_id=previous_submission.id,
                round_no=previous_submission.round_no,
                final_content_text=(
                    previous_final.note_snapshot_text if previous_final else ""
                )
                or "",
                submitted_at=previous_submission.submitted_at,
                reviewed_at=previous_review.reviewed_at if previous_review else None,
                score=previous_review.score if previous_review else None,
                review_status=(
                    previous_review.review_status if previous_review else None
                ),
                rubric_scores=(
                    previous_review.rubric_scores if previous_review else None
                ),
                overall_comment=(
                    previous_review.overall_comment if previous_review else None
                ),
                returned_comment=(
                    previous_review.returned_comment if previous_review else None
                ),
                resubmit_due_at=(
                    previous_review.resubmit_due_at if previous_review else None
                ),
            )
            if previous_submission is not None
            else None
        ),
        assignment=ProfileEvidenceAssignmentContext(
            title=assignment.title,
            description=assignment.description,
            classroom_id=assignment.classroom_id,
            score_max=assignment.score_max,
            rubric_schema=assignment.rubric_schema,
            assignment_due_at=assignment.due_at,
            effective_due_at=effective_due_at,
        ),
        document=ProfileEvidenceDocument(
            final_version_id=final_version.id,
            content_text=final_version.note_snapshot_text or "",
            content_json=final_version.note_snapshot_json,
            content_hash=canonical_json_hash(
                {
                    "text": final_version.note_snapshot_text or "",
                    "json": final_version.note_snapshot_json,
                }
            ),
        ),
        versions=[
            ProfileEvidenceVersionEvent(
                id=version.id,
                version_no=version.version_no,
                trigger_type=version.trigger_type,
                content_text=version.note_snapshot_text or "",
                content_json=version.note_snapshot_json,
                created_at=version.created_at,
            )
            for version in round_versions
        ],
        editor_operations=[
            ProfileEvidenceEditorEvent(
                id=operation.id,
                user_id=operation.user_id,
                op_type=operation.op_type,
                source_type=operation.source_type,
                start_offset=operation.start_offset,
                end_offset=operation.end_offset,
                inserted_text=operation.inserted_text,
                deleted_text=operation.deleted_text,
                batch_id=operation.batch_id,
                occurred_at_ms=operation.occurred_at_ms,
                client_sequence=operation.client_sequence,
                metadata_json=operation.metadata_json,
                created_at=operation.created_at,
            )
            for operation in round_operations
        ],
        provenance=[
            ProfileEvidenceProvenanceEvent(
                id=segment.id,
                version_id=segment.version_id,
                source_type=segment.source_type,
                source_message_id=segment.source_message_id,
                segment_id=segment.segment_id,
                segment_text=segment.segment_text,
                start_offset=segment.start_offset,
                end_offset=segment.end_offset,
                metadata_json=segment.metadata_json,
                created_at=segment.created_at,
            )
            for segment in provenance_segments
        ],
        conversation=[
            ProfileEvidenceConversationEvent(
                id=str(message.get("id") or f"message-{index}"),
                role=message.get("role"),
                content=message.get("content"),
                created_at=_event_timestamp_seconds(message.get("created_at")),
                parent_id=message.get("parent_id"),
                model_id=message.get("model_id"),
                output=message.get("output"),
                usage=message.get("usage"),
            )
            for index, message in enumerate(round_conversation)
        ],
        reflection=ProfileEvidenceReflection(
            id=reflection.id,
            ai_used=reflection.ai_used,
            ai_help_types=list(reflection.ai_help_types),
            reflection=reflection.reflection_json,
            created_at=reflection.created_at,
        ),
        challenge=challenge,
        capture_manifest=ProfileEvidenceCaptureManifest(
            collector_version=PROFILE_EVIDENCE_COLLECTOR_VERSION,
            application_build=profile_code_commit_sha(),
            captured_from_at=captured_from_at,
            captured_until_at=captured_until_at,
            version_window_started_at=version_window_started_at,
            version_data=ProfileEvidenceCaptureStream(
                status=(
                    "complete"
                    if capture.version_data_complete and round_versions
                    else "missing"
                ),
                observed_count=len(round_versions),
                missing_reason=(
                    None
                    if capture.version_data_complete and round_versions
                    else "version_capture_incomplete"
                ),
            ),
            editor_operations=ProfileEvidenceCaptureStream(
                status=(
                    "complete" if capture.editor_operations_complete else "missing"
                ),
                observed_count=len(round_operations),
                missing_reason=(
                    None
                    if capture.editor_operations_complete
                    else "client_reported_incomplete"
                ),
            ),
            source_tracking=ProfileEvidenceCaptureStream(
                status="complete" if capture.source_tracking_complete else "missing",
                observed_count=len(provenance_segments),
                missing_reason=(
                    None
                    if capture.source_tracking_complete
                    else "client_reported_incomplete"
                ),
            ),
            conversation=ProfileEvidenceCaptureStream(
                status="complete",
                observed_count=len(round_conversation),
            ),
        ),
    )
    payload_json = payload.model_dump(mode="json")
    return Education.insert_profile_evidence_snapshot(
        payload,
        canonical_json_hash(payload_json),
        commit=False,
        db=db,
    )


def _as_namespace(value):
    return SimpleNamespace(**value.model_dump())


def _evidence_versions(facts: ProfileEvidencePayload) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=item.id,
            version_no=item.version_no,
            trigger_type=item.trigger_type,
            note_snapshot_text=item.content_text,
            note_snapshot_json=item.content_json,
            created_at=item.created_at,
        )
        for item in facts.versions
    ]


def build_analysis_from_evidence(evidence: ProfileEvidenceSnapshotModel) -> dict:
    verify_profile_evidence(evidence)
    facts = evidence.evidence_json
    submission = SimpleNamespace(
        id=facts.submission_id,
        final_version_id=facts.document.final_version_id,
        submitted_at=facts.submitted_at,
    )
    return build_submission_analysis(
        submission,
        SimpleNamespace(id=facts.writing_session_id),
        _evidence_versions(facts),
        [_as_namespace(item) for item in facts.provenance],
        [
            SimpleNamespace(
                **item.model_dump(exclude={"created_at"}),
                created_at=item.occurred_at_ms // 1000,
            )
            for item in facts.editor_operations
        ],
        [item.model_dump() for item in facts.conversation],
    )


def build_metric_projection(
    evidence: ProfileEvidenceSnapshotModel,
    review_event: Optional[SubmissionReviewEventModel],
    analysis: Optional[dict] = None,
) -> ProfileMetricProjectionPayload:
    facts = evidence.evidence_json
    versions = _evidence_versions(facts)
    analysis = analysis or build_analysis_from_evidence(evidence)
    summary = analysis["summary"]
    previous_text = (
        facts.previous_round.final_content_text if facts.previous_round else ""
    )
    version_diffs = build_version_diffs(versions, previous_text)
    inserted_chars = sum(diff.get("inserted_length", 0) for diff in version_diffs)
    revised_chars = sum(diff.get("deleted_length", 0) for diff in version_diffs)
    version_complete = facts.capture_manifest.version_data.status == "complete"
    editor_complete = facts.capture_manifest.editor_operations.status == "complete"
    source_complete = (
        facts.capture_manifest.source_tracking.status == "complete"
        and bool(summary.get("source_tracking_complete"))
    )
    revision_depth = (
        _compute_revision_depth(revised_chars, inserted_chars)
        if version_complete
        else None
    )
    writing_span_seconds = (
        max(
            facts.submitted_at - facts.capture_manifest.version_window_started_at,
            0,
        )
        if version_complete
        else None
    )
    end_loaded_ratio = (
        _compute_end_loaded_ratio(
            version_diffs,
            facts.capture_manifest.version_window_started_at,
            facts.submitted_at,
        )
        if version_complete
        else None
    )
    deadline_ratio = (
        _compute_deadline_window_ratio(version_diffs, facts.assignment.effective_due_at)
        if version_complete
        else None
    )
    reflection_quality = _reflection_quality_from_review(
        review_event.reflection_score if review_event else None
    )
    score_complete = bool(
        review_event
        and review_event.score is not None
        and review_event.rubric_scores is not None
    )
    scoring_status = (
        "complete"
        if score_complete
        else (
            "pending"
            if review_event is None or review_event.review_status == "pending"
            else (
                "not_applicable"
                if review_event.review_status == "returned"
                else "missing"
            )
        )
    )
    ai_ratio = (
        round(
            float(summary.get("ai_inserted_ratio", 0))
            + float(summary.get("ai_pasted_ratio", 0)),
            4,
        )
        if source_complete
        else None
    )
    digestion_ratio = (
        int(summary.get("average_rewrite_ratio", 0)) if source_complete else None
    )
    prompt_count = len([item for item in facts.conversation if item.role == "user"])
    point = StudentProfileTimelinePoint(
        submission_id=facts.submission_id,
        assignment_id=facts.assignment_id,
        assignment_title=facts.assignment.title,
        round_no=facts.round_no,
        submitted_at=facts.submitted_at,
        data_completeness=StudentProfileDataCompleteness(
            version_data="complete" if version_complete else "missing",
            editor_operations="complete" if editor_complete else "missing",
            source_tracking="complete" if source_complete else "missing",
            scoring=scoring_status,
        ),
        total_chars=len(facts.document.content_text),
        score=review_event.score if score_complete else None,
        score_max=facts.assignment.score_max,
        normalized_score=(
            round(review_event.score / facts.assignment.score_max * 100, 2)
            if score_complete
            else None
        ),
        rubric=review_event.rubric_scores if score_complete else None,
        review_status=review_event.review_status if review_event else "pending",
        inserted_chars=inserted_chars if version_complete else None,
        revised_chars=revised_chars if version_complete else None,
        revision_depth=revision_depth,
        writing_span_seconds=writing_span_seconds,
        active_writing_seconds=(
            _estimate_active_writing_seconds(
                [
                    operation.occurred_at_ms // 1000
                    for operation in facts.editor_operations
                ]
            )
            or 0
            if editor_complete
            else None
        ),
        lead_time_seconds=(
            facts.assignment.effective_due_at
            - facts.capture_manifest.version_window_started_at
            if facts.assignment.effective_due_at is not None and version_complete
            else None
        ),
        end_loaded_ratio=end_loaded_ratio,
        deadline_window_ratio=deadline_ratio,
        process_index=(
            _compute_process_index(
                revision_depth, writing_span_seconds, end_loaded_ratio
            )
            if version_complete
            else None
        ),
        typed_ratio=(float(summary.get("typed_ratio", 0)) if source_complete else None),
        ai_ratio=ai_ratio,
        unknown_ratio=(
            float(summary.get("unknown_ratio", 0)) if source_complete else None
        ),
        prompt_count=prompt_count,
        digestion_ratio=digestion_ratio,
        reflection_quality=reflection_quality,
        ai_help_types=list(facts.reflection.ai_help_types),
        collaboration_index=_compute_collaboration_index(
            digestion_ratio,
            prompt_count,
            reflection_quality,
            ai_ratio,
            facts.reflection.ai_used,
        ),
        burst_count=(int(summary.get("burst_count", 0)) if editor_complete else None),
        suspected_unmarked_import_count=(
            int(summary.get("suspected_unmarked_import_count", 0))
            if source_complete
            else None
        ),
        # 作业没开试读时这四项全是 None：那是「不适用」，不是「表现差」。
        challenge_status=(facts.challenge.status if facts.challenge.enabled else None),
        challenge_answer_ratio=(
            int(
                round(
                    facts.challenge.answered_rounds
                    / facts.challenge.planned_rounds
                    * 100
                )
            )
            if facts.challenge.enabled
            and facts.challenge.status == "completed"
            and facts.challenge.planned_rounds > 0
            else None
        ),
        challenge_unresolved_count=(
            facts.challenge.unresolved_count
            if facts.challenge.enabled and facts.challenge.status == "completed"
            else None
        ),
        challenge_revised=(
            facts.challenge.revised_after
            if facts.challenge.enabled and facts.challenge.status == "completed"
            else None
        ),
    )
    round_progress = None
    if facts.previous_round is not None:
        import difflib

        similarity = difflib.SequenceMatcher(
            None,
            facts.previous_round.final_content_text,
            facts.document.content_text,
        ).ratio()
        round_progress = StudentProfileRoundProgress(
            assignment_id=facts.assignment_id,
            assignment_title=facts.assignment.title,
            from_round=facts.previous_round.round_no,
            to_round=facts.round_no,
            char_delta=(
                len(facts.document.content_text)
                - len(facts.previous_round.final_content_text)
            ),
            revision_ratio=int(round((1 - similarity) * 100)),
            score_delta=(
                review_event.score - facts.previous_round.score
                if score_complete and facts.previous_round.score is not None
                else None
            ),
            turnaround_seconds=(
                facts.submitted_at - facts.previous_round.reviewed_at
                if facts.previous_round.reviewed_at is not None
                else None
            ),
        )
    return ProfileMetricProjectionPayload(
        metric_version=PROFILE_METRIC_VERSION,
        point=point,
        round_progress=round_progress,
    )


def project_profile_evidence(
    evidence: ProfileEvidenceSnapshotModel,
    review_event: Optional[SubmissionReviewEventModel],
    db: Session,
    *,
    run_id: Optional[str] = None,
    analysis_payload: Optional[dict] = None,
    commit: bool = True,
):
    ensure_current_profile_algorithm_release(db)
    analysis = analysis_payload or build_analysis_from_evidence(evidence)
    payload = build_metric_projection(evidence, review_event, analysis)
    review_revision = review_event.review_revision if review_event else 0
    input_hash = canonical_json_hash(
        {
            "evidence_hash": evidence.evidence_hash,
            "review": review_event.model_dump(mode="json") if review_event else None,
            "metric_version": PROFILE_METRIC_VERSION,
            "algorithm_checksum": profile_algorithm_code_checksum(),
        }
    )
    output_hash = canonical_json_hash(payload.model_dump(mode="json"))
    projection = Education.insert_profile_metric_projection(
        evidence,
        review_revision,
        PROFILE_METRIC_VERSION,
        payload,
        input_hash,
        output_hash,
        run_id=run_id,
        commit=commit,
        db=db,
    )
    return projection, analysis
