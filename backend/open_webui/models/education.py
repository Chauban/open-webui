import time
import uuid
from contextlib import contextmanager
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    and_,
    event,
    func,
)
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, JSONField, get_db_context as _get_db_context


@contextmanager
def get_db_context(db: Optional[Session] = None):
    """Education writes must honor the caller's unit-of-work session.

    The application-wide helper may intentionally ignore a supplied session when
    session sharing is disabled. That behavior is useful for unrelated read paths,
    but it makes a multi-record education transaction impossible. Education model
    methods therefore always reuse an explicitly supplied sync session.
    """

    if isinstance(db, Session):
        yield db
    else:
        with _get_db_context() as owned_db:
            yield owned_db


ASSIGNMENT_STATUSES = ("active", "archived")
# 作业的 AI 辅导风格；每档对应一段管理员可改写的提示词（config 的 education.coaching_prompts）。
CoachingStyle = Literal["socratic", "balanced", "hands_off"]
COACHING_STYLES = ("socratic", "balanced", "hands_off")
# 提交前质疑环节。辅导档位管的是「AI 帮多少」,质疑管的是「交之前挑多狠、挑哪几个维度」,
# 两者是两个互不兼任的角色:辅导助手不带质疑口吻,质疑读者不提供辅导。
ChallengeStatus = Literal["in_progress", "completed", "skipped"]
CHALLENGE_STATUSES = ("in_progress", "completed", "skipped")
# 只给 2 或 3。无限回合会把质疑变成打击,而且学生看不到终点就会中途退出。
CHALLENGE_ROUND_CHOICES = (2, 3)
CHALLENGE_MAX_FOCUS_KEYS = 2
AIHelpType = Literal[
    "Understand Assignment",
    "Outline",
    "Examples",
    "Explain Concepts",
    "Revise Structure",
    "Polish",
    "Check Errors",
    "Help Break Through Writer's Block",
    "Strengthen Reasoning",
    "Other",
]
WritingSourceType = Literal[
    "ai_inserted",
    "ai_pasted",
    "user_typed",
    "external_paste",
    "suspected_unmarked_import",
    "unknown",
]
WritingVersionTrigger = Literal["autosave", "manual", "submit", "submit_preflight"]
EditorOperationType = Literal[
    "keyboard_input",
    "replace",
    "delete_text",
    "ai_insert_clicked",
    "paste_detected",
    "platform_ai_insert",
    "ai_reply_selection_copied",
    "ai_copy_button_clicked",
]


class SubmissionAlreadyReviewedError(Exception):
    """学生想重交,但当前轮已被批改(只有退回才允许开新轮)。"""


class Assignment(Base):
    __tablename__ = "assignment"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')", name="assignment_status_check"
        ),
        CheckConstraint("score_max > 0", name="assignment_score_max_check"),
        CheckConstraint(
            "coaching_style IN ('socratic', 'balanced', 'hands_off')",
            name="assignment_coaching_style_check",
        ),
        CheckConstraint(
            "challenge_rounds IN (2, 3)", name="assignment_challenge_rounds_check"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Text, nullable=False)
    classroom_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    due_at = Column(BigInteger, nullable=True)
    score_max = Column(Integer, nullable=False)
    coaching_style = Column(Text, nullable=False, default="balanced")
    challenge_enabled = Column(Boolean, nullable=False, default=False)
    challenge_rounds = Column(Integer, nullable=False, default=3)
    challenge_focus_keys = Column(JSONField, nullable=False, default=list)
    # 写作前的评析靶文与预设漏洞。与质疑构成对称：写前建立判断标准，写后用于自己。
    critique_enabled = Column(Boolean, nullable=False, default=False)
    critique_text = Column(Text, nullable=True)
    critique_flaws = Column(JSONField, nullable=False, default=list)
    rubric_schema = Column(JSONField, nullable=False)
    archived_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class AssignmentExtension(Base):
    """单个学生在某个作业上的个人截止时间。

    作业的 due_at 是全班一刀切的硬闸门,提交接口过期即 403。学生请假、设备故障
    这类情况没有第二条路——改 due_at 会把全班一起放开。这张表让教师只给一个人
    放开,一个学生在一个作业上至多一条。
    """

    __tablename__ = "assignment_extension"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_id", name="assignment_extension_identity_idx"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(Text, nullable=False)
    due_at = Column(BigInteger, nullable=False)
    reason = Column(Text, nullable=True)
    granted_by = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class Classroom(Base):
    __tablename__ = "classroom"

    id = Column(Text, primary_key=True, unique=True)
    name = Column(Text, nullable=False)
    teacher_id = Column(Text, nullable=False)
    invite_code = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class ClassroomMember(Base):
    __tablename__ = "classroom_member"
    __table_args__ = (
        UniqueConstraint(
            "classroom_id", "user_id", name="classroom_member_classroom_user_idx"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    classroom_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    member_role = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class WritingSession(Base):
    __tablename__ = "writing_session"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "owner_user_id",
            "scope",
            name="writing_session_assignment_owner_scope_idx",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=True)
    owner_user_id = Column(Text, nullable=False)
    scope = Column(Text, nullable=False, default="assignment")
    note_id = Column(Text, nullable=False)
    folder_id = Column(Text, nullable=True)
    chat_id = Column(Text, nullable=True)
    active_chat_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="draft")
    submitted_submission_id = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class WritingVersion(Base):
    __tablename__ = "writing_version"
    __table_args__ = (
        UniqueConstraint(
            "writing_session_id",
            "version_no",
            name="writing_version_session_number_idx",
        ),
        CheckConstraint("version_no >= 1", name="writing_version_number_check"),
        CheckConstraint(
            "trigger_type IN ('autosave', 'manual', 'submit', 'submit_preflight')",
            name="writing_version_trigger_check",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    version_no = Column(BigInteger, nullable=False)
    note_snapshot_json = Column(JSONField, nullable=True)
    note_snapshot_text = Column(Text, nullable=True)
    trigger_type = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class ProvenanceSegment(Base):
    __tablename__ = "provenance_segment"
    __table_args__ = (
        UniqueConstraint(
            "writing_session_id",
            "segment_id",
            name="provenance_session_segment_idx",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    version_id = Column(Text, nullable=True)
    source_type = Column(Text, nullable=False)
    source_message_id = Column(Text, nullable=True)
    segment_id = Column(Text, nullable=False)
    segment_text = Column(Text, nullable=False)
    start_offset = Column(BigInteger, nullable=True)
    end_offset = Column(BigInteger, nullable=True)
    metadata_json = Column(JSONField, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class EditorOperation(Base):
    __tablename__ = "editor_operation"
    __table_args__ = (
        Index(
            "editor_operation_session_occurred_idx",
            "writing_session_id",
            "occurred_at_ms",
            "client_sequence",
        ),
        CheckConstraint(
            "occurred_at_ms >= 0", name="editor_operation_occurred_at_check"
        ),
        CheckConstraint(
            "client_sequence >= 0",
            name="editor_operation_client_sequence_check",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    op_type = Column(Text, nullable=False)
    source_type = Column(Text, nullable=False)
    start_offset = Column(BigInteger, nullable=True)
    end_offset = Column(BigInteger, nullable=True)
    inserted_text = Column(Text, nullable=True)
    deleted_text = Column(Text, nullable=True)
    batch_id = Column(Text, nullable=False)
    occurred_at_ms = Column(BigInteger, nullable=False)
    client_sequence = Column(BigInteger, nullable=False)
    metadata_json = Column(JSONField, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_result"
    __table_args__ = (
        UniqueConstraint(
            "writing_session_id",
            "submission_id",
            "result_type",
            name="analysis_result_scope_type_idx",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    submission_id = Column(
        Text, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    result_type = Column(Text, nullable=False)
    payload_json = Column(JSONField, nullable=False, default={})
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class MicroReflection(Base):
    __tablename__ = "micro_reflection"
    __table_args__ = (
        CheckConstraint("ai_used IN (0, 1)", name="micro_reflection_ai_used_check"),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    writing_session_id = Column(Text, nullable=False)
    ai_used = Column(Boolean, nullable=False)
    ai_help_types = Column(JSONField, nullable=False, default=[])
    reflection_json = Column(JSONField, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class ChallengeSession(Base):
    """学生提交前的一次质疑流程,一轮提交至多一条。

    source_version_id 冻结「质疑针对的是哪一稿」——收尾之后学生会回去改,
    不冻住的话教师就分不清质疑指的是改前还是改后的正文。
    """

    __tablename__ = "challenge_session"
    __table_args__ = (
        UniqueConstraint(
            "writing_session_id",
            "submission_round_no",
            name="challenge_session_round_idx",
        ),
        Index("challenge_session_student_idx", "assignment_id", "student_id"),
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'skipped')",
            name="challenge_session_status_check",
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(
        Text, ForeignKey("writing_session.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(Text, nullable=False)
    submission_round_no = Column(Integer, nullable=False)
    # 契约页尚未开始就跳过时没有「被质疑的那一稿」,空是语义正确的状态。
    source_version_id = Column(Text, nullable=True)
    focus_keys = Column(JSONField, nullable=False, default=list)
    planned_rounds = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="in_progress")
    closing_summary_json = Column(JSONField, nullable=True)
    checklist_state_json = Column(JSONField, nullable=True)
    # 教师退回意见的原文，发起这一轮时冻下来。评语可以事后被改，已开始的这轮不跟着变。
    followup_comment = Column(Text, nullable=True)
    started_at = Column(BigInteger, nullable=False)
    ended_at = Column(BigInteger, nullable=True)


class ChallengeTurn(Base):
    """一个质疑回合。

    challenge_text 是服务端生成的权威数据,response_text 是学生自己敲的字
    (可信度等同 typed 正文)。回合数由服务端按 planned_rounds 控制,不靠提示词。

    quoted_span 是这一轮质疑所引用的原文片段,必须是被质疑那一稿的连续子串。
    修订判定靠它定位——判的是「被质疑的那处变没变」,不是「全文改了多少字」。
    """

    __tablename__ = "challenge_turn"
    __table_args__ = (
        UniqueConstraint(
            "challenge_session_id", "turn_no", name="challenge_turn_order_idx"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    challenge_session_id = Column(
        Text, ForeignKey("challenge_session.id", ondelete="CASCADE"), nullable=False
    )
    turn_no = Column(Integer, nullable=False)
    focus_key = Column(Text, nullable=False)
    challenge_text = Column(Text, nullable=False)
    quoted_span = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    responded_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class CritiqueAttempt(Base):
    """一个学生对靶文的一次评析。

    一次作业至多一条:这是写作前的一道门,不是可以反复刷的练习。靶文与预设漏洞挂在
    assignment 上,不随 attempt 复制。
    """

    __tablename__ = "critique_attempt"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_id", name="critique_attempt_student_idx"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(Text, nullable=False)
    items_json = Column(JSONField, nullable=False, default=list)
    matches_json = Column(JSONField, nullable=False, default=list)
    completed_at = Column(BigInteger, nullable=False)


class ChallengeInsight(Base):
    """一次作业的班级质疑归纳,缓存用。

    第一层的维度命中率是纯内存聚合,不落表;只有这一层要调模型,所以必须缓存——
    不缓存的话教师每刷新一次看板就烧一次调用。
    """

    __tablename__ = "challenge_insight"
    __table_args__ = (
        # 一个作业只留一条:输入变了整条覆盖,不攒历史版本。
        UniqueConstraint("assignment_id", name="challenge_insight_assignment_idx"),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False
    )
    # 参与归纳的条目集合的规范化哈希。内容没变就直接复用,不重算。
    input_hash = Column(Text, nullable=False)
    categories_json = Column(JSONField, nullable=False)
    sample_size = Column(Integer, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class Submission(Base):
    __tablename__ = "submission"
    __table_args__ = (
        # 重复点击提交会并发走「先查当前轮再插入」,靠唯一约束兜住。
        UniqueConstraint(
            "assignment_id",
            "student_id",
            "round_no",
            name="submission_assignment_student_round_idx",
        ),
        CheckConstraint("round_no >= 1", name="submission_round_check"),
        CheckConstraint("is_current IN (0, 1)", name="submission_current_check"),
    )

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    writing_session_id = Column(Text, nullable=False)
    final_version_id = Column(Text, nullable=False)
    stats_json = Column(JSONField, nullable=False, default={})
    micro_reflection_id = Column(Text, nullable=False)
    submitted_at = Column(BigInteger, nullable=False)
    round_no = Column(BigInteger, nullable=False, default=1)
    is_current = Column(BigInteger, nullable=False, default=1)


class SubmissionReview(Base):
    __tablename__ = "submission_review"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'returned')",
            name="submission_review_status_check",
        ),
        CheckConstraint(
            "score IS NULL OR score >= 0", name="submission_review_score_check"
        ),
    )

    id = Column(Text, primary_key=True, unique=True)
    submission_id = Column(Text, nullable=False, unique=True)
    assignment_id = Column(Text, nullable=False)
    reviewer_id = Column(Text, nullable=False)
    review_status = Column(Text, nullable=False, default="pending")
    score = Column(BigInteger, nullable=True)
    overall_comment = Column(Text, nullable=True)
    rubric_scores = Column(JSONField, nullable=True)
    returned_comment = Column(Text, nullable=True)
    resubmit_due_at = Column(BigInteger, nullable=True)
    # 教师退回时是否要求质疑读者就这条意见追问。退回意见此前写完就没下文了。
    challenge_followup = Column(Boolean, nullable=False, default=False)
    reviewed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class ProfileEvidenceSnapshot(Base):
    """Immutable, algorithm-independent facts captured for one submit attempt."""

    __tablename__ = "profile_evidence_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "evidence_revision",
            name="profile_evidence_submission_revision_idx",
        ),
        CheckConstraint(
            "evidence_revision >= 1", name="profile_evidence_revision_check"
        ),
        CheckConstraint("round_no >= 1", name="profile_evidence_round_check"),
        CheckConstraint(
            "length(evidence_hash) = 64", name="profile_evidence_hash_check"
        ),
    )

    id = Column(Text, primary_key=True)
    submission_id = Column(
        Text, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    evidence_revision = Column(BigInteger, nullable=False)
    evidence_schema_version = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="RESTRICT"), nullable=False
    )
    round_no = Column(BigInteger, nullable=False)
    submitted_at = Column(BigInteger, nullable=False)
    evidence_json = Column(JSONField, nullable=False)
    evidence_hash = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class SubmissionReviewEvent(Base):
    """Append-only review facts; the mutable review row is only a current-state index."""

    __tablename__ = "submission_review_event"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "review_revision",
            name="submission_review_event_revision_idx",
        ),
        CheckConstraint(
            "review_revision >= 1", name="submission_review_event_revision_check"
        ),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'returned')",
            name="submission_review_event_status_check",
        ),
        CheckConstraint(
            "score IS NULL OR score >= 0", name="submission_review_event_score_check"
        ),
    )

    id = Column(Text, primary_key=True)
    submission_id = Column(
        Text, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    evidence_snapshot_id = Column(
        Text,
        ForeignKey("profile_evidence_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_revision = Column(BigInteger, nullable=False)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_id = Column(Text, nullable=False)
    review_status = Column(Text, nullable=False)
    score = Column(BigInteger, nullable=True)
    rubric_scores = Column(JSONField, nullable=True)
    overall_comment = Column(Text, nullable=True)
    returned_comment = Column(Text, nullable=True)
    resubmit_due_at = Column(BigInteger, nullable=True)
    reviewed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class ProfileAlgorithmRelease(Base):
    __tablename__ = "profile_algorithm_release"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="profile_algorithm_release_status_check",
        ),
    )

    id = Column(Text, primary_key=True)
    metric_version = Column(Text, nullable=False, unique=True)
    insight_version = Column(Text, nullable=False)
    evidence_schema_versions = Column(JSONField, nullable=False)
    formula_config_json = Column(JSONField, nullable=False)
    code_commit_sha = Column(Text, nullable=False)
    code_checksum = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    created_by = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    activated_at = Column(BigInteger, nullable=True)


class ProfileProjectionRun(Base):
    __tablename__ = "profile_projection_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="profile_projection_run_status_check",
        ),
        CheckConstraint(
            "expected_count >= 0 AND succeeded_count >= 0 AND failed_count >= 0",
            name="profile_projection_run_count_check",
        ),
    )

    id = Column(Text, primary_key=True)
    metric_version = Column(
        Text, ForeignKey("profile_algorithm_release.metric_version"), nullable=False
    )
    scope_json = Column(JSONField, nullable=False)
    expected_count = Column(BigInteger, nullable=False, default=0)
    succeeded_count = Column(BigInteger, nullable=False, default=0)
    failed_count = Column(BigInteger, nullable=False, default=0)
    error_json = Column(JSONField, nullable=False, default=[])
    status = Column(Text, nullable=False)
    requested_by = Column(Text, nullable=False)
    code_commit_sha = Column(Text, nullable=False)
    config_hash = Column(Text, nullable=False)
    started_at = Column(BigInteger, nullable=True)
    finished_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class ProfileMetricProjection(Base):
    __tablename__ = "profile_metric_projection"
    __table_args__ = (
        UniqueConstraint(
            "evidence_snapshot_id",
            "review_revision",
            "metric_version",
            name="profile_metric_projection_identity_idx",
        ),
        CheckConstraint(
            "review_revision >= 0", name="profile_metric_projection_review_check"
        ),
        CheckConstraint("round_no >= 1", name="profile_metric_projection_round_check"),
        CheckConstraint(
            "length(input_hash) = 64 AND length(output_hash) = 64",
            name="profile_metric_projection_hash_check",
        ),
    )

    id = Column(Text, primary_key=True)
    evidence_snapshot_id = Column(
        Text,
        ForeignKey("profile_evidence_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_id = Column(
        Text, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(Text, nullable=False)
    assignment_id = Column(
        Text, ForeignKey("assignment.id", ondelete="RESTRICT"), nullable=False
    )
    round_no = Column(BigInteger, nullable=False)
    submitted_at = Column(BigInteger, nullable=False)
    review_revision = Column(BigInteger, nullable=False, default=0)
    metric_version = Column(
        Text, ForeignKey("profile_algorithm_release.metric_version"), nullable=False
    )
    projection_json = Column(JSONField, nullable=False)
    input_hash = Column(Text, nullable=False)
    output_hash = Column(Text, nullable=False)
    run_id = Column(Text, ForeignKey("profile_projection_run.id"), nullable=True)
    generated_at = Column(BigInteger, nullable=False)


class StudentProfileAggregateProjection(Base):
    __tablename__ = "student_profile_aggregate_projection"
    __table_args__ = (
        Index(
            "student_profile_aggregate_latest_idx",
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "aggregate_revision",
        ),
        UniqueConstraint(
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "input_hash",
            name="student_profile_aggregate_identity_idx",
        ),
        UniqueConstraint(
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "aggregate_revision",
            name="student_profile_aggregate_revision_idx",
        ),
        CheckConstraint(
            "scope_kind IN ('global', 'classroom')",
            name="student_profile_aggregate_scope_check",
        ),
        CheckConstraint(
            "length(input_hash) = 64 AND length(output_hash) = 64",
            name="student_profile_aggregate_hash_check",
        ),
        CheckConstraint(
            "aggregate_revision >= 1",
            name="student_profile_aggregate_revision_check",
        ),
    )

    id = Column(Text, primary_key=True)
    student_id = Column(Text, nullable=False)
    scope_kind = Column(Text, nullable=False)
    scope_id = Column(Text, nullable=False)
    metric_version = Column(
        Text, ForeignKey("profile_algorithm_release.metric_version"), nullable=False
    )
    aggregate_revision = Column(BigInteger, nullable=False)
    projection_count = Column(BigInteger, nullable=False)
    input_hash = Column(Text, nullable=False)
    output_hash = Column(Text, nullable=False)
    aggregate_json = Column(JSONField, nullable=False)
    run_id = Column(Text, ForeignKey("profile_projection_run.id"), nullable=True)
    generated_at = Column(BigInteger, nullable=False)


def _reject_immutable_profile_record_change(mapper, connection, target) -> None:
    del mapper, connection, target
    raise ValueError("Profile evidence and published projections are immutable")


for _immutable_profile_model in (
    ProfileEvidenceSnapshot,
    SubmissionReviewEvent,
    ProfileMetricProjection,
    StudentProfileAggregateProjection,
):
    event.listen(
        _immutable_profile_model,
        "before_update",
        _reject_immutable_profile_record_change,
    )
    event.listen(
        _immutable_profile_model,
        "before_delete",
        _reject_immutable_profile_record_change,
    )


class StudentGrowthGoal(Base):
    __tablename__ = "student_growth_goal"

    id = Column(Text, primary_key=True, unique=True)
    student_id = Column(Text, nullable=False)
    classroom_id = Column(Text, nullable=True)
    assignment_id = Column(Text, nullable=True)
    goal_text = Column(Text, nullable=False)
    target_at = Column(BigInteger, nullable=True)
    status = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class TeacherStudentNote(Base):
    __tablename__ = "teacher_student_note"

    id = Column(Text, primary_key=True, unique=True)
    teacher_id = Column(Text, nullable=False)
    classroom_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    observed_at = Column(BigInteger, nullable=False)
    edited_at = Column(BigInteger, nullable=True)
    deleted_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class TeacherStudentNoteRevision(Base):
    __tablename__ = "teacher_student_note_revision"

    id = Column(Text, primary_key=True, unique=True)
    note_id = Column(Text, nullable=False)
    teacher_id = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    observed_at = Column(BigInteger, nullable=False)
    action = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class EducationNotification(Base):
    __tablename__ = "education_notification"

    id = Column(Text, primary_key=True, unique=True)
    user_id = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    payload_json = Column(JSONField, nullable=False, default={})
    created_at = Column(BigInteger, nullable=False)
    read_at = Column(BigInteger, nullable=True)


class RubricCriterion(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    max_score: int = Field(gt=0, le=10000)

    @field_validator("key", "label", mode="before")
    @classmethod
    def strip_rubric_text(cls, value: str) -> str:
        return value.strip()


class RubricSchema(BaseModel):
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_unique_keys(self):
        keys = [criterion.key for criterion in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("Rubric criterion keys must be unique")
        return self

    @property
    def total_score(self) -> int:
        return sum(criterion.max_score for criterion in self.criteria)


CRITIQUE_MAX_ITEMS = 3


class CritiqueFlaw(BaseModel):
    """靶文里一处预设的漏洞。

    绑定 rubric 维度,命中情况才能并进按维度的班级统计。教师必须逐条确认——AI 生成的
    漏洞未必真成立,挂上去就是教错。
    """

    key: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    focus_key: str = Field(min_length=1)


class CritiqueMatch(BaseModel):
    """一处预设漏洞有没有被这个学生找出来。只报命中,不给分、不给等级。"""

    key: str
    focus_key: str
    hit: bool = False


class CritiqueAttemptModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    items_json: list[str] = Field(default_factory=list)
    matches_json: list[CritiqueMatch] = Field(default_factory=list)
    completed_at: int


class CritiqueSubmitForm(BaseModel):
    """学生写出他认为站不住的地方。

    至多三条,且**不设及格线**——找出一条也放行。一旦设卡,学生会转而猜测系统想要
    什么答案,训练目标当场失效。
    """

    items: list[str] = Field(default_factory=list, max_length=CRITIQUE_MAX_ITEMS)
    model: str


class CritiqueStateResponse(BaseModel):
    enabled: bool = False
    text: str = ""
    completed: bool = False
    attempt: Optional[CritiqueAttemptModel] = None


def validate_critique_config(
    enabled: bool,
    text: Optional[str],
    flaws: list,
    rubric: RubricSchema,
) -> tuple[Optional[str], list[dict]]:
    """靶文配置的唯一校验入口。

    与质疑同一条约束:漏洞绑的维度必须是本作业已有的评分维度。没有维度就没有对齐的
    方向,命中情况也并不进按维度的统计。
    """

    if not enabled:
        return (text or None), []

    body = (text or "").strip()
    if not body:
        raise ValueError("Critique needs a target text")

    parsed = [CritiqueFlaw.model_validate(flaw) for flaw in flaws]
    if not parsed:
        raise ValueError("Critique needs at least one preset flaw")

    valid_keys = {criterion.key for criterion in rubric.criteria}
    if not valid_keys:
        raise ValueError("Critique requires rubric criteria")
    for flaw in parsed:
        if flaw.focus_key not in valid_keys:
            raise ValueError(f"Unknown rubric criterion: {flaw.focus_key}")

    keys = [flaw.key for flaw in parsed]
    if len(set(keys)) != len(keys):
        raise ValueError("Critique flaw keys must be unique")

    return body, [flaw.model_dump() for flaw in parsed]


class AssignmentModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    teacher_id: str
    classroom_id: Optional[str] = None
    status: str
    due_at: Optional[int] = None
    score_max: int
    coaching_style: CoachingStyle
    challenge_enabled: bool
    challenge_rounds: int
    challenge_focus_keys: list[str] = Field(default_factory=list)
    critique_enabled: bool = False
    critique_text: Optional[str] = None
    critique_flaws: list[CritiqueFlaw] = Field(default_factory=list)
    rubric_schema: RubricSchema
    archived_at: Optional[int] = None
    created_at: int
    updated_at: int


def validate_challenge_focus_keys(
    focus_keys: list[str], rubric: RubricSchema, enabled: bool
) -> list[str]:
    """质疑焦点必须是本作业已有的评分维度。

    焦点直接复用 rubric,教师不用学新概念,学生被追问的点就是最后被扣分的点。
    未配置评分维度的作业不允许启用质疑——没有维度就没有对齐的方向。
    """

    keys = [key.strip() for key in focus_keys if key.strip()]
    if not enabled:
        return []
    if not keys:
        raise ValueError("Challenge focus requires at least one rubric criterion")
    if len(keys) > CHALLENGE_MAX_FOCUS_KEYS:
        raise ValueError(
            f"Challenge focus accepts at most {CHALLENGE_MAX_FOCUS_KEYS} criteria"
        )
    if len(keys) != len(set(keys)):
        raise ValueError("Challenge focus keys must be unique")
    known = {criterion.key for criterion in rubric.criteria}
    unknown = [key for key in keys if key not in known]
    if unknown:
        raise ValueError("Challenge focus keys must reference rubric criteria")
    return keys


class ChallengeClosingItem(BaseModel):
    """一条仍不成立的点。

    turn_no 是模型自己报的「这条来自第几轮」,focus_key 由服务端按轮次映射得出——
    让模型直接报维度 key 它会瞎编,报轮次它错不了,错了也能当场验出来。

    带上维度是为了班级层面能按维度聚合(「本次论据支撑 21 人没答住」),没有归属的
    条目照样展示给学生,只是不进那张统计表——不硬塞给某个维度。
    """

    text: str
    turn_no: Optional[int] = None
    focus_key: Optional[str] = None


class ChallengeClosing(BaseModel):
    """收尾清单。没有它,学生只是被怼一顿,下次必然跳过。"""

    stood: list[str] = Field(default_factory=list)
    unresolved: list[ChallengeClosingItem] = Field(default_factory=list)


class ChallengeTurnModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    challenge_session_id: str
    turn_no: int
    focus_key: str
    challenge_text: str
    quoted_span: str
    response_text: Optional[str] = None
    responded_at: Optional[int] = None
    created_at: int


class ChallengeSessionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    assignment_id: str
    student_id: str
    submission_round_no: int
    source_version_id: Optional[str] = None
    focus_keys: list[str] = Field(default_factory=list)
    planned_rounds: int
    status: ChallengeStatus
    followup_comment: Optional[str] = None
    closing_summary_json: Optional[ChallengeClosing] = None
    checklist_state_json: Optional[dict] = None
    started_at: int
    ended_at: Optional[int] = None


class ChallengeSessionDetail(BaseModel):
    session: ChallengeSessionModel
    turns: list[ChallengeTurnModel] = Field(default_factory=list)
    # 只有教师读提交时才带：被质疑那一稿与最终正文的差异结论，提交时已冻在 stats_json。
    revision: Optional[dict] = None


class ChallengeInsightCategory(BaseModel):
    """一类「本班普遍站不住的论证」。

    只报频次,不作评价:允许「以个例代替普遍规律,出现 14 人次」,禁止「本班论证基础
    薄弱」这类给班级贴标签的结论。样例必须脱敏到教师敢拿上讲台——展示时全班不能
    认出是谁。
    """

    name: str
    hits: int = Field(default=0, ge=0)
    samples: list[str] = Field(default_factory=list)
    advice: str = ""


class ChallengeInsightModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    input_hash: str
    categories_json: dict
    sample_size: int
    created_at: int


class ChallengeInsightResponse(BaseModel):
    """样本不足时 categories 为空、below_threshold 为真,前端不显示半成品结论。"""

    categories: list[ChallengeInsightCategory] = Field(default_factory=list)
    sample_size: int = 0
    below_threshold: bool = False
    threshold: int = 0
    generated_at: Optional[int] = None


class ChallengeInsightForm(BaseModel):
    """生成教研分析。质疑用哪个模型由学生写作区决定,这里由教师决定。"""

    model: str


class ChallengeStartForm(BaseModel):
    writing_session_id: str
    # 质疑是核心教学交互,不走 task model 降级,直接用学生写作区当前选的模型。
    model: str


class ChallengeSkipBeforeStartForm(BaseModel):
    """契约页尚未开始就跳过。没有 session 可标记,所以按作业 + 写作会话定位。"""

    writing_session_id: str


class ChallengeRespondForm(BaseModel):
    turn_no: int = Field(gt=0)
    response_text: str = Field(min_length=1, max_length=8000)
    model: str

    @field_validator("response_text", mode="before")
    @classmethod
    def strip_response(cls, value: str) -> str:
        return (value or "").strip()


class ChallengeChecklistForm(BaseModel):
    checked_indexes: list[int] = Field(default_factory=list)


class ClassroomModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    teacher_id: str
    invite_code: str
    status: str
    created_at: int
    updated_at: int


class ClassroomMemberModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    classroom_id: str
    user_id: str
    member_role: str
    created_at: int
    updated_at: int


class WritingSessionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: Optional[str] = None
    owner_user_id: str
    scope: str
    note_id: str
    folder_id: Optional[str] = None
    chat_id: Optional[str] = None
    active_chat_id: Optional[str] = None
    status: str
    submitted_submission_id: Optional[str] = None
    created_at: int
    updated_at: int


class WritingVersionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    version_no: int
    note_snapshot_json: Optional[dict] = None
    note_snapshot_text: Optional[str] = None
    trigger_type: str
    created_at: int


class WritingVersionSummaryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    version_no: int
    trigger_type: str
    created_at: int


class ProvenanceSegmentModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    version_id: Optional[str] = None
    source_type: str
    source_message_id: Optional[str] = None
    segment_id: str
    segment_text: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    metadata_json: Optional[dict] = None
    created_at: int


class EditorOperationModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    user_id: str
    op_type: str
    source_type: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    inserted_text: Optional[str] = None
    deleted_text: Optional[str] = None
    batch_id: str
    occurred_at_ms: int
    client_sequence: int
    metadata_json: Optional[dict] = None
    created_at: int


class AnalysisResultModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    submission_id: str
    result_type: str
    payload_json: dict
    created_at: int
    updated_at: int


class StructuredReflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=10, max_length=1000)
    location: str = Field(min_length=2, max_length=300)
    judgement: str = Field(min_length=10, max_length=1000)
    next_step: str = Field(min_length=5, max_length=500)
    other_ai_help: Optional[str] = Field(default=None, max_length=300)

    @field_validator(
        "action", "location", "judgement", "next_step", "other_ai_help", mode="before"
    )
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class MicroReflectionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    writing_session_id: str
    ai_used: bool
    ai_help_types: list[AIHelpType] = Field(default_factory=list)
    reflection_json: StructuredReflection
    created_at: int


class SubmissionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    writing_session_id: str
    final_version_id: str
    stats_json: dict
    micro_reflection_id: str
    submitted_at: int
    round_no: int = 1
    is_current: int = 1


class SubmissionReviewModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submission_id: str
    assignment_id: str
    reviewer_id: str
    review_status: str
    score: Optional[int] = Field(default=None, ge=0)
    overall_comment: Optional[str] = None
    rubric_scores: Optional[dict[str, int]] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None
    challenge_followup: bool = False
    reviewed_at: Optional[int] = None
    created_at: int
    updated_at: int


class EducationNotificationModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: str
    payload_json: dict
    created_at: int
    read_at: Optional[int] = None


class AssignmentCreateForm(BaseModel):
    title: str
    description: Optional[str] = None
    classroom_ids: list[str] = Field(default_factory=list)
    due_at: Optional[int] = None
    score_max: int = Field(gt=0, le=10000)
    coaching_style: CoachingStyle = "balanced"
    challenge_enabled: bool = False
    challenge_rounds: int = 3
    challenge_focus_keys: list[str] = Field(default_factory=list)
    critique_enabled: bool = False
    critique_text: Optional[str] = None
    critique_flaws: list[CritiqueFlaw] = Field(default_factory=list)
    rubric_schema: RubricSchema

    @model_validator(mode="after")
    def validate_rubric_total(self):
        if self.rubric_schema.total_score != self.score_max:
            raise ValueError(
                "Rubric maximum scores must add up to assignment maximum score"
            )
        return self

    @model_validator(mode="after")
    def validate_challenge_config(self):
        if self.challenge_rounds not in CHALLENGE_ROUND_CHOICES:
            raise ValueError("Challenge rounds must be 2 or 3")
        self.challenge_focus_keys = validate_challenge_focus_keys(
            self.challenge_focus_keys, self.rubric_schema, self.challenge_enabled
        )
        return self

    @model_validator(mode="after")
    def validate_critique(self):
        text, flaws = validate_critique_config(
            self.critique_enabled,
            self.critique_text,
            [flaw.model_dump() for flaw in self.critique_flaws],
            self.rubric_schema,
        )
        self.critique_text = text
        self.critique_flaws = [CritiqueFlaw.model_validate(flaw) for flaw in flaws]
        return self


class AssignmentUpdateForm(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    classroom_id: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[int] = None
    score_max: Optional[int] = Field(default=None, gt=0, le=10000)
    coaching_style: Optional[CoachingStyle] = None
    challenge_enabled: Optional[bool] = None
    challenge_rounds: Optional[int] = None
    # 焦点 key 要对着「更新后」的 rubric 校验,而 rubric 可能不在本次请求里,
    # 所以交叉校验放在 update_assignment 里做,那里能拿到库里的现值。
    challenge_focus_keys: Optional[list[str]] = None
    # 靶文同理：漏洞绑的维度要对着「更新后」的 rubric 校验，交叉校验放在
    # update_assignment 里做。
    critique_enabled: Optional[bool] = None
    critique_text: Optional[str] = None
    critique_flaws: Optional[list[CritiqueFlaw]] = None
    rubric_schema: Optional[RubricSchema] = None

    @model_validator(mode="after")
    def validate_updated_challenge_rounds(self):
        if (
            self.challenge_rounds is not None
            and self.challenge_rounds not in CHALLENGE_ROUND_CHOICES
        ):
            raise ValueError("Challenge rounds must be 2 or 3")
        return self

    @model_validator(mode="after")
    def validate_updated_rubric_total(self):
        if (
            self.score_max is not None
            and self.rubric_schema is not None
            and self.rubric_schema.total_score != self.score_max
        ):
            raise ValueError(
                "Rubric maximum scores must add up to assignment maximum score"
            )
        return self


class ClassroomCreateForm(BaseModel):
    name: str


class ClassroomJoinForm(BaseModel):
    invite_code: str


class ClassroomMemberCreateForm(BaseModel):
    user_id: str
    member_role: str = "student"


class AssignmentWorkspaceResponse(BaseModel):
    assignment: AssignmentModel
    membership_role: str
    writing_session: WritingSessionModel
    note: dict
    project: dict
    active_chat_id: Optional[str] = None
    source_map: list[ProvenanceSegmentModel] = Field(default_factory=list)
    review: Optional[dict] = None
    effective_due_at: Optional[int] = None


class WritingProcessSummaryResponse(BaseModel):
    clarification_answered_count: int = Field(ge=0)


class PersonalWritingCreateForm(BaseModel):
    title: Optional[str] = None


class PersonalWorkspaceListItem(BaseModel):
    project_mode: str = "personal_writing"
    writing_session: WritingSessionModel
    project_id: Optional[str] = None
    title: str
    updated_at: int
    preview_text: Optional[str] = None


class WritingRecentItem(BaseModel):
    project_mode: str
    scope: str
    writing_session_id: str
    title: str
    updated_at: int
    status: str
    assignment: Optional[AssignmentModel] = None


class WritingHomeResponse(BaseModel):
    role: str
    classrooms: list[ClassroomModel] = Field(default_factory=list)
    recent_items: list[WritingRecentItem] = Field(default_factory=list)
    assignment_items: list["AssignmentWorkspaceListItem"] = Field(default_factory=list)
    personal_items: list[PersonalWorkspaceListItem] = Field(default_factory=list)


class UnifiedWritingWorkspaceResponse(BaseModel):
    scope: str
    owner_role: str
    assignment: Optional[AssignmentModel] = None
    writing_session: WritingSessionModel
    note: dict
    project: dict
    active_chat_id: Optional[str] = None
    source_map: list[ProvenanceSegmentModel] = Field(default_factory=list)


class ClassroomMemberDetail(BaseModel):
    member: ClassroomMemberModel
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    education_role: Optional[str] = None


class ClassroomResponse(BaseModel):
    classroom: ClassroomModel
    membership: Optional[ClassroomMemberModel] = None


class TeacherAssignmentListItem(BaseModel):
    assignment: AssignmentModel
    classroom: Optional[ClassroomModel] = None
    student_count: int = 0
    submission_count: int = 0
    latest_submission_at: Optional[int] = None
    risk_summary: Optional[dict] = None


class TeacherClassroomListItem(BaseModel):
    classroom: ClassroomModel
    student_count: int = 0
    assignment_count: int = 0
    risk_summary: Optional[dict] = None


class AdminClassroomListItem(BaseModel):
    classroom: ClassroomModel
    teacher_name: Optional[str] = None


class StudentAssignmentListItem(BaseModel):
    assignment: AssignmentModel
    membership: ClassroomMemberModel
    has_submission: bool = False
    submission_id: Optional[str] = None
    writing_session_id: Optional[str] = None


class AssignmentWorkspaceListItem(BaseModel):
    project_mode: str = "assignment_writing"
    assignment: AssignmentModel
    project_id: Optional[str] = None
    writing_session_id: Optional[str] = None
    status: str
    updated_at: int
    submitted_at: Optional[int] = None
    review_status: Optional[str] = None
    score: Optional[int] = None
    effective_due_at: Optional[int] = None
    round_no: Optional[int] = None


class AutosaveForm(BaseModel):
    content_json: Optional[dict] = None
    content_html: Optional[str] = None
    content_text: str = ""
    save_reason: str = "autosave"


class VersionCreateForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_type: WritingVersionTrigger
    content_json: Optional[dict] = None
    content_text: str = Field(default="", max_length=1_000_000)


class ProvenanceSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1, max_length=200)
    source_type: WritingSourceType
    segment_text: str = Field(max_length=1_000_000)
    source_message_id: Optional[str] = None
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, ge=0)
    metadata_json: Optional[dict] = None

    @model_validator(mode="after")
    def validate_offsets(self):
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be supplied together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not precede start_offset")
        return self


class EditorOperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op_type: EditorOperationType
    source_type: WritingSourceType
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, ge=0)
    inserted_text: Optional[str] = None
    deleted_text: Optional[str] = None
    batch_id: str = Field(min_length=1, max_length=200)
    occurred_at_ms: int = Field(ge=0)
    client_sequence: int = Field(ge=0)
    metadata_json: Optional[dict] = None

    @model_validator(mode="after")
    def validate_offsets(self):
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be supplied together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not precede start_offset")
        return self


class EditorOperationCreateForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[EditorOperationInput] = Field(
        default_factory=list, max_length=1000
    )


class ProvenanceCreateForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: Optional[str] = None
    segments: list[ProvenanceSegmentInput] = Field(
        default_factory=list, max_length=10000
    )
    replace_existing: bool = False


class SubmissionEvidenceCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_data_complete: bool
    editor_operations_complete: bool
    source_tracking_complete: bool


class SubmissionCreateForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    writing_session_id: str = Field(min_length=1)
    final_content_json: Optional[dict] = None
    final_content_html: Optional[str] = None
    final_content_text: str = Field(max_length=1_000_000)
    ai_used: bool
    ai_help_types: list[AIHelpType] = Field(default_factory=list)
    reflection: StructuredReflection
    data_completeness: SubmissionEvidenceCompleteness

    @model_validator(mode="after")
    def validate_ai_reflection(self):
        if len(self.ai_help_types) != len(set(self.ai_help_types)):
            raise ValueError("AI help types must be unique")
        if self.ai_used and not self.ai_help_types:
            raise ValueError("At least one AI help type is required when AI was used")
        if not self.ai_used and self.ai_help_types:
            raise ValueError("AI help types must be empty when AI was not used")
        if "Other" in self.ai_help_types and not self.reflection.other_ai_help:
            raise ValueError("Other AI help requires a description")
        if "Other" not in self.ai_help_types and self.reflection.other_ai_help:
            raise ValueError("Other AI help description requires the Other help type")
        return self


class SubmissionReviewForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["pending", "reviewed", "returned"] = "reviewed"
    score: Optional[int] = Field(default=None, ge=0)
    overall_comment: Optional[str] = None
    rubric_scores: Optional[dict[str, int]] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None
    # 只在退回时有意义：让质疑读者下一轮就着这条意见追问。
    challenge_followup: bool = False


class ClassroomBulkImportForm(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)


class ClassroomMembersActionForm(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class ClassroomMemberTransferForm(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    target_classroom_id: str


class ClassroomMembersActionResult(BaseModel):
    affected_count: int = 0
    skipped_users: list[str] = Field(default_factory=list)


class AssignmentExtensionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    due_at: int
    reason: Optional[str] = None
    granted_by: str
    created_at: int
    updated_at: int


class AssignmentExtensionForm(BaseModel):
    due_at: int = Field(gt=0)
    reason: Optional[str] = Field(default=None, max_length=200)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class UnsubmittedStudentItem(BaseModel):
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    extension: Optional[AssignmentExtensionModel] = None
    effective_due_at: Optional[int] = None


class AssignmentRemindForm(BaseModel):
    user_ids: Optional[list[str]] = None


class AssignmentRemindResult(BaseModel):
    reminded_count: int = 0
    user_ids: list[str] = Field(default_factory=list)


class SubmissionListItem(BaseModel):
    submission: SubmissionModel
    session: WritingSessionModel
    assignment: AssignmentModel
    classroom: Optional[ClassroomModel] = None
    reflection: Optional[MicroReflectionModel] = None
    student_name: Optional[str] = None
    review_status: str = "pending"
    score: Optional[float] = None
    risk_summary: Optional[dict] = None


class SubmissionDetailResponse(BaseModel):
    submission: SubmissionModel
    assignment: AssignmentModel
    writing_session: WritingSessionModel
    final_version: WritingVersionModel
    versions: list[WritingVersionSummaryModel]
    version_count: int = 0
    provenance_segments: list[ProvenanceSegmentModel]
    prompt_timeline: list[dict]
    micro_reflection: MicroReflectionModel
    review: Optional[SubmissionReviewModel] = None
    note: dict
    student_name: Optional[str] = None
    analysis: Optional[dict] = None
    rounds: list[dict] = Field(default_factory=list)


class MySubmissionRoundContent(BaseModel):
    content_json: Optional[dict] = None
    content_text: str = ""


class MySubmissionRoundReview(BaseModel):
    review_status: str
    score: Optional[int] = None
    rubric: Optional[dict] = None
    overall_comment: Optional[str] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None
    reviewed_at: Optional[int] = None


class MySubmissionRound(BaseModel):
    submission_id: str
    round_no: int
    is_current: int
    submitted_at: int
    content: MySubmissionRoundContent
    review: Optional[MySubmissionRoundReview] = None


class MyAssignmentSubmissionsResponse(BaseModel):
    assignment_id: str
    rounds: list[MySubmissionRound] = Field(default_factory=list)


class DashboardItem(BaseModel):
    submission_id: str
    student_id: str
    student_name: Optional[str] = None
    source_stats: dict
    prompt_count: int
    has_reflection: bool
    submitted_at: int
    risk_summary: Optional[dict] = None


class DashboardResponse(BaseModel):
    items: list[DashboardItem]
    summary: Optional[dict] = None
    distributions: Optional[dict] = None


class TeacherOverviewResponse(BaseModel):
    classroom_count: int
    assignment_count: int
    submission_count: int
    pending_review_count: int = 0
    unsubmitted_count: int = 0
    classrooms: list[TeacherClassroomListItem]
    # 概述页只保留三份清单：提交（含批改状态与风险）、作业（含截止与进度）、班级。
    recent_assignments: list[TeacherAssignmentListItem]
    recent_submissions: list[SubmissionListItem]


class TeacherReviewResponse(BaseModel):
    items: list[SubmissionListItem] = Field(default_factory=list)
    total: int = 0


ProfileReviewStatus = Literal["unsubmitted", "pending", "reviewed", "returned"]
ProfileTrendDirection = Literal["up", "down", "flat"]
ProfileCompletenessStatus = Literal["complete", "missing", "pending", "not_applicable"]
ProfileInsightTone = Literal["positive", "warning", "neutral"]
ProfileInsightCode = Literal[
    "not_enough_data",
    "digestion_up",
    "digestion_low",
    "ai_share_changed",
    "round_improvement",
    "round_revision_thin",
    "help_type_shift_refining",
    "deadline_rush",
    "process_up",
    "reflection_thin",
    "ai_revision_productive",
    "ai_use_needs_review",
]
ProfileInsightActionCode = Literal[
    "complete_more_submissions",
    "keep_rewriting_ai_text",
    "rewrite_one_ai_section",
    "review_ai_use_pattern",
    "reuse_successful_revision",
    "revise_feedback_deeply",
    "continue_refining_own_writing",
    "start_next_assignment_earlier",
    "keep_current_process",
    "add_specific_reflection_evidence",
    "repeat_productive_ai_revision",
    "reduce_ai_share_and_deepen_revision",
]
ProfileMetricKey = Literal[
    "total_chars",
    "normalized_score",
    "process_index",
    "collaboration_index",
    "revision_depth",
    "active_writing_seconds",
    "end_loaded_ratio",
    "deadline_window_ratio",
    "ai_ratio",
    "digestion_ratio",
    "prompt_count",
    "reflection_quality",
]
ProfileFormulaMetric = Literal[
    "revised_chars / inserted_chars",
    "writing_span_seconds",
    "end_loaded_ratio",
    "digestion_ratio",
    "prompt_count",
    "reflection_quality",
]


class StrictProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileEvidenceAssignmentContext(StrictProfileModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    classroom_id: Optional[str] = None
    score_max: int = Field(gt=0, le=10000)
    rubric_schema: RubricSchema
    assignment_due_at: Optional[int] = Field(default=None, ge=0)
    effective_due_at: Optional[int] = Field(default=None, ge=0)


class ProfileEvidenceDocument(StrictProfileModel):
    final_version_id: str = Field(min_length=1)
    content_text: str
    content_json: Optional[dict[str, Any]] = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProfileEvidenceVersionEvent(StrictProfileModel):
    id: str = Field(min_length=1)
    version_no: int = Field(ge=1)
    trigger_type: str = Field(min_length=1, max_length=40)
    content_text: str
    content_json: Optional[dict[str, Any]] = None
    created_at: int = Field(ge=0)


class ProfileEvidenceEditorEvent(StrictProfileModel):
    id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    op_type: str = Field(min_length=1, max_length=40)
    source_type: str = Field(min_length=1, max_length=40)
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, ge=0)
    inserted_text: Optional[str] = None
    deleted_text: Optional[str] = None
    batch_id: str = Field(min_length=1)
    occurred_at_ms: int = Field(ge=0)
    client_sequence: int = Field(ge=0)
    metadata_json: Optional[dict[str, Any]] = None
    created_at: int = Field(ge=0)


class ProfileEvidenceProvenanceEvent(StrictProfileModel):
    id: str = Field(min_length=1)
    version_id: Optional[str] = None
    source_type: str = Field(min_length=1, max_length=40)
    source_message_id: Optional[str] = None
    segment_id: str = Field(min_length=1)
    segment_text: str
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, ge=0)
    metadata_json: Optional[dict[str, Any]] = None
    created_at: int = Field(ge=0)


class ProfileEvidenceConversationEvent(StrictProfileModel):
    id: str = Field(min_length=1)
    role: Literal["user", "assistant", "system", "tool"]
    content: Any
    created_at: int = Field(ge=0)
    parent_id: Optional[str] = None
    model_id: Optional[str] = None
    output: Any = None
    usage: Optional[dict[str, Any]] = None


class ProfileEvidenceReflection(StrictProfileModel):
    id: str = Field(min_length=1)
    ai_used: bool
    ai_help_types: list[AIHelpType] = Field(default_factory=list)
    reflection: StructuredReflection
    created_at: int = Field(ge=0)


class ProfileEvidenceCaptureStream(StrictProfileModel):
    status: Literal["complete", "missing"]
    observed_count: int = Field(ge=0)
    missing_reason: Optional[str] = Field(default=None, max_length=200)


class ProfileEvidenceCaptureManifest(StrictProfileModel):
    collector_version: str = Field(min_length=1, max_length=80)
    application_build: str = Field(min_length=1, max_length=200)
    captured_from_at: int = Field(ge=0)
    captured_until_at: int = Field(ge=0)
    version_window_started_at: int = Field(ge=0)
    version_data: ProfileEvidenceCaptureStream
    editor_operations: ProfileEvidenceCaptureStream
    source_tracking: ProfileEvidenceCaptureStream
    conversation: ProfileEvidenceCaptureStream

    @model_validator(mode="after")
    def validate_capture_window(self):
        if self.captured_until_at < self.captured_from_at:
            raise ValueError("captured_until_at must not precede captured_from_at")
        if (
            not self.captured_from_at
            <= self.version_window_started_at
            <= self.captured_until_at
        ):
            raise ValueError(
                "version_window_started_at must be inside the capture window"
            )
        return self


class ProfileEvidencePreviousRound(StrictProfileModel):
    submission_id: str = Field(min_length=1)
    round_no: int = Field(ge=1)
    final_content_text: str
    submitted_at: int = Field(ge=0)
    reviewed_at: Optional[int] = Field(default=None, ge=0)
    score: Optional[int] = Field(default=None, ge=0)
    review_status: Optional[Literal["pending", "reviewed", "returned"]] = None
    rubric_scores: Optional[dict[str, int]] = None
    overall_comment: Optional[str] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = Field(default=None, ge=0)


class ProfileEvidenceCritique(StrictProfileModel):
    """写作前评析的事实,提交时已冻在 stats_json 里。

    只记做没做、命中几条。**不记分数、不记等级**——这个环节从设计上就不给分。
    """

    enabled: bool = False
    completed: bool = False
    hits: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class ProfileEvidenceChallenge(StrictProfileModel):
    """这一轮提交前读者试读的事实,提交时已冻在 stats_json 里。

    画像只读派生数据,不回读 challenge_session / challenge_turn 原表,所以这里
    的每一项都必须在提交那一刻就算好。
    """

    enabled: bool = False
    status: Optional[Literal["completed", "skipped"]] = None
    planned_rounds: int = Field(default=0, ge=0)
    answered_rounds: int = Field(default=0, ge=0)
    unresolved_count: int = Field(default=0, ge=0)
    focus_keys: list[str] = Field(default_factory=list)
    revised_after: Optional[bool] = None
    # 判的是位置不是字数:被质疑的几处里有几处动了。
    changed_spans: int = Field(default=0, ge=0)
    total_spans: int = Field(default=0, ge=0)


class ProfileEvidencePayload(StrictProfileModel):
    evidence_schema_version: Literal["2026-09-06.3"] = "2026-09-06.3"
    submission_id: str = Field(min_length=1)
    student_id: str = Field(min_length=1)
    assignment_id: str = Field(min_length=1)
    writing_session_id: str = Field(min_length=1)
    evidence_revision: int = Field(ge=1)
    round_no: int = Field(ge=1)
    submitted_at: int = Field(ge=0)
    previous_submission_id: Optional[str] = None
    previous_round: Optional[ProfileEvidencePreviousRound] = None
    assignment: ProfileEvidenceAssignmentContext
    document: ProfileEvidenceDocument
    versions: list[ProfileEvidenceVersionEvent]
    editor_operations: list[ProfileEvidenceEditorEvent]
    provenance: list[ProfileEvidenceProvenanceEvent]
    conversation: list[ProfileEvidenceConversationEvent]
    reflection: ProfileEvidenceReflection
    critique: ProfileEvidenceCritique = Field(
        default_factory=ProfileEvidenceCritique
    )
    challenge: ProfileEvidenceChallenge = Field(
        default_factory=ProfileEvidenceChallenge
    )
    capture_manifest: ProfileEvidenceCaptureManifest


class ProfileEvidenceSnapshotModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    submission_id: str
    evidence_revision: int
    evidence_schema_version: str
    student_id: str
    assignment_id: str
    round_no: int
    submitted_at: int
    evidence_json: ProfileEvidencePayload
    evidence_hash: str
    created_at: int


class StudentProfileDataCompleteness(StrictProfileModel):
    version_data: ProfileCompletenessStatus
    editor_operations: ProfileCompletenessStatus
    source_tracking: ProfileCompletenessStatus
    scoring: ProfileCompletenessStatus


class StudentProfileCompletenessSummary(StrictProfileModel):
    point_count: int = 0
    version_complete_count: int = 0
    version_missing_count: int = 0
    editor_operations_complete_count: int = 0
    editor_operations_missing_count: int = 0
    source_tracking_complete_count: int = 0
    source_tracking_missing_count: int = 0
    scoring_comparable_count: int = 0
    scoring_pending_count: int = 0
    scoring_not_applicable_count: int = 0
    scoring_missing_count: int = 0
    overall_ratio: Optional[float] = None


class StudentProfileAssignmentItem(StrictProfileModel):
    """作业维度的当前状态；未提交的作业也要出现,否则缺交信息会从画像里消失。"""

    assignment: AssignmentModel
    submission_id: Optional[str] = None
    submitted_at: Optional[int] = None
    round_no: Optional[int] = None
    review_status: ProfileReviewStatus = "unsubmitted"
    score: Optional[int] = None


class StudentProfileTimelinePoint(StrictProfileModel):
    """一次提交在成长画像里的三维快照(产出 / 过程 / AI 协作)。"""

    submission_id: str
    assignment_id: str
    assignment_title: str
    round_no: int = Field(default=1, ge=1)
    is_current: bool = True
    submitted_at: int = Field(ge=0)
    data_completeness: StudentProfileDataCompleteness

    # 产出维:保留教师评分原值，并用作业明确声明的满分生成可比较百分比。
    total_chars: int = Field(default=0, ge=0)
    score: Optional[int] = Field(default=None, ge=0)
    score_max: int = Field(gt=0, le=10000)
    normalized_score: Optional[float] = Field(default=None, ge=0, le=100)
    rubric: Optional[dict[str, int]] = None
    review_status: ProfileReviewStatus = "pending"

    # 过程维。不用版本数:一个版本 = 一次 1.2 秒防抖自动保存,衡量的是打字时长
    # 而不是「改了几版」,拿它当修改投入会被打字速度带偏。
    inserted_chars: Optional[int] = Field(default=None, ge=0)
    revised_chars: Optional[int] = Field(default=None, ge=0)
    revision_depth: Optional[int] = Field(default=None, ge=0, le=100)
    writing_span_seconds: Optional[int] = Field(default=None, ge=0)
    active_writing_seconds: Optional[int] = Field(default=None, ge=0)
    lead_time_seconds: Optional[int] = None
    end_loaded_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    deadline_window_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    process_index: Optional[int] = Field(default=None, ge=0, le=100)

    # AI 协作维
    typed_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    ai_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    unknown_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    prompt_count: Optional[int] = Field(default=None, ge=0)
    digestion_ratio: Optional[int] = Field(default=None, ge=0, le=100)
    reflection_char_count: int = Field(default=0, ge=0)
    reflection_quality: int = Field(default=0, ge=0, le=100)
    ai_help_types: list[AIHelpType] = Field(default_factory=list)
    collaboration_index: Optional[int] = Field(default=None, ge=0, le=100)

    # 面对质疑维。作业没开试读时全为 None——这是「不适用」,不是「表现差」,
    # 前端必须按缺数据呈现,不能拿它拉低任何汇总。
    challenge_status: Optional[Literal["completed", "skipped"]] = None
    challenge_answer_ratio: Optional[int] = Field(default=None, ge=0, le=100)
    challenge_unresolved_count: Optional[int] = Field(default=None, ge=0)
    challenge_revised: Optional[bool] = None
    critique_hit_ratio: Optional[int] = Field(default=None, ge=0, le=100)

    # 风险信号:只做展示,不参与任何成长指数。
    burst_count: Optional[int] = Field(default=None, ge=0)
    suspected_unmarked_import_count: Optional[int] = Field(default=None, ge=0)


class StudentProfileRoundProgress(StrictProfileModel):
    """退回—重交之间的改动幅度,是最直接的「响应反馈」证据。"""

    assignment_id: str
    assignment_title: str
    from_round: int
    to_round: int
    char_delta: int = 0
    revision_ratio: int = 0
    score_delta: Optional[int] = None
    turnaround_seconds: Optional[int] = None
    comparison_scope: Literal["same_assignment_rounds"] = "same_assignment_rounds"


class StudentProfileMetricTrend(StrictProfileModel):
    key: ProfileMetricKey
    first: float
    last: float
    delta: float
    direction: ProfileTrendDirection = "flat"
    sample_count: int = 0
    comparison_scope: Literal["cross_assignment"] = "cross_assignment"


class StudentProfileInsightParams(StrictProfileModel):
    delta: Optional[float] = None
    last: Optional[float] = None
    digestion_ratio: Optional[int] = None
    ai_ratio: Optional[float] = None
    count: Optional[int] = None
    best_delta: Optional[float] = None
    revision_ratio: Optional[int] = None
    ratio: Optional[float] = None
    average_score: Optional[int] = None
    normalized_score: Optional[float] = None
    revision_depth: Optional[int] = None
    reflection_quality: Optional[int] = None
    score_delta: Optional[float] = None


class StudentProfileInsight(StrictProfileModel):
    """规则生成的结论;文案由前端按 code 走 i18n,后端不产出自然语言。"""

    code: ProfileInsightCode
    tone: ProfileInsightTone = "neutral"
    params: StudentProfileInsightParams = Field(
        default_factory=StudentProfileInsightParams
    )
    action_code: Optional[ProfileInsightActionCode] = None
    submission_id: Optional[str] = None
    severity: Literal["low", "medium", "high"] = "low"
    confidence: float = Field(default=0, ge=0, le=1)
    sample_count: int = Field(default=0, ge=0)
    data_completeness: float = Field(default=0, ge=0, le=1)
    teaching_value: int = Field(default=1, ge=1, le=5)
    priority_score: float = Field(default=0, ge=0)
    evidence_codes: list[
        Literal[
            "sample_size",
            "version_evidence",
            "editor_evidence",
            "source_evidence",
            "scoring_evidence",
            "reflection_evidence",
            "round_evidence",
        ]
    ] = Field(default_factory=list)


class StudentGrowthGoalCreateForm(StrictProfileModel):
    goal_text: str = Field(min_length=5, max_length=500)
    classroom_id: Optional[str] = None
    assignment_id: Optional[str] = None
    target_at: Optional[int] = Field(default=None, ge=0)

    @field_validator("goal_text", mode="before")
    @classmethod
    def strip_goal_text(cls, value: str) -> str:
        return value.strip()


class StudentGrowthGoalUpdateForm(StrictProfileModel):
    goal_text: Optional[str] = Field(default=None, min_length=5, max_length=500)
    target_at: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["active", "completed", "archived"]] = None

    @field_validator("goal_text", mode="before")
    @classmethod
    def strip_updated_goal_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_goal_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one goal field is required")
        if "goal_text" in self.model_fields_set and self.goal_text is None:
            raise ValueError("goal_text cannot be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class StudentGrowthGoalModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    student_id: str
    classroom_id: Optional[str] = None
    assignment_id: Optional[str] = None
    goal_text: str
    target_at: Optional[int] = None
    status: Literal["active", "completed", "archived"]
    created_at: int
    updated_at: int


class TeacherStudentNoteCreateForm(StrictProfileModel):
    content: str = Field(min_length=2, max_length=2000)
    observed_at: Optional[int] = Field(default=None, ge=0)

    @field_validator("content", mode="before")
    @classmethod
    def strip_note_content(cls, value: str) -> str:
        return value.strip()


class TeacherStudentNoteUpdateForm(StrictProfileModel):
    content: Optional[str] = Field(default=None, min_length=2, max_length=2000)
    observed_at: Optional[int] = Field(default=None, ge=0)

    @field_validator("content", mode="before")
    @classmethod
    def strip_updated_note_content(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_note_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one note field is required")
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("content cannot be null")
        if "observed_at" in self.model_fields_set and self.observed_at is None:
            raise ValueError("observed_at cannot be null")
        return self


class TeacherStudentNoteModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    teacher_id: str
    classroom_id: str
    student_id: str
    content: str
    observed_at: int
    edited_at: Optional[int] = None
    created_at: int
    updated_at: int


class StudentProfilePortfolioSummary(StrictProfileModel):
    assignment_count: int = 0
    submitted_count: int = 0
    unsubmitted_count: int = 0
    reviewed_count: int = 0
    returned_count: int = 0
    average_score_percent: Optional[float] = None


class StudentProfileFilteredSummary(StrictProfileModel):
    point_count: int = 0
    assignment_count: int = 0
    reviewed_point_count: int = 0
    average_score_percent: Optional[float] = None


class StudentProfilePagination(StrictProfileModel):
    total: int = 0
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class StudentProfileHelpTypeSummary(StrictProfileModel):
    generative: int = 0
    refining: int = 0
    refining_ratio: Optional[float] = None


class StudentProfileHelpTypeShift(StrictProfileModel):
    early: StudentProfileHelpTypeSummary
    recent: StudentProfileHelpTypeSummary
    refining_ratio_delta: Optional[float] = None


class StudentProfileReflectionQuality(StrictProfileModel):
    count: int = 0
    average_score: Optional[int] = None
    average_chars: Optional[int] = None


class StudentProfileFormulaTerm(StrictProfileModel):
    metric: ProfileFormulaMetric
    weight: float
    target: Optional[float] = None
    inverted: bool = False


class StudentProfileProcessFormula(StrictProfileModel):
    revision_depth: StudentProfileFormulaTerm
    span_effort: StudentProfileFormulaTerm
    pacing: StudentProfileFormulaTerm


class StudentProfileCollaborationFormula(StrictProfileModel):
    digestion: StudentProfileFormulaTerm
    inquiry: StudentProfileFormulaTerm
    reflection: StudentProfileFormulaTerm
    no_ai_fallback_metric: Literal["reflection_quality"] = "reflection_quality"


class StudentProfileReflectionFormulaTerm(StrictProfileModel):
    target_chars: int
    max_score: int


class StudentProfileReflectionFormula(StrictProfileModel):
    action: StudentProfileReflectionFormulaTerm
    location: StudentProfileReflectionFormulaTerm
    judgement: StudentProfileReflectionFormulaTerm
    next_step: StudentProfileReflectionFormulaTerm


class StudentProfileIndexFormula(StrictProfileModel):
    process_index: StudentProfileProcessFormula
    collaboration_index: StudentProfileCollaborationFormula
    reflection_quality: StudentProfileReflectionFormula


class ProfileMetricProjectionPayload(StrictProfileModel):
    metric_version: str
    point: StudentProfileTimelinePoint
    round_progress: Optional[StudentProfileRoundProgress] = None


class SubmissionReviewEventModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    submission_id: str
    evidence_snapshot_id: str
    review_revision: int
    assignment_id: str
    reviewer_id: str
    review_status: Literal["pending", "reviewed", "returned"]
    score: Optional[int] = Field(default=None, ge=0)
    rubric_scores: Optional[dict[str, int]] = None
    overall_comment: Optional[str] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None
    reviewed_at: Optional[int] = None
    created_at: int


class ProfileMetricProjectionModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    evidence_snapshot_id: str
    submission_id: str
    student_id: str
    assignment_id: str
    round_no: int
    submitted_at: int
    review_revision: int
    metric_version: str
    projection_json: ProfileMetricProjectionPayload
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: Optional[str] = None
    generated_at: int


class StudentProfileAggregatePayload(StrictProfileModel):
    metric_version: str
    insight_version: str
    assignment_ids: list[str] = Field(default_factory=list)
    projection_count: int = Field(ge=0)
    cross_assignment_timeline: list[StudentProfileTimelinePoint] = Field(
        default_factory=list
    )
    round_progress: list[StudentProfileRoundProgress] = Field(default_factory=list)
    trends: list[StudentProfileMetricTrend] = Field(default_factory=list)
    ai_help_type_distribution: dict[AIHelpType, int] = Field(default_factory=dict)
    ai_help_type_shift: StudentProfileHelpTypeShift
    reflection_quality: StudentProfileReflectionQuality
    insights: list[StudentProfileInsight] = Field(default_factory=list)
    data_completeness: StudentProfileCompletenessSummary
    filtered_summary: StudentProfileFilteredSummary


class StudentProfileAggregateProjectionModel(StrictProfileModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    student_id: str
    scope_kind: Literal["global", "classroom"]
    scope_id: str
    metric_version: str
    aggregate_revision: int = Field(ge=1)
    projection_count: int
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    aggregate_json: StudentProfileAggregatePayload
    run_id: Optional[str] = None
    generated_at: int


class StudentProfileResponse(StrictProfileModel):
    metric_version: str
    active_metric_version: str
    insight_version: str
    aggregate_materialized: bool
    aggregate_revision: Optional[int] = None
    available_metric_versions: list[str] = Field(default_factory=list)
    excluded_snapshot_count: int = 0
    student_id: str
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    classrooms: list[ClassroomModel] = Field(default_factory=list)
    portfolio_summary: StudentProfilePortfolioSummary
    filtered_summary: StudentProfileFilteredSummary
    filters_applied: bool = False
    timeline_pagination: StudentProfilePagination
    assignments: list[StudentProfileAssignmentItem] = Field(default_factory=list)
    timeline: list[StudentProfileTimelinePoint] = Field(default_factory=list)
    cross_assignment_timeline: list[StudentProfileTimelinePoint] = Field(
        default_factory=list
    )
    round_progress: list[StudentProfileRoundProgress] = Field(default_factory=list)
    trends: list[StudentProfileMetricTrend] = Field(default_factory=list)
    ai_help_type_distribution: dict[AIHelpType, int] = Field(default_factory=dict)
    ai_help_type_shift: StudentProfileHelpTypeShift
    reflection_quality: StudentProfileReflectionQuality
    index_formula: StudentProfileIndexFormula
    insights: list[StudentProfileInsight] = Field(default_factory=list)
    data_completeness: StudentProfileCompletenessSummary
    growth_goals: list[StudentGrowthGoalModel] = Field(default_factory=list)


class TeacherStudentProfileResponse(StudentProfileResponse):
    teacher_notes: list[TeacherStudentNoteModel] = Field(default_factory=list)


class ClassroomBulkImportResult(BaseModel):
    added_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    added_users: list[str] = Field(default_factory=list)
    skipped_users: list[str] = Field(default_factory=list)
    failed_users: list[dict] = Field(default_factory=list)


class ClassroomProgressAssignmentItem(BaseModel):
    assignment: AssignmentModel
    submitted_count: int = 0
    unsubmitted_count: int = 0
    reviewed_count: int = 0
    pending_review_count: int = 0
    risk_summary: Optional[dict] = None


class ClassroomProgressResponse(BaseModel):
    classroom: ClassroomModel
    student_count: int = 0
    assignment_count: int = 0
    submitted_count: int = 0
    unsubmitted_count: int = 0
    reviewed_count: int = 0
    pending_review_count: int = 0
    risk_summary: Optional[dict] = None
    assignments: list[ClassroomProgressAssignmentItem] = Field(default_factory=list)


class EducationTable:
    @staticmethod
    def _generate_invite_code() -> str:
        return uuid.uuid4().hex[:8].upper()

    def insert_classroom(
        self,
        teacher_id: str,
        form_data: ClassroomCreateForm,
        db: Optional[Session] = None,
    ) -> ClassroomModel:
        with get_db_context(db) as db:
            classroom_name = form_data.name.strip()
            if not classroom_name:
                raise ValueError("Classroom name is required")
            existing = (
                db.query(Classroom)
                .filter(
                    Classroom.teacher_id == teacher_id,
                    Classroom.name == classroom_name,
                )
                .first()
            )
            if existing is not None:
                raise ValueError("Classroom name already exists")
            now = int(time.time())
            classroom = Classroom(
                id=str(uuid.uuid4()),
                name=classroom_name,
                teacher_id=teacher_id,
                invite_code=self._generate_invite_code(),
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(classroom)
            db.commit()
            db.refresh(classroom)
            self.ensure_classroom_member(classroom.id, teacher_id, "teacher", db=db)
            return ClassroomModel.model_validate(classroom)

    def get_classroom_by_id(
        self, classroom_id: str, db: Optional[Session] = None
    ) -> Optional[ClassroomModel]:
        with get_db_context(db) as db:
            classroom = db.get(Classroom, classroom_id)
            return ClassroomModel.model_validate(classroom) if classroom else None

    def get_classrooms_by_teacher(
        self, teacher_id: str, db: Optional[Session] = None
    ) -> list[ClassroomModel]:
        with get_db_context(db) as db:
            classrooms = (
                db.query(Classroom)
                .filter(Classroom.teacher_id == teacher_id)
                .order_by(Classroom.updated_at.desc(), Classroom.created_at.desc())
                .all()
            )
            return [
                ClassroomModel.model_validate(classroom) for classroom in classrooms
            ]

    def get_all_classrooms(self, db: Optional[Session] = None) -> list[ClassroomModel]:
        with get_db_context(db) as db:
            classrooms = (
                db.query(Classroom)
                .order_by(Classroom.updated_at.desc(), Classroom.created_at.desc())
                .all()
            )
            return [
                ClassroomModel.model_validate(classroom) for classroom in classrooms
            ]

    def get_classroom_by_invite_code(
        self, invite_code: str, db: Optional[Session] = None
    ) -> Optional[ClassroomModel]:
        with get_db_context(db) as db:
            classroom = (
                db.query(Classroom)
                .filter(Classroom.invite_code == invite_code.strip().upper())
                .first()
            )
            return ClassroomModel.model_validate(classroom) if classroom else None

    def regenerate_classroom_invite_code(
        self, classroom_id: str, db: Optional[Session] = None
    ) -> Optional[ClassroomModel]:
        with get_db_context(db) as db:
            classroom = db.get(Classroom, classroom_id)
            if classroom is None:
                return None

            classroom.invite_code = self._generate_invite_code()
            classroom.updated_at = int(time.time())
            db.commit()
            db.refresh(classroom)
            return ClassroomModel.model_validate(classroom)

    def ensure_classroom_member(
        self,
        classroom_id: str,
        user_id: str,
        member_role: str,
        db: Optional[Session] = None,
    ) -> ClassroomMemberModel:
        with get_db_context(db) as db:
            member = (
                db.query(ClassroomMember)
                .filter(
                    ClassroomMember.classroom_id == classroom_id,
                    ClassroomMember.user_id == user_id,
                )
                .first()
            )
            now = int(time.time())
            if member is None:
                member = ClassroomMember(
                    id=str(uuid.uuid4()),
                    classroom_id=classroom_id,
                    user_id=user_id,
                    member_role=member_role,
                    created_at=now,
                    updated_at=now,
                )
                db.add(member)
            else:
                member.member_role = member_role
                member.updated_at = now
            db.commit()
            db.refresh(member)
            return ClassroomMemberModel.model_validate(member)

    def get_classroom_member(
        self, classroom_id: str, user_id: str, db: Optional[Session] = None
    ) -> Optional[ClassroomMemberModel]:
        with get_db_context(db) as db:
            member = (
                db.query(ClassroomMember)
                .filter(
                    ClassroomMember.classroom_id == classroom_id,
                    ClassroomMember.user_id == user_id,
                )
                .first()
            )
            return ClassroomMemberModel.model_validate(member) if member else None

    def get_classroom_members(
        self,
        classroom_id: str,
        member_role: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[ClassroomMemberModel]:
        with get_db_context(db) as db:
            query = db.query(ClassroomMember).filter(
                ClassroomMember.classroom_id == classroom_id
            )
            if member_role is not None:
                query = query.filter(ClassroomMember.member_role == member_role)

            members = query.order_by(
                ClassroomMember.created_at.asc(), ClassroomMember.user_id.asc()
            ).all()
            return [ClassroomMemberModel.model_validate(member) for member in members]

    def get_classroom_member_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> Optional[ClassroomMemberModel]:
        with get_db_context(db) as db:
            member = (
                db.query(ClassroomMember)
                .filter(ClassroomMember.user_id == user_id)
                .order_by(ClassroomMember.created_at.asc())
                .first()
            )
            return ClassroomMemberModel.model_validate(member) if member else None

    def get_classroom_members_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[ClassroomMemberModel]:
        with get_db_context(db) as db:
            members = (
                db.query(ClassroomMember)
                .filter(ClassroomMember.user_id == user_id)
                .order_by(ClassroomMember.created_at.asc())
                .all()
            )
            return [ClassroomMemberModel.model_validate(member) for member in members]

    def delete_classroom_member(
        self, classroom_id: str, user_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            deleted = (
                db.query(ClassroomMember)
                .filter(
                    ClassroomMember.classroom_id == classroom_id,
                    ClassroomMember.user_id == user_id,
                )
                .delete()
            )
            db.commit()
            return deleted > 0

    def delete_classroom_memberships_by_user_id(
        self,
        user_id: str,
        member_role: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        """Drop every classroom membership a user holds, across all classrooms.

        ``member_role`` narrows the deletion to one kind of membership, which is
        how a teaching-identity change sheds the memberships that no longer
        match the account.
        """
        with get_db_context(db) as db:
            query = db.query(ClassroomMember).filter(
                ClassroomMember.user_id == user_id
            )
            if member_role is not None:
                query = query.filter(ClassroomMember.member_role == member_role)
            deleted = query.delete()
            db.commit()
            return deleted

    def update_assignment_classroom(
        self, assignment_id: str, classroom_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentModel]:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None:
                return None
            assignment.classroom_id = classroom_id
            assignment.updated_at = int(time.time())
            db.commit()
            db.refresh(assignment)
            return AssignmentModel.model_validate(assignment)

    def update_assignment(
        self,
        assignment_id: str,
        form_data: AssignmentUpdateForm,
        db: Optional[Session] = None,
    ) -> Optional[AssignmentModel]:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None:
                return None

            if "title" in form_data.model_fields_set:
                title = (form_data.title or "").strip()
                if not title:
                    raise ValueError("Assignment title is required")
                assignment.title = title
            if "description" in form_data.model_fields_set:
                assignment.description = (form_data.description or "").strip() or None
            if "classroom_id" in form_data.model_fields_set:
                classroom_id = (form_data.classroom_id or "").strip()
                if not classroom_id:
                    raise ValueError("classroom_id is required")
                assignment.classroom_id = classroom_id
            if "status" in form_data.model_fields_set:
                if form_data.status not in ASSIGNMENT_STATUSES:
                    raise ValueError("Invalid assignment status")
                assignment.status = form_data.status
                assignment.archived_at = (
                    int(time.time()) if form_data.status == "archived" else None
                )
            if "due_at" in form_data.model_fields_set:
                if form_data.due_at is None or form_data.due_at <= 0:
                    raise ValueError("Assignment due time is required")
                assignment.due_at = form_data.due_at
            if "score_max" in form_data.model_fields_set:
                if form_data.score_max is None or form_data.score_max <= 0:
                    raise ValueError("Assignment maximum score is required")
                assignment.score_max = form_data.score_max
            if "coaching_style" in form_data.model_fields_set:
                if form_data.coaching_style not in COACHING_STYLES:
                    raise ValueError("Invalid assignment coaching style")
                assignment.coaching_style = form_data.coaching_style
            if "rubric_schema" in form_data.model_fields_set:
                if form_data.rubric_schema is None:
                    raise ValueError("Assignment rubric is required")
                assignment.rubric_schema = form_data.rubric_schema.model_dump()
            if "challenge_enabled" in form_data.model_fields_set:
                if form_data.challenge_enabled is None:
                    raise ValueError("Challenge switch is required")
                assignment.challenge_enabled = form_data.challenge_enabled
            if "challenge_rounds" in form_data.model_fields_set:
                if form_data.challenge_rounds is None:
                    raise ValueError("Challenge rounds are required")
                assignment.challenge_rounds = form_data.challenge_rounds
            if "challenge_focus_keys" in form_data.model_fields_set:
                assignment.challenge_focus_keys = list(
                    form_data.challenge_focus_keys or []
                )
            # 焦点必须对着「本次更新后」的 rubric 与开关重新校验:任何一边动了都可能
            # 让原来的焦点失效(维度被删、质疑被打开但没选焦点)。
            assignment.challenge_focus_keys = validate_challenge_focus_keys(
                list(assignment.challenge_focus_keys or []),
                RubricSchema.model_validate(assignment.rubric_schema),
                bool(assignment.challenge_enabled),
            )

            if "critique_enabled" in form_data.model_fields_set:
                if form_data.critique_enabled is None:
                    raise ValueError("Critique switch is required")
                assignment.critique_enabled = form_data.critique_enabled
            if "critique_text" in form_data.model_fields_set:
                assignment.critique_text = form_data.critique_text
            if "critique_flaws" in form_data.model_fields_set:
                assignment.critique_flaws = [
                    flaw.model_dump() for flaw in (form_data.critique_flaws or [])
                ]
            # 与焦点同理：靶文漏洞绑的维度要对着更新后的 rubric 与开关重新校验。
            assignment.critique_text, assignment.critique_flaws = (
                validate_critique_config(
                    bool(assignment.critique_enabled),
                    assignment.critique_text,
                    list(assignment.critique_flaws or []),
                    RubricSchema.model_validate(assignment.rubric_schema),
                )
            )

            assignment.updated_at = int(time.time())
            db.commit()
            db.refresh(assignment)
            return AssignmentModel.model_validate(assignment)

    def archive_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentModel]:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None:
                return None

            assignment.status = "archived"
            assignment.archived_at = int(time.time())
            assignment.updated_at = assignment.archived_at
            db.commit()
            db.refresh(assignment)
            return AssignmentModel.model_validate(assignment)

    def insert_assignment(
        self,
        teacher_id: str,
        classroom_id: str,
        form_data: AssignmentCreateForm,
        db: Optional[Session] = None,
    ) -> AssignmentModel:
        with get_db_context(db) as db:
            now = int(time.time())
            assignment_title = form_data.title.strip()
            classroom_id = classroom_id.strip()
            if not classroom_id:
                raise ValueError("classroom_id is required")
            if not assignment_title:
                raise ValueError("Assignment title is required")
            if form_data.due_at is None or form_data.due_at <= 0:
                raise ValueError("Assignment due time is required")
            assignment = Assignment(
                id=str(uuid.uuid4()),
                title=assignment_title,
                description=form_data.description,
                teacher_id=teacher_id,
                classroom_id=classroom_id,
                status="active",
                due_at=form_data.due_at,
                score_max=form_data.score_max,
                coaching_style=form_data.coaching_style,
                critique_enabled=form_data.critique_enabled,
                critique_text=form_data.critique_text,
                critique_flaws=[flaw.model_dump() for flaw in form_data.critique_flaws],
                challenge_enabled=form_data.challenge_enabled,
                challenge_rounds=form_data.challenge_rounds,
                challenge_focus_keys=list(form_data.challenge_focus_keys),
                rubric_schema=form_data.rubric_schema.model_dump(),
                archived_at=None,
                created_at=now,
                updated_at=now,
            )
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            return AssignmentModel.model_validate(assignment)

    def get_assignment_by_id(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentModel]:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            return AssignmentModel.model_validate(assignment) if assignment else None

    def get_writing_sessions_by_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> list[WritingSessionModel]:
        with get_db_context(db) as db:
            sessions = (
                db.query(WritingSession)
                .filter(WritingSession.assignment_id == assignment_id)
                .all()
            )
            return [WritingSessionModel.model_validate(session) for session in sessions]

    def delete_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None:
                return False
            db.delete(assignment)
            db.commit()
            return True

    def delete_assignment_notifications(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> int:
        with get_db_context(db) as db:
            rows = (
                db.query(EducationNotification)
                .filter(
                    EducationNotification.type.in_(
                        [
                            "assignment_published",
                            "assignment_updated",
                            "assignment_reminder",
                            "assignment_extension_granted",
                            "assignment_extension_revoked",
                        ]
                    )
                )
                .all()
            )
            deleted = 0
            for row in rows:
                payload = row.payload_json or {}
                if payload.get("assignment_id") == assignment_id:
                    db.delete(row)
                    deleted += 1
            db.commit()
            return deleted

    def get_assignment_extension(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentExtensionModel]:
        with get_db_context(db) as db:
            extension = (
                db.query(AssignmentExtension)
                .filter(
                    AssignmentExtension.assignment_id == assignment_id,
                    AssignmentExtension.student_id == student_id,
                )
                .first()
            )
            return (
                AssignmentExtensionModel.model_validate(extension)
                if extension
                else None
            )

    def get_assignment_extensions(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> dict[str, AssignmentExtensionModel]:
        """一个作业下的全部个人延期,按 student_id 索引,供名单页一次取齐。"""
        with get_db_context(db) as db:
            extensions = (
                db.query(AssignmentExtension)
                .filter(AssignmentExtension.assignment_id == assignment_id)
                .all()
            )
            return {
                extension.student_id: AssignmentExtensionModel.model_validate(extension)
                for extension in extensions
            }

    def upsert_assignment_extension(
        self,
        assignment_id: str,
        student_id: str,
        granted_by: str,
        form_data: AssignmentExtensionForm,
        db: Optional[Session] = None,
    ) -> AssignmentExtensionModel:
        with get_db_context(db) as db:
            now = int(time.time())
            extension = (
                db.query(AssignmentExtension)
                .filter(
                    AssignmentExtension.assignment_id == assignment_id,
                    AssignmentExtension.student_id == student_id,
                )
                .first()
            )
            if extension is None:
                extension = AssignmentExtension(
                    id=str(uuid.uuid4()),
                    assignment_id=assignment_id,
                    student_id=student_id,
                    due_at=form_data.due_at,
                    reason=form_data.reason,
                    granted_by=granted_by,
                    created_at=now,
                    updated_at=now,
                )
                db.add(extension)
            else:
                extension.due_at = form_data.due_at
                extension.reason = form_data.reason
                extension.granted_by = granted_by
                extension.updated_at = now
            db.commit()
            db.refresh(extension)
            return AssignmentExtensionModel.model_validate(extension)

    def delete_assignment_extension(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            extension = (
                db.query(AssignmentExtension)
                .filter(
                    AssignmentExtension.assignment_id == assignment_id,
                    AssignmentExtension.student_id == student_id,
                )
                .first()
            )
            if extension is None:
                return False
            db.delete(extension)
            db.commit()
            return True

    def get_assignments_by_classroom(
        self, classroom_id: str, db: Optional[Session] = None
    ) -> list[AssignmentModel]:
        with get_db_context(db) as db:
            assignments = (
                db.query(Assignment)
                .filter(Assignment.classroom_id == classroom_id)
                .order_by(Assignment.updated_at.desc())
                .all()
            )
            return [
                AssignmentModel.model_validate(assignment) for assignment in assignments
            ]

    def get_assignments_by_teacher(
        self, teacher_id: str, db: Optional[Session] = None
    ) -> list[AssignmentModel]:
        with get_db_context(db) as db:
            assignments = (
                db.query(Assignment)
                .filter(Assignment.teacher_id == teacher_id)
                .order_by(Assignment.updated_at.desc(), Assignment.created_at.desc())
                .all()
            )
            return [
                AssignmentModel.model_validate(assignment) for assignment in assignments
            ]

    def get_assignments_by_student(
        self, student_id: str, db: Optional[Session] = None
    ) -> list[AssignmentModel]:
        with get_db_context(db) as db:
            classroom_ids = [
                member.classroom_id
                for member in self.get_classroom_members_by_user_id(student_id, db=db)
                if member.member_role == "student"
            ]
            if not classroom_ids:
                return []
            assignments = (
                db.query(Assignment)
                .filter(
                    Assignment.classroom_id.in_(classroom_ids),
                )
                .order_by(Assignment.updated_at.desc(), Assignment.id.asc())
                .all()
            )
            return [
                AssignmentModel.model_validate(assignment) for assignment in assignments
            ]

    def get_writing_session_by_id(
        self, session_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            return WritingSessionModel.model_validate(session) if session else None

    def get_assignment_writing_session(
        self, assignment_id: str, owner_user_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(WritingSession)
                .filter(
                    WritingSession.assignment_id == assignment_id,
                    WritingSession.owner_user_id == owner_user_id,
                    WritingSession.scope == "assignment",
                )
                .first()
            )
            return WritingSessionModel.model_validate(session) if session else None

    def get_personal_writing_session(
        self, session_id: str, owner_user_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(WritingSession)
                .filter(
                    WritingSession.id == session_id,
                    WritingSession.owner_user_id == owner_user_id,
                    WritingSession.scope == "personal",
                )
                .first()
            )
            return WritingSessionModel.model_validate(session) if session else None

    def get_writing_session_by_chat_id(
        self, chat_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(WritingSession)
                .filter(
                    (WritingSession.chat_id == chat_id)
                    | (WritingSession.active_chat_id == chat_id)
                )
                .first()
            )
            return WritingSessionModel.model_validate(session) if session else None

    def get_writing_session_by_folder_id(
        self, folder_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(WritingSession)
                .filter(WritingSession.folder_id == folder_id)
                .first()
            )
            return WritingSessionModel.model_validate(session) if session else None

    def get_writing_sessions_by_owner(
        self, owner_user_id: str, db: Optional[Session] = None
    ) -> list[WritingSessionModel]:
        with get_db_context(db) as db:
            sessions = (
                db.query(WritingSession)
                .filter(WritingSession.owner_user_id == owner_user_id)
                .order_by(
                    WritingSession.updated_at.desc(), WritingSession.created_at.desc()
                )
                .all()
            )
            return [WritingSessionModel.model_validate(session) for session in sessions]

    def insert_writing_session(
        self,
        assignment_id: Optional[str],
        owner_user_id: str,
        scope: str,
        note_id: str,
        folder_id: Optional[str],
        chat_id: Optional[str],
        active_chat_id: Optional[str] = None,
        status: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> WritingSessionModel:
        with get_db_context(db) as db:
            now = int(time.time())
            session = WritingSession(
                id=session_id or str(uuid.uuid4()),
                assignment_id=assignment_id,
                owner_user_id=owner_user_id,
                scope=scope,
                note_id=note_id,
                folder_id=folder_id,
                chat_id=chat_id,
                active_chat_id=active_chat_id,
                status=status or ("active" if scope == "personal" else "draft"),
                submitted_submission_id=None,
                created_at=now,
                updated_at=now,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return WritingSessionModel.model_validate(session)

    def update_writing_session_context(
        self,
        session_id: str,
        *,
        folder_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        active_chat_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            if session is None:
                return None

            if folder_id is not None:
                session.folder_id = folder_id
            session.chat_id = chat_id
            session.active_chat_id = active_chat_id
            session.updated_at = int(time.time())
            db.commit()
            db.refresh(session)
            return WritingSessionModel.model_validate(session)

    def touch_writing_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            if session is None:
                return None
            session.updated_at = int(time.time())
            if status is not None:
                session.status = status
            db.commit()
            db.refresh(session)
            return WritingSessionModel.model_validate(session)

    async def delete_personal_writing_session(
        self, session_id: str, owner_user_id: str, db: Optional[Session] = None
    ) -> Optional[dict]:
        # Phase 1 (sync session): look up the writing session, collect the ids
        # the async cleanup needs, delete the rows owned by this table, and
        # COMMIT before any async table call. The async Chats/Folders/Notes
        # methods cannot reuse this sync Session (they require an AsyncSession),
        # so they open their own connection to the same database; holding this
        # sync write transaction open across those calls self-deadlocks sqlite
        # ("database is locked") and their deletes silently do nothing.
        related_folder_ids: list[str] = []
        with get_db_context(db) as sync_db:
            session = (
                sync_db.query(WritingSession)
                .filter(
                    WritingSession.id == session_id,
                    WritingSession.owner_user_id == owner_user_id,
                    WritingSession.scope == "personal",
                )
                .first()
            )
            if session is None:
                return None

            folder_id = session.folder_id
            chat_id = session.chat_id
            note_id = session.note_id

            if folder_id:
                from open_webui.models.folders import Folder

                related_folder_ids = list(
                    {
                        folder.id
                        for folder in sync_db.query(Folder)
                        .filter_by(user_id=owner_user_id)
                        .all()
                        if ((folder.meta or {}).get("writing_session_id") == session.id)
                    }
                    | {folder_id}
                )

            sync_db.query(WritingVersion).filter(
                WritingVersion.writing_session_id == session.id
            ).delete(synchronize_session=False)
            sync_db.query(ProvenanceSegment).filter(
                ProvenanceSegment.writing_session_id == session.id
            ).delete(synchronize_session=False)
            sync_db.delete(session)
            sync_db.commit()

        # Phase 2 (async sessions): clean up related chats, folders, and the
        # note through the async table APIs now that no sync write lock is
        # held on the database. Known tradeoff: the session row is already
        # committed away, so a failure below leaves orphaned chats/folders/note
        # behind with no retry or repair path — accepted for personal writing.
        deleted_chat_ids: list[str] = []
        deleted_folder_ids: list[str] = []

        if related_folder_ids:
            from open_webui.models.chats import Chats
            from open_webui.models.folders import Folders

            for related_folder_id in related_folder_ids:
                deleted_chat_ids.extend(
                    chat.id
                    for chat in await Chats.get_chats_by_folder_id_and_user_id(
                        related_folder_id,
                        owner_user_id,
                        skip=0,
                        limit=None,
                    )
                )
                await Chats.delete_chats_by_user_id_and_folder_id(
                    owner_user_id, related_folder_id
                )
                deleted_folder_ids.extend(
                    await Folders.delete_folder_by_id_and_user_id(
                        related_folder_id, owner_user_id
                    )
                )

            deleted_folder_ids = list(dict.fromkeys(deleted_folder_ids))
            deleted_chat_ids = list(dict.fromkeys(deleted_chat_ids))
        elif chat_id:
            from open_webui.models.chats import Chats

            deleted_chat_ids = [chat_id]
            await Chats.delete_chat_by_id_and_user_id(chat_id, owner_user_id)

        if note_id:
            from open_webui.models.notes import Notes

            await Notes.delete_note_by_id(note_id)

        return {
            "session_id": session_id,
            "project_id": folder_id,
            "deleted_folder_ids": deleted_folder_ids,
            "deleted_chat_ids": deleted_chat_ids,
        }

    def insert_version(
        self,
        session_id: str,
        trigger_type: str,
        content_json: Optional[dict],
        content_text: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> WritingVersionModel:
        with get_db_context(db) as db:
            version_count = (
                db.query(WritingVersion)
                .filter(WritingVersion.writing_session_id == session_id)
                .count()
            )
            version = WritingVersion(
                id=str(uuid.uuid4()),
                writing_session_id=session_id,
                version_no=version_count + 1,
                note_snapshot_json=content_json,
                note_snapshot_text=content_text,
                trigger_type=trigger_type,
                created_at=int(time.time()),
            )
            db.add(version)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(version)
            return WritingVersionModel.model_validate(version)

    def get_versions(
        self, session_id: str, db: Optional[Session] = None
    ) -> list[WritingVersionModel]:
        with get_db_context(db) as db:
            versions = (
                db.query(WritingVersion)
                .filter(WritingVersion.writing_session_id == session_id)
                .order_by(WritingVersion.version_no.asc())
                .all()
            )
            return [WritingVersionModel.model_validate(version) for version in versions]

    def get_submission_window_versions(
        self,
        session_id: str,
        final_version_id: str,
        previous_final_version_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[WritingVersionModel]:
        with get_db_context(db) as db:
            final_version = db.get(WritingVersion, final_version_id)
            if (
                final_version is None
                or final_version.writing_session_id != session_id
            ):
                raise ValueError("Final writing version is missing from the session")
            previous_version_no = 0
            if previous_final_version_id is not None:
                previous_version = db.get(WritingVersion, previous_final_version_id)
                if (
                    previous_version is None
                    or previous_version.writing_session_id != session_id
                    or previous_version.version_no >= final_version.version_no
                ):
                    raise ValueError("Previous final version is invalid")
                previous_version_no = previous_version.version_no
            versions = (
                db.query(WritingVersion)
                .filter(
                    WritingVersion.writing_session_id == session_id,
                    WritingVersion.version_no > previous_version_no,
                    WritingVersion.version_no <= final_version.version_no,
                )
                .order_by(WritingVersion.version_no.asc())
                .all()
            )
            return [
                WritingVersionModel.model_validate(version) for version in versions
            ]

    def count_versions(
        self, session_id: str, db: Optional[Session] = None
    ) -> int:
        with get_db_context(db) as db:
            return (
                db.query(WritingVersion)
                .filter(WritingVersion.writing_session_id == session_id)
                .count()
            )

    def get_versions_by_session_ids(
        self, session_ids: list[str], db: Optional[Session] = None
    ) -> dict[str, list[WritingVersionModel]]:
        if not session_ids:
            return {}
        with get_db_context(db) as db:
            versions = (
                db.query(WritingVersion)
                .filter(WritingVersion.writing_session_id.in_(session_ids))
                .order_by(
                    WritingVersion.writing_session_id.asc(),
                    WritingVersion.version_no.asc(),
                )
                .all()
            )
            grouped: dict[str, list[WritingVersionModel]] = {}
            for version in versions:
                grouped.setdefault(version.writing_session_id, []).append(
                    WritingVersionModel.model_validate(version)
                )
            return grouped

    def get_version_by_id(
        self, version_id: str, db: Optional[Session] = None
    ) -> Optional[WritingVersionModel]:
        with get_db_context(db) as db:
            version = db.get(WritingVersion, version_id)
            return WritingVersionModel.model_validate(version) if version else None

    def get_latest_version(
        self, session_id: str, db: Optional[Session] = None
    ) -> Optional[WritingVersionModel]:
        with get_db_context(db) as db:
            version = (
                db.query(WritingVersion)
                .filter(WritingVersion.writing_session_id == session_id)
                .order_by(WritingVersion.version_no.desc())
                .first()
            )
            return WritingVersionModel.model_validate(version) if version else None

    def insert_provenance_segments(
        self,
        session_id: str,
        segments: list[ProvenanceSegmentInput],
        version_id: Optional[str] = None,
        replace_existing: bool = False,
        db: Optional[Session] = None,
    ) -> list[ProvenanceSegmentModel]:
        with get_db_context(db) as db:
            if replace_existing:
                db.query(ProvenanceSegment).filter(
                    ProvenanceSegment.writing_session_id == session_id
                ).delete()
            records = []
            for segment in segments:
                existing = None
                if not replace_existing:
                    existing = (
                        db.query(ProvenanceSegment)
                        .filter(
                            ProvenanceSegment.writing_session_id == session_id,
                            ProvenanceSegment.segment_id == segment.segment_id,
                        )
                        .first()
                    )
                if existing is not None:
                    existing.version_id = version_id or existing.version_id
                    existing.source_type = segment.source_type
                    existing.source_message_id = segment.source_message_id
                    existing.segment_text = segment.segment_text
                    existing.start_offset = segment.start_offset
                    existing.end_offset = segment.end_offset
                    existing.metadata_json = segment.metadata_json
                    records.append(existing)
                    continue

                record = ProvenanceSegment(
                    id=str(uuid.uuid4()),
                    writing_session_id=session_id,
                    version_id=version_id,
                    source_type=segment.source_type,
                    source_message_id=segment.source_message_id,
                    segment_id=segment.segment_id,
                    segment_text=segment.segment_text,
                    start_offset=segment.start_offset,
                    end_offset=segment.end_offset,
                    metadata_json=segment.metadata_json,
                    created_at=int(time.time()),
                )
                db.add(record)
                records.append(record)

            db.commit()
            return [ProvenanceSegmentModel.model_validate(record) for record in records]

    def get_provenance_segments(
        self, session_id: str, db: Optional[Session] = None
    ) -> list[ProvenanceSegmentModel]:
        with get_db_context(db) as db:
            segments = (
                db.query(ProvenanceSegment)
                .filter(ProvenanceSegment.writing_session_id == session_id)
                .order_by(ProvenanceSegment.created_at.asc())
                .all()
            )
            return [
                ProvenanceSegmentModel.model_validate(segment) for segment in segments
            ]

    def insert_editor_operations(
        self,
        session_id: str,
        user_id: str,
        operations: list[EditorOperationInput],
        db: Optional[Session] = None,
    ) -> list[EditorOperationModel]:
        with get_db_context(db) as db:
            records = []
            now = int(time.time())
            for operation in operations:
                record = EditorOperation(
                    id=str(uuid.uuid4()),
                    writing_session_id=session_id,
                    user_id=user_id,
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
                    created_at=now,
                )
                db.add(record)
                records.append(record)

            db.commit()
            return [EditorOperationModel.model_validate(record) for record in records]

    def get_editor_operations(
        self, session_id: str, db: Optional[Session] = None
    ) -> list[EditorOperationModel]:
        with get_db_context(db) as db:
            operations = (
                db.query(EditorOperation)
                .filter(EditorOperation.writing_session_id == session_id)
                .order_by(
                    EditorOperation.occurred_at_ms.asc(),
                    EditorOperation.client_sequence.asc(),
                    EditorOperation.id.asc(),
                )
                .all()
            )
            return [
                EditorOperationModel.model_validate(operation)
                for operation in operations
            ]

    def get_editor_operation_marks_by_session_ids(
        self, session_ids: list[str], db: Optional[Session] = None
    ) -> dict[str, list[int]]:
        """只取操作时间戳:画像的「有效写作时长」只需要时间轴,不需要正文。"""
        if not session_ids:
            return {}
        with get_db_context(db) as db:
            rows = (
                db.query(
                    EditorOperation.writing_session_id,
                    EditorOperation.occurred_at_ms,
                )
                .filter(EditorOperation.writing_session_id.in_(session_ids))
                .order_by(EditorOperation.occurred_at_ms.asc())
                .all()
            )
            grouped: dict[str, list[int]] = {}
            for session_id, occurred_at_ms in rows:
                grouped.setdefault(session_id, []).append(occurred_at_ms // 1000)
            return grouped

    def upsert_analysis_result(
        self,
        session_id: str,
        result_type: str,
        payload_json: dict,
        submission_id: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> AnalysisResultModel:
        with get_db_context(db) as db:
            query = db.query(AnalysisResult).filter(
                AnalysisResult.writing_session_id == session_id,
                AnalysisResult.result_type == result_type,
            )
            query = query.filter(AnalysisResult.submission_id == submission_id)
            result = query.first()
            now = int(time.time())
            if result is None:
                result = AnalysisResult(
                    id=str(uuid.uuid4()),
                    writing_session_id=session_id,
                    submission_id=submission_id,
                    result_type=result_type,
                    payload_json=payload_json,
                    created_at=now,
                    updated_at=now,
                )
                db.add(result)
            else:
                result.submission_id = submission_id
                result.payload_json = payload_json
                result.updated_at = now

            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(result)
            return AnalysisResultModel.model_validate(result)

    def get_analysis_result(
        self,
        session_id: str,
        result_type: str,
        submission_id: str,
        db: Optional[Session] = None,
    ) -> Optional[AnalysisResultModel]:
        with get_db_context(db) as db:
            query = db.query(AnalysisResult).filter(
                AnalysisResult.writing_session_id == session_id,
                AnalysisResult.result_type == result_type,
            )
            query = query.filter(AnalysisResult.submission_id == submission_id)
            result = query.first()
            return AnalysisResultModel.model_validate(result) if result else None

    def insert_micro_reflection(
        self,
        assignment_id: str,
        student_id: str,
        writing_session_id: str,
        ai_used: bool,
        ai_help_types: list[AIHelpType],
        reflection: StructuredReflection,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> MicroReflectionModel:
        with get_db_context(db) as db:
            reflection = MicroReflection(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                writing_session_id=writing_session_id,
                ai_used=ai_used,
                ai_help_types=ai_help_types,
                reflection_json=reflection.model_dump(),
                created_at=int(time.time()),
            )
            db.add(reflection)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(reflection)
            return MicroReflectionModel.model_validate(reflection)

    def get_micro_reflection_by_id(
        self, reflection_id: str, db: Optional[Session] = None
    ) -> Optional[MicroReflectionModel]:
        with get_db_context(db) as db:
            reflection = db.get(MicroReflection, reflection_id)
            return (
                MicroReflectionModel.model_validate(reflection) if reflection else None
            )

    def resolve_next_submission_round_no(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> int:
        """下一次提交会落在第几轮。

        与 insert_submission 的开轮逻辑保持一致:首轮为 1,退回后重交开新轮,
        当前轮还没批改就仍是这一轮(覆盖式重交)。质疑按轮绑定,一轮只质疑一次。
        """

        with get_db_context(db) as db:
            current = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.round_no.desc())
                .first()
            )
            if current is None:
                return 1
            review = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id == current.id)
                .first()
            )
            if review is not None and review.review_status == "returned":
                return current.round_no + 1
            return current.round_no

    def get_critique_attempt(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> Optional[CritiqueAttemptModel]:
        with get_db_context(db) as db:
            attempt = (
                db.query(CritiqueAttempt)
                .filter(
                    CritiqueAttempt.assignment_id == assignment_id,
                    CritiqueAttempt.student_id == student_id,
                )
                .first()
            )
            return CritiqueAttemptModel.model_validate(attempt) if attempt else None

    def insert_critique_attempt(
        self,
        assignment_id: str,
        student_id: str,
        items: list[str],
        matches: list[dict],
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> CritiqueAttemptModel:
        with get_db_context(db) as db:
            attempt = CritiqueAttempt(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                items_json=list(items),
                matches_json=list(matches),
                completed_at=int(time.time()),
            )
            db.add(attempt)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(attempt)
            return CritiqueAttemptModel.model_validate(attempt)

    def get_critique_attempts_by_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> list[CritiqueAttemptModel]:
        with get_db_context(db) as db:
            attempts = (
                db.query(CritiqueAttempt)
                .filter(CritiqueAttempt.assignment_id == assignment_id)
                .all()
            )
            return [
                CritiqueAttemptModel.model_validate(attempt) for attempt in attempts
            ]

    def get_challenge_insight(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> Optional[ChallengeInsightModel]:
        with get_db_context(db) as db:
            insight = (
                db.query(ChallengeInsight)
                .filter(ChallengeInsight.assignment_id == assignment_id)
                .first()
            )
            return ChallengeInsightModel.model_validate(insight) if insight else None

    def upsert_challenge_insight(
        self,
        assignment_id: str,
        input_hash: str,
        categories_json: dict,
        sample_size: int,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> ChallengeInsightModel:
        with get_db_context(db) as db:
            insight = (
                db.query(ChallengeInsight)
                .filter(ChallengeInsight.assignment_id == assignment_id)
                .first()
            )
            if insight is None:
                insight = ChallengeInsight(
                    id=str(uuid.uuid4()),
                    assignment_id=assignment_id,
                    input_hash=input_hash,
                    categories_json=categories_json,
                    sample_size=sample_size,
                    created_at=int(time.time()),
                )
                db.add(insight)
            else:
                insight.input_hash = input_hash
                insight.categories_json = categories_json
                insight.sample_size = sample_size
                insight.created_at = int(time.time())
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(insight)
            return ChallengeInsightModel.model_validate(insight)

    def insert_challenge_session(
        self,
        writing_session_id: str,
        assignment_id: str,
        student_id: str,
        submission_round_no: int,
        source_version_id: Optional[str],
        focus_keys: list[str],
        planned_rounds: int,
        status: str = "in_progress",
        followup_comment: Optional[str] = None,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> ChallengeSessionModel:
        """落一条质疑会话。

        status 传 `skipped` 用于「学生在契约页没点开始就跳过」——这种回避同样要留痕,
        否则最该被教师看到的那批学生反而是唯一没有记录的。
        """

        with get_db_context(db) as db:
            session = ChallengeSession(
                id=str(uuid.uuid4()),
                writing_session_id=writing_session_id,
                assignment_id=assignment_id,
                student_id=student_id,
                submission_round_no=submission_round_no,
                source_version_id=source_version_id,
                focus_keys=list(focus_keys),
                planned_rounds=planned_rounds,
                status=status,
                followup_comment=followup_comment,
                closing_summary_json=None,
                checklist_state_json=None,
                started_at=int(time.time()),
                ended_at=None if status == "in_progress" else int(time.time()),
            )
            db.add(session)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(session)
            return ChallengeSessionModel.model_validate(session)

    def get_challenge_session_by_id(
        self, session_id: str, db: Optional[Session] = None
    ) -> Optional[ChallengeSessionModel]:
        with get_db_context(db) as db:
            session = db.get(ChallengeSession, session_id)
            return ChallengeSessionModel.model_validate(session) if session else None

    def get_challenge_session_for_round(
        self,
        writing_session_id: str,
        submission_round_no: int,
        db: Optional[Session] = None,
    ) -> Optional[ChallengeSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(ChallengeSession)
                .filter(
                    ChallengeSession.writing_session_id == writing_session_id,
                    ChallengeSession.submission_round_no == submission_round_no,
                )
                .first()
            )
            return ChallengeSessionModel.model_validate(session) if session else None

    def get_challenge_turns(
        self, challenge_session_id: str, db: Optional[Session] = None
    ) -> list[ChallengeTurnModel]:
        with get_db_context(db) as db:
            turns = (
                db.query(ChallengeTurn)
                .filter(ChallengeTurn.challenge_session_id == challenge_session_id)
                .order_by(ChallengeTurn.turn_no.asc())
                .all()
            )
            return [ChallengeTurnModel.model_validate(turn) for turn in turns]

    def insert_challenge_turn(
        self,
        challenge_session_id: str,
        turn_no: int,
        focus_key: str,
        challenge_text: str,
        quoted_span: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> ChallengeTurnModel:
        with get_db_context(db) as db:
            turn = ChallengeTurn(
                id=str(uuid.uuid4()),
                challenge_session_id=challenge_session_id,
                turn_no=turn_no,
                focus_key=focus_key,
                challenge_text=challenge_text,
                quoted_span=quoted_span,
                response_text=None,
                responded_at=None,
                created_at=int(time.time()),
            )
            db.add(turn)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(turn)
            return ChallengeTurnModel.model_validate(turn)

    def record_challenge_response(
        self,
        challenge_session_id: str,
        turn_no: int,
        response_text: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> Optional[ChallengeTurnModel]:
        with get_db_context(db) as db:
            turn = (
                db.query(ChallengeTurn)
                .filter(
                    ChallengeTurn.challenge_session_id == challenge_session_id,
                    ChallengeTurn.turn_no == turn_no,
                )
                .first()
            )
            if turn is None:
                return None
            turn.response_text = response_text
            turn.responded_at = int(time.time())
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(turn)
            return ChallengeTurnModel.model_validate(turn)

    def complete_challenge_session(
        self,
        challenge_session_id: str,
        closing: ChallengeClosing,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> Optional[ChallengeSessionModel]:
        with get_db_context(db) as db:
            session = db.get(ChallengeSession, challenge_session_id)
            if session is None:
                return None
            session.status = "completed"
            session.closing_summary_json = closing.model_dump()
            session.ended_at = int(time.time())
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(session)
            return ChallengeSessionModel.model_validate(session)

    def skip_challenge_session(
        self,
        challenge_session_id: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> Optional[ChallengeSessionModel]:
        with get_db_context(db) as db:
            session = db.get(ChallengeSession, challenge_session_id)
            if session is None:
                return None
            session.status = "skipped"
            session.ended_at = int(time.time())
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(session)
            return ChallengeSessionModel.model_validate(session)

    def update_challenge_checklist(
        self,
        challenge_session_id: str,
        checked_indexes: list[int],
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> Optional[ChallengeSessionModel]:
        with get_db_context(db) as db:
            session = db.get(ChallengeSession, challenge_session_id)
            if session is None:
                return None
            session.checklist_state_json = {
                "checked_indexes": sorted(set(checked_indexes))
            }
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(session)
            return ChallengeSessionModel.model_validate(session)

    def get_analysis_results_by_submission_ids(
        self,
        submission_ids: list[str],
        result_type: str,
        db: Optional[Session] = None,
    ) -> dict[str, dict]:
        ids = [submission_id for submission_id in submission_ids if submission_id]
        if not ids:
            return {}
        with get_db_context(db) as db:
            rows = (
                db.query(AnalysisResult)
                .filter(
                    AnalysisResult.submission_id.in_(ids),
                    AnalysisResult.result_type == result_type,
                )
                .all()
            )
            return {row.submission_id: row.payload_json for row in rows}

    def insert_profile_evidence_snapshot(
        self,
        payload: ProfileEvidencePayload,
        evidence_hash: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> ProfileEvidenceSnapshotModel:
        """Append one immutable evidence revision for a successful submit attempt."""

        with get_db_context(db) as db:
            existing = (
                db.query(ProfileEvidenceSnapshot)
                .filter(
                    ProfileEvidenceSnapshot.submission_id == payload.submission_id,
                    ProfileEvidenceSnapshot.evidence_revision
                    == payload.evidence_revision,
                )
                .first()
            )
            if existing is not None:
                if existing.evidence_hash != evidence_hash:
                    raise ValueError("Evidence revision is immutable")
                return ProfileEvidenceSnapshotModel.model_validate(existing)

            snapshot = ProfileEvidenceSnapshot(
                id=str(uuid.uuid4()),
                submission_id=payload.submission_id,
                evidence_revision=payload.evidence_revision,
                evidence_schema_version=payload.evidence_schema_version,
                student_id=payload.student_id,
                assignment_id=payload.assignment_id,
                round_no=payload.round_no,
                submitted_at=payload.submitted_at,
                evidence_json=payload.model_dump(mode="json"),
                evidence_hash=evidence_hash,
                created_at=int(time.time()),
            )
            db.add(snapshot)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(snapshot)
            return ProfileEvidenceSnapshotModel.model_validate(snapshot)

    def get_next_profile_evidence_revision(
        self, submission_id: str, db: Optional[Session] = None
    ) -> int:
        with get_db_context(db) as db:
            current = (
                db.query(func.max(ProfileEvidenceSnapshot.evidence_revision))
                .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
                .scalar()
            )
            return int(current or 0) + 1

    def get_latest_profile_evidence_snapshot(
        self, submission_id: str, db: Optional[Session] = None
    ) -> Optional[ProfileEvidenceSnapshotModel]:
        with get_db_context(db) as db:
            row = (
                db.query(ProfileEvidenceSnapshot)
                .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
                .order_by(ProfileEvidenceSnapshot.evidence_revision.desc())
                .first()
            )
            return ProfileEvidenceSnapshotModel.model_validate(row) if row else None

    def get_profile_evidence_snapshots(
        self,
        *,
        student_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        after_id: Optional[str] = None,
        limit: int = 200,
        db: Optional[Session] = None,
    ) -> list[ProfileEvidenceSnapshotModel]:
        with get_db_context(db) as db:
            query = db.query(ProfileEvidenceSnapshot)
            if student_id is not None:
                query = query.filter(ProfileEvidenceSnapshot.student_id == student_id)
            if assignment_id is not None:
                query = query.filter(
                    ProfileEvidenceSnapshot.assignment_id == assignment_id
                )
            if after_id is not None:
                query = query.filter(ProfileEvidenceSnapshot.id > after_id)
            rows = query.order_by(ProfileEvidenceSnapshot.id.asc()).limit(limit).all()
            return [ProfileEvidenceSnapshotModel.model_validate(row) for row in rows]

    def _latest_profile_evidence_query(
        self,
        db: Session,
        *,
        student_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
    ):
        latest_revision = (
            db.query(
                ProfileEvidenceSnapshot.submission_id.label("submission_id"),
                func.max(ProfileEvidenceSnapshot.evidence_revision).label(
                    "evidence_revision"
                ),
            )
            .group_by(ProfileEvidenceSnapshot.submission_id)
            .subquery()
        )
        query = db.query(ProfileEvidenceSnapshot).join(
            latest_revision,
            and_(
                latest_revision.c.submission_id
                == ProfileEvidenceSnapshot.submission_id,
                latest_revision.c.evidence_revision
                == ProfileEvidenceSnapshot.evidence_revision,
            ),
        )
        if student_id is not None:
            query = query.filter(ProfileEvidenceSnapshot.student_id == student_id)
        if assignment_id is not None:
            query = query.filter(
                ProfileEvidenceSnapshot.assignment_id == assignment_id
            )
        return query

    def count_latest_profile_evidence_snapshots(
        self,
        *,
        student_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        with get_db_context(db) as db:
            return self._latest_profile_evidence_query(
                db,
                student_id=student_id,
                assignment_id=assignment_id,
            ).count()

    def get_latest_profile_evidence_batch(
        self,
        *,
        student_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        after_id: Optional[str] = None,
        limit: int = 200,
        db: Optional[Session] = None,
    ) -> list[ProfileEvidenceSnapshotModel]:
        with get_db_context(db) as db:
            query = self._latest_profile_evidence_query(
                db,
                student_id=student_id,
                assignment_id=assignment_id,
            )
            if after_id is not None:
                query = query.filter(ProfileEvidenceSnapshot.id > after_id)
            rows = query.order_by(ProfileEvidenceSnapshot.id.asc()).limit(limit).all()
            return [ProfileEvidenceSnapshotModel.model_validate(row) for row in rows]

    def append_submission_review_event(
        self,
        review: SubmissionReviewModel,
        evidence_snapshot_id: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> SubmissionReviewEventModel:
        with get_db_context(db) as db:
            revision = (
                db.query(func.max(SubmissionReviewEvent.review_revision))
                .filter(SubmissionReviewEvent.submission_id == review.submission_id)
                .scalar()
                or 0
            ) + 1
            event = SubmissionReviewEvent(
                id=str(uuid.uuid4()),
                submission_id=review.submission_id,
                evidence_snapshot_id=evidence_snapshot_id,
                review_revision=revision,
                assignment_id=review.assignment_id,
                reviewer_id=review.reviewer_id,
                review_status=review.review_status,
                score=review.score,
                rubric_scores=review.rubric_scores,
                overall_comment=review.overall_comment,
                returned_comment=review.returned_comment,
                resubmit_due_at=review.resubmit_due_at,
                reviewed_at=review.reviewed_at,
                created_at=int(time.time()),
            )
            db.add(event)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(event)
            return SubmissionReviewEventModel.model_validate(event)

    def get_latest_submission_review_event(
        self,
        submission_id: str,
        evidence_snapshot_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[SubmissionReviewEventModel]:
        with get_db_context(db) as db:
            query = db.query(SubmissionReviewEvent).filter(
                SubmissionReviewEvent.submission_id == submission_id
            )
            if evidence_snapshot_id is not None:
                query = query.filter(
                    SubmissionReviewEvent.evidence_snapshot_id == evidence_snapshot_id
                )
            row = query.order_by(SubmissionReviewEvent.review_revision.desc()).first()
            return SubmissionReviewEventModel.model_validate(row) if row else None

    def ensure_profile_algorithm_release(
        self,
        *,
        metric_version: str,
        insight_version: str,
        evidence_schema_version: str,
        formula_config: dict,
        code_commit_sha: str,
        code_checksum: str,
        created_by: str,
        db: Optional[Session] = None,
    ) -> None:
        with get_db_context(db) as db:
            existing = (
                db.query(ProfileAlgorithmRelease)
                .filter(ProfileAlgorithmRelease.metric_version == metric_version)
                .first()
            )
            if existing is not None:
                if (
                    existing.code_checksum != code_checksum
                    or existing.formula_config_json != formula_config
                ):
                    raise ValueError(
                        "Published profile algorithm releases are immutable"
                    )
                return
            now = int(time.time())
            has_active = (
                db.query(ProfileAlgorithmRelease.id)
                .filter(ProfileAlgorithmRelease.status == "active")
                .first()
                is not None
            )
            db.add(
                ProfileAlgorithmRelease(
                    id=str(uuid.uuid4()),
                    metric_version=metric_version,
                    insight_version=insight_version,
                    evidence_schema_versions=[evidence_schema_version],
                    formula_config_json=formula_config,
                    code_commit_sha=code_commit_sha,
                    code_checksum=code_checksum,
                    status="draft" if has_active else "active",
                    created_by=created_by,
                    created_at=now,
                    activated_at=None if has_active else now,
                )
            )
            db.flush()

    def get_active_profile_metric_version(
        self, db: Optional[Session] = None
    ) -> Optional[str]:
        with get_db_context(db) as db:
            row = (
                db.query(ProfileAlgorithmRelease.metric_version)
                .filter(ProfileAlgorithmRelease.status == "active")
                .order_by(ProfileAlgorithmRelease.activated_at.desc())
                .first()
            )
            return row[0] if row else None

    def get_profile_insight_version(
        self, metric_version: str, db: Optional[Session] = None
    ) -> Optional[str]:
        with get_db_context(db) as db:
            row = (
                db.query(ProfileAlgorithmRelease.insight_version)
                .filter(ProfileAlgorithmRelease.metric_version == metric_version)
                .first()
            )
            return row[0] if row else None

    def get_profile_formula_config(
        self, metric_version: str, db: Optional[Session] = None
    ) -> Optional[dict]:
        with get_db_context(db) as db:
            row = (
                db.query(ProfileAlgorithmRelease.formula_config_json)
                .filter(ProfileAlgorithmRelease.metric_version == metric_version)
                .first()
            )
            return row[0] if row else None

    def activate_profile_algorithm_release(
        self, metric_version: str, db: Optional[Session] = None
    ) -> None:
        with get_db_context(db) as db:
            release = (
                db.query(ProfileAlgorithmRelease)
                .filter(ProfileAlgorithmRelease.metric_version == metric_version)
                .first()
            )
            if release is None:
                raise ValueError("Profile algorithm release does not exist")
            db.query(ProfileAlgorithmRelease).filter(
                ProfileAlgorithmRelease.status == "active"
            ).update({"status": "retired"}, synchronize_session=False)
            release.status = "active"
            release.activated_at = int(time.time())
            db.flush()

    def insert_profile_metric_projection(
        self,
        evidence: ProfileEvidenceSnapshotModel,
        review_revision: int,
        metric_version: str,
        payload: ProfileMetricProjectionPayload,
        input_hash: str,
        output_hash: str,
        *,
        run_id: Optional[str] = None,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> ProfileMetricProjectionModel:
        if payload.metric_version != metric_version:
            raise ValueError("Projection payload version does not match its release")
        with get_db_context(db) as db:
            existing = (
                db.query(ProfileMetricProjection)
                .filter(
                    ProfileMetricProjection.evidence_snapshot_id == evidence.id,
                    ProfileMetricProjection.review_revision == review_revision,
                    ProfileMetricProjection.metric_version == metric_version,
                )
                .first()
            )
            if existing is not None:
                if (
                    existing.input_hash != input_hash
                    or existing.output_hash != output_hash
                ):
                    raise ValueError("Metric projection is immutable")
                return ProfileMetricProjectionModel.model_validate(existing)
            row = ProfileMetricProjection(
                id=str(uuid.uuid4()),
                evidence_snapshot_id=evidence.id,
                submission_id=evidence.submission_id,
                student_id=evidence.student_id,
                assignment_id=evidence.assignment_id,
                round_no=evidence.round_no,
                submitted_at=evidence.submitted_at,
                review_revision=review_revision,
                metric_version=metric_version,
                projection_json=payload.model_dump(mode="json"),
                input_hash=input_hash,
                output_hash=output_hash,
                run_id=run_id,
                generated_at=int(time.time()),
            )
            db.add(row)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(row)
            return ProfileMetricProjectionModel.model_validate(row)

    def insert_student_profile_aggregate_projection(
        self,
        *,
        student_id: str,
        scope_kind: Literal["global", "classroom"],
        scope_id: str,
        metric_version: str,
        input_hash: str,
        output_hash: str,
        payload: StudentProfileAggregatePayload,
        run_id: Optional[str] = None,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> StudentProfileAggregateProjectionModel:
        if payload.metric_version != metric_version:
            raise ValueError("Aggregate payload version does not match its release")
        with get_db_context(db) as db:
            existing = (
                db.query(StudentProfileAggregateProjection)
                .filter(
                    StudentProfileAggregateProjection.student_id == student_id,
                    StudentProfileAggregateProjection.scope_kind == scope_kind,
                    StudentProfileAggregateProjection.scope_id == scope_id,
                    StudentProfileAggregateProjection.metric_version == metric_version,
                    StudentProfileAggregateProjection.input_hash == input_hash,
                )
                .first()
            )
            if existing is not None:
                if existing.output_hash != output_hash:
                    raise ValueError("Aggregate projection is immutable")
                return StudentProfileAggregateProjectionModel.model_validate(existing)
            aggregate_revision = (
                db.query(
                    func.max(
                        StudentProfileAggregateProjection.aggregate_revision
                    )
                )
                .filter(
                    StudentProfileAggregateProjection.student_id == student_id,
                    StudentProfileAggregateProjection.scope_kind == scope_kind,
                    StudentProfileAggregateProjection.scope_id == scope_id,
                    StudentProfileAggregateProjection.metric_version == metric_version,
                )
                .scalar()
                or 0
            ) + 1
            row = StudentProfileAggregateProjection(
                id=str(uuid.uuid4()),
                student_id=student_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                metric_version=metric_version,
                aggregate_revision=aggregate_revision,
                projection_count=payload.projection_count,
                input_hash=input_hash,
                output_hash=output_hash,
                aggregate_json=payload.model_dump(mode="json"),
                run_id=run_id,
                generated_at=int(time.time()),
            )
            db.add(row)
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(row)
            return StudentProfileAggregateProjectionModel.model_validate(row)

    def get_latest_student_profile_aggregate_projection(
        self,
        *,
        student_id: str,
        scope_kind: Literal["global", "classroom"],
        scope_id: str,
        metric_version: str,
        db: Optional[Session] = None,
    ) -> Optional[StudentProfileAggregateProjectionModel]:
        with get_db_context(db) as db:
            row = (
                db.query(StudentProfileAggregateProjection)
                .filter(
                    StudentProfileAggregateProjection.student_id == student_id,
                    StudentProfileAggregateProjection.scope_kind == scope_kind,
                    StudentProfileAggregateProjection.scope_id == scope_id,
                    StudentProfileAggregateProjection.metric_version == metric_version,
                )
                .order_by(
                    StudentProfileAggregateProjection.aggregate_revision.desc(),
                )
                .first()
            )
            return (
                StudentProfileAggregateProjectionModel.model_validate(row)
                if row
                else None
            )

    def _latest_profile_projection_query(
        self,
        db: Session,
        student_id: str,
        metric_version: str,
    ):
        latest_evidence = (
            db.query(
                ProfileEvidenceSnapshot.submission_id.label("submission_id"),
                func.max(ProfileEvidenceSnapshot.evidence_revision).label(
                    "evidence_revision"
                ),
            )
            .group_by(ProfileEvidenceSnapshot.submission_id)
            .subquery()
        )
        latest_review = (
            db.query(
                ProfileMetricProjection.evidence_snapshot_id.label(
                    "evidence_snapshot_id"
                ),
                func.max(ProfileMetricProjection.review_revision).label(
                    "review_revision"
                ),
            )
            .filter(ProfileMetricProjection.metric_version == metric_version)
            .group_by(ProfileMetricProjection.evidence_snapshot_id)
            .subquery()
        )
        return (
            db.query(ProfileMetricProjection)
            .join(
                ProfileEvidenceSnapshot,
                ProfileEvidenceSnapshot.id
                == ProfileMetricProjection.evidence_snapshot_id,
            )
            .join(
                latest_evidence,
                and_(
                    latest_evidence.c.submission_id
                    == ProfileEvidenceSnapshot.submission_id,
                    latest_evidence.c.evidence_revision
                    == ProfileEvidenceSnapshot.evidence_revision,
                ),
            )
            .join(
                latest_review,
                and_(
                    latest_review.c.evidence_snapshot_id
                    == ProfileMetricProjection.evidence_snapshot_id,
                    latest_review.c.review_revision
                    == ProfileMetricProjection.review_revision,
                ),
            )
            .filter(
                ProfileMetricProjection.student_id == student_id,
                ProfileMetricProjection.metric_version == metric_version,
            )
        )

    def get_profile_metric_projections(
        self,
        student_id: str,
        metric_version: str,
        assignment_ids: Optional[list[str]] = None,
        start_at: Optional[int] = None,
        end_at: Optional[int] = None,
        round_no: Optional[int] = None,
        limit: Optional[int] = 200,
        offset: int = 0,
        db: Optional[Session] = None,
    ) -> list[ProfileMetricProjectionModel]:
        if assignment_ids is not None and not assignment_ids:
            return []
        with get_db_context(db) as db:
            query = self._latest_profile_projection_query(
                db, student_id, metric_version
            )
            if assignment_ids is not None:
                query = query.filter(
                    ProfileMetricProjection.assignment_id.in_(assignment_ids)
                )
            if start_at is not None:
                query = query.filter(ProfileMetricProjection.submitted_at >= start_at)
            if end_at is not None:
                query = query.filter(ProfileMetricProjection.submitted_at <= end_at)
            if round_no is not None:
                query = query.filter(ProfileMetricProjection.round_no == round_no)
            query = query.order_by(
                ProfileMetricProjection.submitted_at.asc(),
                ProfileMetricProjection.round_no.asc(),
                ProfileMetricProjection.id.asc(),
            ).offset(offset)
            if limit is not None:
                query = query.limit(limit)
            return [
                ProfileMetricProjectionModel.model_validate(row) for row in query.all()
            ]

    def count_profile_metric_projections(
        self,
        student_id: str,
        metric_version: str,
        assignment_ids: Optional[list[str]] = None,
        start_at: Optional[int] = None,
        end_at: Optional[int] = None,
        round_no: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> int:
        if assignment_ids is not None and not assignment_ids:
            return 0
        with get_db_context(db) as db:
            query = self._latest_profile_projection_query(
                db, student_id, metric_version
            )
            if assignment_ids is not None:
                query = query.filter(
                    ProfileMetricProjection.assignment_id.in_(assignment_ids)
                )
            if start_at is not None:
                query = query.filter(ProfileMetricProjection.submitted_at >= start_at)
            if end_at is not None:
                query = query.filter(ProfileMetricProjection.submitted_at <= end_at)
            if round_no is not None:
                query = query.filter(ProfileMetricProjection.round_no == round_no)
            return query.count()

    def get_profile_metric_versions(
        self,
        student_id: str,
        assignment_ids: Optional[list[str]] = None,
        db: Optional[Session] = None,
    ) -> list[str]:
        if assignment_ids is not None and not assignment_ids:
            return []
        with get_db_context(db) as db:
            query = db.query(ProfileMetricProjection.metric_version).filter(
                ProfileMetricProjection.student_id == student_id
            )
            if assignment_ids is not None:
                query = query.filter(
                    ProfileMetricProjection.assignment_id.in_(assignment_ids)
                )
            return sorted({row[0] for row in query.distinct().all()}, reverse=True)

    def get_micro_reflections_by_ids(
        self, reflection_ids: list[str], db: Optional[Session] = None
    ) -> dict[str, MicroReflectionModel]:
        ids = [reflection_id for reflection_id in reflection_ids if reflection_id]
        if not ids:
            return {}
        with get_db_context(db) as db:
            reflections = (
                db.query(MicroReflection).filter(MicroReflection.id.in_(ids)).all()
            )
            return {
                reflection.id: MicroReflectionModel.model_validate(reflection)
                for reflection in reflections
            }

    def insert_submission(
        self,
        assignment_id: str,
        student_id: str,
        writing_session_id: str,
        final_version_id: str,
        stats_json: dict,
        micro_reflection_id: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> SubmissionModel:
        with get_db_context(db) as db:
            now = int(time.time())
            current = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.round_no.desc())
                .first()
            )
            review = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id == current.id)
                .first()
                if current is not None
                else None
            )

            if review is not None and review.review_status == "reviewed":
                # 已批改即定稿:再开新轮会把该学生打回「待批改」,旧分数进历史轮
                # 后不再计入平均分。要让学生继续改,老师应显式退回。
                raise SubmissionAlreadyReviewedError(
                    "Submission has already been reviewed"
                )

            if current is None or (
                review is not None and review.review_status == "returned"
            ):
                # 首轮,或退回后的重交:开新轮,旧轮完整保留
                if current is not None:
                    current.is_current = 0
                submission = Submission(
                    id=str(uuid.uuid4()),
                    assignment_id=assignment_id,
                    student_id=student_id,
                    writing_session_id=writing_session_id,
                    final_version_id=final_version_id,
                    stats_json=stats_json,
                    micro_reflection_id=micro_reflection_id,
                    submitted_at=now,
                    round_no=1 if current is None else current.round_no + 1,
                    is_current=1,
                )
                db.add(submission)
            else:
                # 未批改(无 review 或 pending):覆盖当前轮
                previous_reflection_id = current.micro_reflection_id
                current.writing_session_id = writing_session_id
                current.final_version_id = final_version_id
                current.stats_json = stats_json
                current.micro_reflection_id = micro_reflection_id
                current.submitted_at = now
                if review is not None:
                    db.delete(review)
                if (
                    previous_reflection_id
                    and previous_reflection_id != micro_reflection_id
                ):
                    db.query(MicroReflection).filter(
                        MicroReflection.id == previous_reflection_id
                    ).delete(synchronize_session=False)
                submission = current

            db.flush()

            session = db.get(WritingSession, writing_session_id)
            if session is not None:
                session.status = "submitted"
                session.submitted_submission_id = submission.id
                session.updated_at = int(time.time())
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(submission)

            return SubmissionModel.model_validate(submission)

    def get_submission_by_id(
        self, submission_id: str, db: Optional[Session] = None
    ) -> Optional[SubmissionModel]:
        with get_db_context(db) as db:
            submission = db.get(Submission, submission_id)
            return SubmissionModel.model_validate(submission) if submission else None

    def get_current_submission(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> Optional[SubmissionModel]:
        with get_db_context(db) as db:
            submission = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.round_no.desc())
                .first()
            )
            return SubmissionModel.model_validate(submission) if submission else None

    def get_submission_rounds(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> list[SubmissionModel]:
        with get_db_context(db) as db:
            submissions = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                )
                .order_by(Submission.round_no.desc())
                .all()
            )
            return [SubmissionModel.model_validate(s) for s in submissions]

    def get_submissions_by_student(
        self,
        student_id: str,
        assignment_ids: Optional[list[str]] = None,
        db: Optional[Session] = None,
    ) -> list[SubmissionModel]:
        """该学生的全部提交,含历史轮次 —— 画像要的正是轮次之间的变化。"""
        if assignment_ids is not None and not assignment_ids:
            return []
        with get_db_context(db) as db:
            query = db.query(Submission).filter(Submission.student_id == student_id)
            if assignment_ids is not None:
                query = query.filter(Submission.assignment_id.in_(assignment_ids))
            submissions = query.order_by(
                Submission.submitted_at.asc(), Submission.round_no.asc()
            ).all()
            return [
                SubmissionModel.model_validate(submission) for submission in submissions
            ]

    def get_current_submissions_by_student(
        self,
        student_id: str,
        assignment_ids: Optional[list[str]] = None,
        db: Optional[Session] = None,
    ) -> list[SubmissionModel]:
        if assignment_ids is not None and not assignment_ids:
            return []
        with get_db_context(db) as db:
            query = db.query(Submission).filter(
                Submission.student_id == student_id,
                Submission.is_current == 1,
            )
            if assignment_ids is not None:
                query = query.filter(Submission.assignment_id.in_(assignment_ids))
            submissions = query.order_by(Submission.submitted_at.asc()).all()
            return [
                SubmissionModel.model_validate(submission) for submission in submissions
            ]

    def get_writing_sessions_by_ids(
        self, session_ids: list[str], db: Optional[Session] = None
    ) -> dict[str, WritingSessionModel]:
        ids = [session_id for session_id in session_ids if session_id]
        if not ids:
            return {}
        with get_db_context(db) as db:
            sessions = db.query(WritingSession).filter(WritingSession.id.in_(ids)).all()
            return {
                session.id: WritingSessionModel.model_validate(session)
                for session in sessions
            }

    def set_writing_session_status(
        self,
        session_id: str,
        status: str,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> None:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            if session is not None:
                session.status = status
                session.updated_at = int(time.time())
                if commit:
                    db.commit()
                else:
                    db.flush()

    def get_submission_review_by_submission_id(
        self, submission_id: str, db: Optional[Session] = None
    ) -> Optional[SubmissionReviewModel]:
        with get_db_context(db) as db:
            review = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id == submission_id)
                .first()
            )
            return SubmissionReviewModel.model_validate(review) if review else None

    def get_submission_reviews_by_submission_ids(
        self, submission_ids: list[str], db: Optional[Session] = None
    ) -> dict[str, SubmissionReviewModel]:
        if not submission_ids:
            return {}
        with get_db_context(db) as db:
            reviews = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id.in_(submission_ids))
                .all()
            )
            return {
                review.submission_id: SubmissionReviewModel.model_validate(review)
                for review in reviews
            }

    def upsert_submission_review(
        self,
        submission_id: str,
        assignment_id: str,
        reviewer_id: str,
        form_data: SubmissionReviewForm,
        commit: bool = True,
        db: Optional[Session] = None,
    ) -> SubmissionReviewModel:
        with get_db_context(db) as db:
            now = int(time.time())
            review = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id == submission_id)
                .first()
            )
            if review is None:
                review = SubmissionReview(
                    id=str(uuid.uuid4()),
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    reviewer_id=reviewer_id,
                    review_status=form_data.review_status,
                    score=form_data.score,
                    overall_comment=form_data.overall_comment,
                    rubric_scores=form_data.rubric_scores,
                    returned_comment=form_data.returned_comment,
                    challenge_followup=form_data.challenge_followup,
                    resubmit_due_at=form_data.resubmit_due_at,
                    reviewed_at=now if form_data.review_status != "pending" else None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(review)
            else:
                review.reviewer_id = reviewer_id
                review.review_status = form_data.review_status
                review.score = form_data.score
                review.overall_comment = form_data.overall_comment
                review.rubric_scores = form_data.rubric_scores
                review.returned_comment = form_data.returned_comment
                review.challenge_followup = form_data.challenge_followup
                review.resubmit_due_at = form_data.resubmit_due_at
                review.reviewed_at = (
                    now if form_data.review_status != "pending" else None
                )
                review.updated_at = now

            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(review)
            return SubmissionReviewModel.model_validate(review)

    def get_submissions_by_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> list[SubmissionModel]:
        with get_db_context(db) as db:
            submissions = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.submitted_at.desc())
                .all()
            )
            return [
                SubmissionModel.model_validate(submission) for submission in submissions
            ]

    def get_student_growth_goals(
        self,
        student_id: str,
        classroom_ids: Optional[list[str]] = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
        db: Optional[Session] = None,
    ) -> list[StudentGrowthGoalModel]:
        with get_db_context(db) as db:
            query = db.query(StudentGrowthGoal).filter(
                StudentGrowthGoal.student_id == student_id
            )
            if classroom_ids is not None:
                query = query.filter(
                    (StudentGrowthGoal.classroom_id.is_(None))
                    | (StudentGrowthGoal.classroom_id.in_(classroom_ids))
                )
            if not include_archived:
                query = query.filter(StudentGrowthGoal.status != "archived")
            goals = (
                query.order_by(
                    StudentGrowthGoal.status.asc(), StudentGrowthGoal.updated_at.desc()
                )
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [StudentGrowthGoalModel.model_validate(goal) for goal in goals]

    def insert_student_growth_goal(
        self,
        student_id: str,
        form_data: StudentGrowthGoalCreateForm,
        db: Optional[Session] = None,
    ) -> StudentGrowthGoalModel:
        with get_db_context(db) as db:
            now = int(time.time())
            goal = StudentGrowthGoal(
                id=str(uuid.uuid4()),
                student_id=student_id,
                classroom_id=form_data.classroom_id,
                assignment_id=form_data.assignment_id,
                goal_text=form_data.goal_text,
                target_at=form_data.target_at,
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(goal)
            db.commit()
            db.refresh(goal)
            return StudentGrowthGoalModel.model_validate(goal)

    def update_student_growth_goal(
        self,
        goal_id: str,
        student_id: str,
        form_data: StudentGrowthGoalUpdateForm,
        db: Optional[Session] = None,
    ) -> Optional[StudentGrowthGoalModel]:
        with get_db_context(db) as db:
            goal = db.get(StudentGrowthGoal, goal_id)
            if goal is None or goal.student_id != student_id:
                return None
            if "goal_text" in form_data.model_fields_set:
                goal.goal_text = form_data.goal_text
            if "target_at" in form_data.model_fields_set:
                goal.target_at = form_data.target_at
            if "status" in form_data.model_fields_set:
                goal.status = form_data.status
            goal.updated_at = int(time.time())
            db.commit()
            db.refresh(goal)
            return StudentGrowthGoalModel.model_validate(goal)

    def get_teacher_student_notes(
        self,
        teacher_id: str,
        classroom_id: str,
        student_id: str,
        limit: int = 100,
        offset: int = 0,
        db: Optional[Session] = None,
    ) -> list[TeacherStudentNoteModel]:
        with get_db_context(db) as db:
            notes = (
                db.query(TeacherStudentNote)
                .filter(
                    TeacherStudentNote.teacher_id == teacher_id,
                    TeacherStudentNote.classroom_id == classroom_id,
                    TeacherStudentNote.student_id == student_id,
                    TeacherStudentNote.deleted_at.is_(None),
                )
                .order_by(TeacherStudentNote.observed_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [TeacherStudentNoteModel.model_validate(note) for note in notes]

    def insert_teacher_student_note(
        self,
        teacher_id: str,
        classroom_id: str,
        student_id: str,
        form_data: TeacherStudentNoteCreateForm,
        db: Optional[Session] = None,
    ) -> TeacherStudentNoteModel:
        with get_db_context(db) as db:
            now = int(time.time())
            note = TeacherStudentNote(
                id=str(uuid.uuid4()),
                teacher_id=teacher_id,
                classroom_id=classroom_id,
                student_id=student_id,
                content=form_data.content,
                observed_at=form_data.observed_at or now,
                created_at=now,
                updated_at=now,
            )
            db.add(note)
            db.commit()
            db.refresh(note)
            return TeacherStudentNoteModel.model_validate(note)

    def update_teacher_student_note(
        self,
        note_id: str,
        teacher_id: str,
        form_data: TeacherStudentNoteUpdateForm,
        db: Optional[Session] = None,
    ) -> Optional[TeacherStudentNoteModel]:
        with get_db_context(db) as db:
            note = db.get(TeacherStudentNote, note_id)
            if (
                note is None
                or note.teacher_id != teacher_id
                or note.deleted_at is not None
            ):
                return None
            db.add(
                TeacherStudentNoteRevision(
                    id=str(uuid.uuid4()),
                    note_id=note.id,
                    teacher_id=teacher_id,
                    content=note.content,
                    observed_at=note.observed_at,
                    action="update",
                    created_at=int(time.time()),
                )
            )
            if "content" in form_data.model_fields_set:
                note.content = form_data.content
            if "observed_at" in form_data.model_fields_set:
                note.observed_at = form_data.observed_at
            note.edited_at = int(time.time())
            note.updated_at = note.edited_at
            db.commit()
            db.refresh(note)
            return TeacherStudentNoteModel.model_validate(note)

    def delete_teacher_student_note(
        self,
        note_id: str,
        teacher_id: str,
        db: Optional[Session] = None,
    ) -> bool:
        with get_db_context(db) as db:
            note = (
                db.query(TeacherStudentNote)
                .filter(
                    TeacherStudentNote.id == note_id,
                    TeacherStudentNote.teacher_id == teacher_id,
                    TeacherStudentNote.deleted_at.is_(None),
                )
                .first()
            )
            if note is None:
                return False
            now = int(time.time())
            db.add(
                TeacherStudentNoteRevision(
                    id=str(uuid.uuid4()),
                    note_id=note.id,
                    teacher_id=teacher_id,
                    content=note.content,
                    observed_at=note.observed_at,
                    action="delete",
                    created_at=now,
                )
            )
            note.deleted_at = now
            note.updated_at = now
            db.commit()
            return True

    def insert_notifications(
        self,
        user_ids: list[str],
        type: str,
        payload: dict,
        db: Optional[Session] = None,
    ) -> int:
        if not user_ids:
            return 0
        with get_db_context(db) as db:
            now = int(time.time())
            for user_id in user_ids:
                db.add(
                    EducationNotification(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        type=type,
                        payload_json=payload,
                        created_at=now,
                        read_at=None,
                    )
                )
            db.commit()
            return len(user_ids)

    def get_unread_notification_summary(
        self, user_id: str, db: Optional[Session] = None
    ) -> dict:
        with get_db_context(db) as db:
            rows = (
                db.query(EducationNotification)
                .filter(
                    EducationNotification.user_id == user_id,
                    EducationNotification.read_at.is_(None),
                )
                .all()
            )
            by_type: dict[str, int] = {}
            for row in rows:
                by_type[row.type] = by_type.get(row.type, 0) + 1
            return {"total": len(rows), "by_type": by_type}

    def mark_notifications_read(
        self,
        user_id: str,
        types: Optional[list[str]] = None,
        assignment_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        with get_db_context(db) as db:
            query = db.query(EducationNotification).filter(
                EducationNotification.user_id == user_id,
                EducationNotification.read_at.is_(None),
            )
            if types:
                query = query.filter(EducationNotification.type.in_(types))
            rows = query.all()
            now = int(time.time())
            marked = 0
            for row in rows:
                if assignment_id is not None:
                    payload = row.payload_json or {}
                    if payload.get("assignment_id") != assignment_id:
                        continue
                row.read_at = now
                marked += 1
            db.commit()
            return marked


Education = EducationTable()
