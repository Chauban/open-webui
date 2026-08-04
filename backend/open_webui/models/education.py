import time
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Column, Text, UniqueConstraint
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, JSONField, get_db_context


ASSIGNMENT_STATUSES = ("active", "archived")


class SubmissionAlreadyReviewedError(Exception):
    """学生想重交,但当前轮已被批改(只有退回才允许开新轮)。"""


class Assignment(Base):
    __tablename__ = "assignment"

    id = Column(Text, primary_key=True, unique=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Text, nullable=False)
    classroom_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    due_at = Column(BigInteger, nullable=True)
    archived_at = Column(BigInteger, nullable=True)
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

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    version_no = Column(BigInteger, nullable=False)
    note_snapshot_json = Column(JSONField, nullable=True)
    note_snapshot_text = Column(Text, nullable=True)
    trigger_type = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class ProvenanceSegment(Base):
    __tablename__ = "provenance_segment"

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
    metadata_json = Column(JSONField, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_result"

    id = Column(Text, primary_key=True, unique=True)
    writing_session_id = Column(Text, nullable=False)
    submission_id = Column(Text, nullable=True)
    result_type = Column(Text, nullable=False)
    payload_json = Column(JSONField, nullable=False, default={})
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class MicroReflection(Base):
    __tablename__ = "micro_reflection"

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    writing_session_id = Column(Text, nullable=False)
    ai_help_types = Column(JSONField, nullable=False, default=[])
    reflection_text = Column(Text, nullable=False)
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

    id = Column(Text, primary_key=True, unique=True)
    submission_id = Column(Text, nullable=False, unique=True)
    assignment_id = Column(Text, nullable=False)
    reviewer_id = Column(Text, nullable=False)
    review_status = Column(Text, nullable=False, default="pending")
    score = Column(BigInteger, nullable=True)
    overall_comment = Column(Text, nullable=True)
    rubric_json = Column(JSONField, nullable=True)
    returned_comment = Column(Text, nullable=True)
    resubmit_due_at = Column(BigInteger, nullable=True)
    reviewed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class EducationNotification(Base):
    __tablename__ = "education_notification"

    id = Column(Text, primary_key=True, unique=True)
    user_id = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    payload_json = Column(JSONField, nullable=False, default={})
    created_at = Column(BigInteger, nullable=False)
    read_at = Column(BigInteger, nullable=True)


class AssignmentModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    teacher_id: str
    classroom_id: Optional[str] = None
    status: str
    due_at: Optional[int] = None
    archived_at: Optional[int] = None
    created_at: int
    updated_at: int


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
    metadata_json: Optional[dict] = None
    created_at: int


class AnalysisResultModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    writing_session_id: str
    submission_id: Optional[str] = None
    result_type: str
    payload_json: dict
    created_at: int
    updated_at: int


class MicroReflectionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    writing_session_id: str
    ai_help_types: list[str] = Field(default_factory=list)
    reflection_text: str
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
    score: Optional[int] = None
    overall_comment: Optional[str] = None
    rubric_json: Optional[dict] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None
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


class AssignmentUpdateForm(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    classroom_id: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[int] = None


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
    classroom: Optional[ClassroomModel] = None
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
    trigger_type: str
    content_json: Optional[dict] = None
    content_text: str = ""


class ProvenanceSegmentInput(BaseModel):
    segment_id: str
    source_type: str
    segment_text: str
    source_message_id: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    metadata_json: Optional[dict] = None


class EditorOperationInput(BaseModel):
    op_type: str
    source_type: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    inserted_text: Optional[str] = None
    deleted_text: Optional[str] = None
    batch_id: str
    metadata_json: Optional[dict] = None


class EditorOperationCreateForm(BaseModel):
    operations: list[EditorOperationInput] = Field(default_factory=list)


class ProvenanceCreateForm(BaseModel):
    version_id: Optional[str] = None
    segments: list[ProvenanceSegmentInput] = Field(default_factory=list)
    replace_existing: bool = False


class SubmissionCreateForm(BaseModel):
    writing_session_id: str
    final_content_json: Optional[dict] = None
    final_content_html: Optional[str] = None
    final_content_text: str
    ai_help_types: list[str] = Field(default_factory=list, min_length=1)
    reflection_text: str


class SubmissionReviewForm(BaseModel):
    review_status: str = "reviewed"
    score: Optional[int] = None
    overall_comment: Optional[str] = None
    rubric_json: Optional[dict] = None
    returned_comment: Optional[str] = None
    resubmit_due_at: Optional[int] = None


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


class UnsubmittedStudentItem(BaseModel):
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None


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
    review_count: int
    pending_review_count: int = 0
    unsubmitted_count: int = 0
    classrooms: list[TeacherClassroomListItem]
    recent_assignments: list[TeacherAssignmentListItem]
    recent_submissions: list[SubmissionListItem]
    pending_review_items: list[SubmissionListItem] = Field(default_factory=list)
    upcoming_due_assignments: list[TeacherAssignmentListItem] = Field(
        default_factory=list
    )


class TeacherReviewResponse(BaseModel):
    items: list[SubmissionListItem] = Field(default_factory=list)
    total: int = 0


class StudentProfileAssignmentItem(BaseModel):
    """作业维度的当前状态；未提交的作业也要出现,否则缺交信息会从画像里消失。"""

    assignment: AssignmentModel
    submission_id: Optional[str] = None
    submitted_at: Optional[int] = None
    round_no: Optional[int] = None
    review_status: str = "unsubmitted"
    score: Optional[int] = None


class StudentProfileTimelinePoint(BaseModel):
    """一次提交在成长画像里的三维快照(产出 / 过程 / AI 协作)。"""

    submission_id: str
    assignment_id: str
    assignment_title: str
    round_no: int = 1
    is_current: bool = True
    submitted_at: int

    # 产出维:教师评分与 rubric 原值,不做归一化(满分由教师自定,没有统一量纲)。
    total_chars: int = 0
    score: Optional[int] = None
    rubric: Optional[dict] = None
    review_status: str = "pending"

    # 过程维。不用版本数:一个版本 = 一次 1.2 秒防抖自动保存,衡量的是打字时长
    # 而不是「改了几版」,拿它当修改投入会被打字速度带偏。
    inserted_chars: int = 0
    revised_chars: int = 0
    revision_depth: int = 0
    writing_span_seconds: int = 0
    active_writing_seconds: int = 0
    lead_time_seconds: Optional[int] = None
    last_minute_ratio: float = 0.0
    process_index: int = 0

    # AI 协作维
    typed_ratio: float = 0.0
    ai_ratio: float = 0.0
    unknown_ratio: float = 0.0
    prompt_count: int = 0
    digestion_ratio: int = 0
    reflection_char_count: int = 0
    reflection_quality: int = 0
    ai_help_types: list[str] = Field(default_factory=list)
    collaboration_index: int = 0

    # 风险信号:只做展示,不参与任何成长指数。
    burst_count: int = 0
    suspected_unmarked_import_count: int = 0


class StudentProfileRoundProgress(BaseModel):
    """退回—重交之间的改动幅度,是最直接的「响应反馈」证据。"""

    assignment_id: str
    assignment_title: str
    from_round: int
    to_round: int
    char_delta: int = 0
    revision_ratio: int = 0
    score_delta: Optional[int] = None
    turnaround_seconds: Optional[int] = None


class StudentProfileMetricTrend(BaseModel):
    key: str
    first: float
    last: float
    delta: float
    direction: str = "flat"
    sample_count: int = 0


class StudentProfileInsight(BaseModel):
    """规则生成的结论;文案由前端按 code 走 i18n,后端不产出自然语言。"""

    code: str
    tone: str = "neutral"
    params: dict = Field(default_factory=dict)


class StudentProfileResponse(BaseModel):
    student_id: str
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    classroom: Optional[ClassroomModel] = None
    assignment_count: int = 0
    submitted_count: int = 0
    unsubmitted_count: int = 0
    reviewed_count: int = 0
    returned_count: int = 0
    average_score: Optional[float] = None
    assignments: list[StudentProfileAssignmentItem] = Field(default_factory=list)
    timeline: list[StudentProfileTimelinePoint] = Field(default_factory=list)
    round_progress: list[StudentProfileRoundProgress] = Field(default_factory=list)
    trends: list[StudentProfileMetricTrend] = Field(default_factory=list)
    ai_help_type_distribution: dict = Field(default_factory=dict)
    ai_help_type_shift: dict = Field(default_factory=dict)
    reflection_quality: dict = Field(default_factory=dict)
    index_formula: dict = Field(default_factory=dict)
    insights: list[StudentProfileInsight] = Field(default_factory=list)


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
            classroom_member = self.get_classroom_member_by_user_id(student_id, db=db)
            if classroom_member is None:
                return []
            assignments = (
                db.query(Assignment)
                .filter(
                    Assignment.classroom_id == classroom_member.classroom_id,
                )
                .order_by(Assignment.updated_at.desc())
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
                        if (
                            (folder.meta or {}).get("writing_session_id")
                            == session.id
                        )
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
            db.commit()
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
                .order_by(EditorOperation.created_at.asc(), EditorOperation.id.asc())
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
                db.query(EditorOperation.writing_session_id, EditorOperation.created_at)
                .filter(EditorOperation.writing_session_id.in_(session_ids))
                .order_by(EditorOperation.created_at.asc())
                .all()
            )
            grouped: dict[str, list[int]] = {}
            for session_id, created_at in rows:
                grouped.setdefault(session_id, []).append(created_at)
            return grouped

    def upsert_analysis_result(
        self,
        session_id: str,
        result_type: str,
        payload_json: dict,
        submission_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> AnalysisResultModel:
        with get_db_context(db) as db:
            query = db.query(AnalysisResult).filter(
                AnalysisResult.writing_session_id == session_id,
                AnalysisResult.result_type == result_type,
            )
            if submission_id is not None:
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

            db.commit()
            db.refresh(result)
            return AnalysisResultModel.model_validate(result)

    def get_analysis_result(
        self,
        session_id: str,
        result_type: str,
        submission_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[AnalysisResultModel]:
        with get_db_context(db) as db:
            query = db.query(AnalysisResult).filter(
                AnalysisResult.writing_session_id == session_id,
                AnalysisResult.result_type == result_type,
            )
            if submission_id is not None:
                query = query.filter(AnalysisResult.submission_id == submission_id)
            result = query.first()
            return AnalysisResultModel.model_validate(result) if result else None

    def insert_micro_reflection(
        self,
        assignment_id: str,
        student_id: str,
        writing_session_id: str,
        ai_help_types: list[str],
        reflection_text: str,
        db: Optional[Session] = None,
    ) -> MicroReflectionModel:
        with get_db_context(db) as db:
            reflection = MicroReflection(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                writing_session_id=writing_session_id,
                ai_help_types=ai_help_types,
                reflection_text=reflection_text,
                created_at=int(time.time()),
            )
            db.add(reflection)
            db.commit()
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

            db.commit()
            db.refresh(submission)

            session = db.get(WritingSession, writing_session_id)
            if session is not None:
                session.status = "submitted"
                session.submitted_submission_id = submission.id
                session.updated_at = int(time.time())
                db.commit()

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
        self, session_id: str, status: str, db: Optional[Session] = None
    ) -> None:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            if session is not None:
                session.status = status
                session.updated_at = int(time.time())
                db.commit()

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
                    rubric_json=form_data.rubric_json,
                    returned_comment=form_data.returned_comment,
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
                review.rubric_json = form_data.rubric_json
                review.returned_comment = form_data.returned_comment
                review.resubmit_due_at = form_data.resubmit_due_at
                review.reviewed_at = (
                    now if form_data.review_status != "pending" else None
                )
                review.updated_at = now

            db.commit()
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
