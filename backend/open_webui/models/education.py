import time
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Column, Text
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, JSONField, get_db_context


class Assignment(Base):
    __tablename__ = "assignment"

    id = Column(Text, primary_key=True, unique=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Text, nullable=False)
    classroom_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
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

    id = Column(Text, primary_key=True, unique=True)
    classroom_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    member_role = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class AssignmentMember(Base):
    __tablename__ = "assignment_member"

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    member_role = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class WritingSession(Base):
    __tablename__ = "writing_session"

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    note_id = Column(Text, nullable=False)
    chat_id = Column(Text, nullable=False)
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


class MicroReflection(Base):
    __tablename__ = "micro_reflection"

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    writing_session_id = Column(Text, nullable=False)
    ai_help_type = Column(Text, nullable=False)
    reflection_text = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class Submission(Base):
    __tablename__ = "submission"

    id = Column(Text, primary_key=True, unique=True)
    assignment_id = Column(Text, nullable=False)
    student_id = Column(Text, nullable=False)
    writing_session_id = Column(Text, nullable=False)
    final_version_id = Column(Text, nullable=False)
    stats_json = Column(JSONField, nullable=False, default={})
    micro_reflection_id = Column(Text, nullable=False)
    submitted_at = Column(BigInteger, nullable=False)


class AssignmentModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    teacher_id: str
    classroom_id: Optional[str] = None
    status: str
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


class AssignmentMemberModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    user_id: str
    member_role: str
    created_at: int
    updated_at: int


class WritingSessionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    note_id: str
    chat_id: str
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


class MicroReflectionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_id: str
    writing_session_id: str
    ai_help_type: str
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


class AssignmentCreateForm(BaseModel):
    title: str
    description: Optional[str] = None
    classroom_id: Optional[str] = None


class ClassroomCreateForm(BaseModel):
    name: str


class ClassroomJoinForm(BaseModel):
    invite_code: str


class AssignmentMemberCreateForm(BaseModel):
    user_id: str
    member_role: str = "student"


class AssignmentWorkspaceResponse(BaseModel):
    assignment: AssignmentModel
    membership_role: str
    writing_session: WritingSessionModel
    note: dict
    chat: dict


class AssignmentMemberDetail(BaseModel):
    member: AssignmentMemberModel
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    education_role: Optional[str] = None


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
    student_count: int = 0
    submission_count: int = 0


class StudentAssignmentListItem(BaseModel):
    assignment: AssignmentModel
    membership: ClassroomMemberModel
    has_submission: bool = False
    submission_id: Optional[str] = None
    writing_session_id: Optional[str] = None


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


class ProvenanceCreateForm(BaseModel):
    version_id: Optional[str] = None
    segments: list[ProvenanceSegmentInput] = Field(default_factory=list)


class SubmissionCreateForm(BaseModel):
    writing_session_id: str
    final_content_json: Optional[dict] = None
    final_content_html: Optional[str] = None
    final_content_text: str
    ai_help_type: str
    reflection_text: str


class SubmissionListItem(BaseModel):
    submission: SubmissionModel
    session: WritingSessionModel
    assignment: AssignmentModel
    reflection: Optional[MicroReflectionModel] = None
    student_name: Optional[str] = None


class SubmissionDetailResponse(BaseModel):
    submission: SubmissionModel
    assignment: AssignmentModel
    writing_session: WritingSessionModel
    final_version: WritingVersionModel
    versions: list[WritingVersionModel]
    provenance_segments: list[ProvenanceSegmentModel]
    prompt_timeline: list[dict]
    micro_reflection: MicroReflectionModel
    note: dict
    student_name: Optional[str] = None


class DashboardItem(BaseModel):
    submission_id: str
    student_id: str
    student_name: Optional[str] = None
    source_stats: dict
    prompt_count: int
    has_reflection: bool
    submitted_at: int


class DashboardResponse(BaseModel):
    items: list[DashboardItem]


class EducationTable:
    @staticmethod
    def _generate_invite_code() -> str:
        return uuid.uuid4().hex[:8].upper()

    def insert_classroom(
        self, teacher_id: str, form_data: ClassroomCreateForm, db: Optional[Session] = None
    ) -> ClassroomModel:
        with get_db_context(db) as db:
            now = int(time.time())
            classroom = Classroom(
                id=str(uuid.uuid4()),
                name=form_data.name,
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

    def get_classroom_by_teacher(
        self, teacher_id: str, db: Optional[Session] = None
    ) -> Optional[ClassroomModel]:
        with get_db_context(db) as db:
            classroom = (
                db.query(Classroom)
                .filter(Classroom.teacher_id == teacher_id)
                .order_by(Classroom.created_at.asc())
                .first()
            )
            return ClassroomModel.model_validate(classroom) if classroom else None

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

    def ensure_default_classroom_for_teacher(
        self, teacher_id: str, db: Optional[Session] = None
    ) -> ClassroomModel:
        with get_db_context(db) as db:
            classroom = self.get_classroom_by_teacher(teacher_id, db=db)
            if classroom:
                return classroom
            return self.insert_classroom(
                teacher_id,
                ClassroomCreateForm(name="Default Classroom"),
                db=db,
            )

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

            members = (
                query.order_by(ClassroomMember.created_at.asc(), ClassroomMember.user_id.asc()).all()
            )
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

    def insert_assignment(
        self, teacher_id: str, form_data: AssignmentCreateForm, db: Optional[Session] = None
    ) -> AssignmentModel:
        with get_db_context(db) as db:
            now = int(time.time())
            classroom_id = form_data.classroom_id or self.ensure_default_classroom_for_teacher(
                teacher_id, db=db
            ).id
            assignment = Assignment(
                id=str(uuid.uuid4()),
                title=form_data.title,
                description=form_data.description,
                teacher_id=teacher_id,
                classroom_id=classroom_id,
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            self.ensure_assignment_member(assignment.id, teacher_id, "teacher", db=db)
            return AssignmentModel.model_validate(assignment)

    def get_assignment_by_id(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentModel]:
        with get_db_context(db) as db:
            assignment = db.get(Assignment, assignment_id)
            return AssignmentModel.model_validate(assignment) if assignment else None

    def get_assignments_by_teacher(
        self, teacher_id: str, db: Optional[Session] = None
    ) -> list[AssignmentModel]:
        with get_db_context(db) as db:
            default_classroom = self.ensure_default_classroom_for_teacher(teacher_id, db=db)
            assignments = (
                db.query(Assignment)
                .filter(Assignment.teacher_id == teacher_id)
                .order_by(Assignment.updated_at.desc())
                .all()
            )
            updated_assignments = []
            for assignment in assignments:
                if assignment.classroom_id is None:
                    assignment.classroom_id = default_classroom.id
                    assignment.updated_at = int(time.time())
                    db.commit()
                    db.refresh(assignment)
                updated_assignments.append(assignment)
            return [AssignmentModel.model_validate(assignment) for assignment in updated_assignments]

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
            return [AssignmentModel.model_validate(assignment) for assignment in assignments]

    def ensure_assignment_member(
        self,
        assignment_id: str,
        user_id: str,
        member_role: str,
        db: Optional[Session] = None,
    ) -> AssignmentMemberModel:
        with get_db_context(db) as db:
            member = (
                db.query(AssignmentMember)
                .filter(
                    AssignmentMember.assignment_id == assignment_id,
                    AssignmentMember.user_id == user_id,
                )
                .first()
            )
            now = int(time.time())
            if member is None:
                member = AssignmentMember(
                    id=str(uuid.uuid4()),
                    assignment_id=assignment_id,
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
            return AssignmentMemberModel.model_validate(member)

    def get_assignment_member(
        self, assignment_id: str, user_id: str, db: Optional[Session] = None
    ) -> Optional[AssignmentMemberModel]:
        with get_db_context(db) as db:
            member = (
                db.query(AssignmentMember)
                .filter(
                    AssignmentMember.assignment_id == assignment_id,
                    AssignmentMember.user_id == user_id,
                )
                .first()
            )
            return AssignmentMemberModel.model_validate(member) if member else None

    def get_assignment_members(
        self,
        assignment_id: str,
        member_role: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[AssignmentMemberModel]:
        with get_db_context(db) as db:
            query = db.query(AssignmentMember).filter(
                AssignmentMember.assignment_id == assignment_id
            )
            if member_role is not None:
                query = query.filter(AssignmentMember.member_role == member_role)

            members = (
                query.order_by(AssignmentMember.created_at.asc(), AssignmentMember.user_id.asc()).all()
            )
            return [AssignmentMemberModel.model_validate(member) for member in members]

    def delete_assignment_member(
        self, assignment_id: str, user_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            deleted = (
                db.query(AssignmentMember)
                .filter(
                    AssignmentMember.assignment_id == assignment_id,
                    AssignmentMember.user_id == user_id,
                )
                .delete()
            )
            db.commit()
            return deleted > 0

    def get_writing_session_by_id(
        self, session_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = db.get(WritingSession, session_id)
            return WritingSessionModel.model_validate(session) if session else None

    def get_writing_session(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> Optional[WritingSessionModel]:
        with get_db_context(db) as db:
            session = (
                db.query(WritingSession)
                .filter(
                    WritingSession.assignment_id == assignment_id,
                    WritingSession.student_id == student_id,
                )
                .first()
            )
            return WritingSessionModel.model_validate(session) if session else None

    def insert_writing_session(
        self,
        assignment_id: str,
        student_id: str,
        note_id: str,
        chat_id: str,
        db: Optional[Session] = None,
    ) -> WritingSessionModel:
        with get_db_context(db) as db:
            now = int(time.time())
            session = WritingSession(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                note_id=note_id,
                chat_id=chat_id,
                status="draft",
                submitted_submission_id=None,
                created_at=now,
                updated_at=now,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return WritingSessionModel.model_validate(session)

    def touch_writing_session(
        self, session_id: str, status: Optional[str] = None, db: Optional[Session] = None
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

    def insert_provenance_segments(
        self,
        session_id: str,
        segments: list[ProvenanceSegmentInput],
        version_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[ProvenanceSegmentModel]:
        with get_db_context(db) as db:
            records = []
            for segment in segments:
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
            return [ProvenanceSegmentModel.model_validate(segment) for segment in segments]

    def insert_micro_reflection(
        self,
        assignment_id: str,
        student_id: str,
        writing_session_id: str,
        ai_help_type: str,
        reflection_text: str,
        db: Optional[Session] = None,
    ) -> MicroReflectionModel:
        with get_db_context(db) as db:
            reflection = MicroReflection(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                writing_session_id=writing_session_id,
                ai_help_type=ai_help_type,
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
            return MicroReflectionModel.model_validate(reflection) if reflection else None

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
            submission = Submission(
                id=str(uuid.uuid4()),
                assignment_id=assignment_id,
                student_id=student_id,
                writing_session_id=writing_session_id,
                final_version_id=final_version_id,
                stats_json=stats_json,
                micro_reflection_id=micro_reflection_id,
                submitted_at=int(time.time()),
            )
            db.add(submission)
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

    def get_submissions_by_assignment(
        self, assignment_id: str, db: Optional[Session] = None
    ) -> list[SubmissionModel]:
        with get_db_context(db) as db:
            submissions = (
                db.query(Submission)
                .filter(Submission.assignment_id == assignment_id)
                .order_by(Submission.submitted_at.desc())
                .all()
            )
            return [SubmissionModel.model_validate(submission) for submission in submissions]


Education = EducationTable()
