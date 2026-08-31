import csv
import difflib
import io
import time
import uuid
from datetime import datetime
from typing import NamedTuple, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.chats import ChatForm, Chats
from open_webui.models.chat_messages import ChatMessages
from open_webui.models.folders import FolderForm, Folders
from open_webui.models.education import (
    AssignmentModel,
    AssignmentCreateForm,
    AssignmentRemindForm,
    AssignmentRemindResult,
    AssignmentUpdateForm,
    AssignmentWorkspaceListItem,
    AssignmentWorkspaceResponse,
    AutosaveForm,
    ClassroomCreateForm,
    ClassroomBulkImportForm,
    ClassroomBulkImportResult,
    ClassroomJoinForm,
    ClassroomMemberCreateForm,
    ClassroomMemberDetail,
    ClassroomMembersActionForm,
    ClassroomMembersActionResult,
    ClassroomMemberTransferForm,
    ClassroomModel,
    ClassroomProgressAssignmentItem,
    ClassroomProgressResponse,
    ClassroomResponse,
    DashboardItem,
    DashboardResponse,
    EditorOperationCreateForm,
    Education,
    MyAssignmentSubmissionsResponse,
    MySubmissionRound,
    MySubmissionRoundContent,
    MySubmissionRoundReview,
    PersonalWritingCreateForm,
    PersonalWorkspaceListItem,
    ProvenanceCreateForm,
    SubmissionAlreadyReviewedError,
    SubmissionCreateForm,
    SubmissionDetailResponse,
    SubmissionListItem,
    SubmissionModel,
    SubmissionReviewForm,
    StudentAssignmentListItem,
    StudentProfileResponse,
    TeacherAssignmentListItem,
    TeacherClassroomListItem,
    TeacherOverviewResponse,
    TeacherReviewResponse,
    UnifiedWritingWorkspaceResponse,
    UnsubmittedStudentItem,
    VersionCreateForm,
    WritingHomeResponse,
    WritingRecentItem,
    WritingSessionModel,
    WritingVersionSummaryModel,
)
from open_webui.services.education.analysis import (
    NormalizedSegment,
    accumulate_risk_summary,
    build_submission_analysis,
    build_source_map_highlights,
    compute_stats,
    compute_stats_from_highlights,
    empty_risk_summary,
    filter_segments_for_final_text,
    finalize_risk_summary,
    get_or_build_submission_analysis,
    get_or_build_submission_analyses,
    get_prompt_timeline,
)
from open_webui.services.education.profile import build_student_profile
from open_webui.models.notes import NoteForm, Notes
from open_webui.models.users import Users
from open_webui.socket.main import emit_to_users
from open_webui.utils.auth import get_verified_user

router = APIRouter()

MAX_STUDENT_ASSIGNMENTS = 100
SUBMISSION_DETAIL_VERSION_LIMIT = 20
PROJECT_MODE_GENERAL = "general"
PROJECT_MODE_PERSONAL_WRITING = "personal_writing"
PROJECT_MODE_ASSIGNMENT_WRITING = "assignment_writing"


class ChatMessageUpsertForm(BaseModel):
    message: dict


class ActiveChatUpdateForm(BaseModel):
    chat_id: Optional[str] = None


class NotificationMarkReadForm(BaseModel):
    types: Optional[list[str]] = None
    assignment_id: Optional[str] = None


async def _send_education_notifications(
    user_ids: list[str], notification_type: str, payload: dict, db: Session
) -> None:
    if not user_ids:
        return
    Education.insert_notifications(user_ids, notification_type, payload, db=db)
    await emit_to_users(
        "education:notification",
        {"type": notification_type, "payload": payload},
        user_ids,
    )


def _get_education_role(user):
    if user.role == "admin":
        return "admin"
    if getattr(user, "info", None):
        return user.info.get("education_role")
    return None


def _ensure_teacher_identity(user):
    education_role = _get_education_role(user)
    if education_role in {"admin", "teacher"}:
        return education_role

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Teacher identity is required",
    )


def _is_valid_due_at(due_at: Optional[int]) -> bool:
    return due_at is not None and due_at > 0


def _format_export_timestamp(timestamp: Optional[int]) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


async def _build_classroom_member_detail(member, db: Session):
    linked_user = await Users.get_user_by_id(member.user_id, db=db)
    linked_user_info = linked_user.info if linked_user and linked_user.info else {}
    return ClassroomMemberDetail(
        member=member,
        user_name=linked_user.name if linked_user else member.user_id,
        user_email=linked_user.email if linked_user else None,
        education_role=linked_user_info.get("education_role"),
    )


async def _build_teacher_assignment_list_item(assignment, db: Session):
    classroom = None
    student_count = 0
    if assignment.classroom_id:
        classroom = Education.get_classroom_by_id(assignment.classroom_id, db=db)
        if classroom is not None:
            student_count = len(
                Education.get_classroom_members(
                    classroom.id, member_role="student", db=db
                )
            )

    submissions = Education.get_submissions_by_assignment(assignment.id, db=db)
    latest_submission_at = max(
        (submission.submitted_at for submission in submissions), default=None
    )
    risk_summary = empty_risk_summary()
    sessions = Education.get_writing_sessions_by_ids(
        [submission.writing_session_id for submission in submissions], db=db
    )
    analyses = await get_or_build_submission_analyses(submissions, sessions, db)
    for submission in submissions:
        analysis = analyses.get(submission.id) or {}
        accumulate_risk_summary(risk_summary, analysis.get("summary"))

    return TeacherAssignmentListItem(
        assignment=assignment,
        classroom=classroom,
        student_count=student_count,
        submission_count=len(submissions),
        latest_submission_at=latest_submission_at,
        risk_summary=finalize_risk_summary(risk_summary),
    )


async def _build_submission_list_item(submission, assignment, db: Session):
    session = Education.get_writing_session_by_id(submission.writing_session_id, db=db)
    reflection = Education.get_micro_reflection_by_id(
        submission.micro_reflection_id, db=db
    )
    student = await Users.get_user_by_id(submission.student_id, db=db)
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    classroom = (
        Education.get_classroom_by_id(assignment.classroom_id, db=db)
        if assignment.classroom_id
        else None
    )
    analysis = await get_or_build_submission_analysis(submission, session, db)
    return SubmissionListItem(
        submission=submission,
        session=session,
        assignment=assignment,
        classroom=classroom,
        reflection=reflection,
        student_name=student.name if student else submission.student_id,
        review_status=review.review_status if review else "pending",
        score=review.score if review else None,
        risk_summary=analysis.get("summary", {}),
    )


def _ensure_classroom_access(
    user, classroom, db: Session, require_teacher: bool = False
):
    if user.role == "admin":
        return "admin"

    member = Education.get_classroom_member(classroom.id, user.id, db=db)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this classroom",
        )

    if require_teacher and member.member_role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher access is required",
        )

    return member.member_role


def _make_assignment_project_meta(
    assignment_id: str, session_id: Optional[str] = None
) -> dict:
    meta = {
        "mode": PROJECT_MODE_ASSIGNMENT_WRITING,
        "assignment_id": assignment_id,
        "hidden_from_sidebar": False,
    }
    if session_id:
        meta["writing_session_id"] = session_id
    return meta


def _make_personal_project_meta(session_id: str) -> dict:
    return {
        "mode": PROJECT_MODE_PERSONAL_WRITING,
        "writing_session_id": session_id,
        "hidden_from_sidebar": False,
    }


def _get_project_mode_from_session(session) -> str:
    return (
        PROJECT_MODE_ASSIGNMENT_WRITING
        if session.scope == "assignment"
        else PROJECT_MODE_PERSONAL_WRITING
    )


def _make_default_note(title: str, assignment_id: str) -> NoteForm:
    return NoteForm(
        title=title,
        data={
            "content": {"json": None, "html": "", "md": ""},
            "versions": [],
            "files": [],
        },
        meta={"assignment_id": assignment_id},
        access_grants=[],
    )


def _make_personal_note(title: str) -> NoteForm:
    return NoteForm(
        title=title,
        data={
            "content": {"json": None, "html": "", "md": ""},
            "versions": [],
            "files": [],
        },
        meta={"scope": "personal"},
        access_grants=[],
    )


def _get_assignment_or_404(assignment_id: str, db: Session) -> AssignmentModel:
    assignment = Education.get_assignment_by_id(assignment_id, db=db)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    return assignment


def _get_classroom_or_404(classroom_id: str, db: Session) -> ClassroomModel:
    classroom = Education.get_classroom_by_id(classroom_id, db=db)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )
    return classroom


def _get_submission_or_404(submission_id: str, db: Session) -> SubmissionModel:
    submission = Education.get_submission_by_id(submission_id, db=db)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return submission


def _load_submission_rounds_with_reviews(
    assignment, student_id: str, db: Session
) -> tuple[list, dict]:
    rounds = Education.get_submission_rounds(assignment.id, student_id, db=db)
    reviews = Education.get_submission_reviews_by_submission_ids(
        [submission.id for submission in rounds], db=db
    )
    return rounds, reviews


def _resolve_effective_due_at(assignment, rounds: list, reviews: dict) -> Optional[int]:
    for submission in rounds:
        review = reviews.get(submission.id)
        if review is None or review.review_status == "pending":
            continue
        if review.review_status == "returned" and review.resubmit_due_at:
            return review.resubmit_due_at
        break  # reviewed:本作业反馈循环已关闭,回落到原始截止
    return assignment.due_at


def _get_effective_due_at(
    assignment, student_id: str, db: Session
) -> Optional[int]:
    rounds, reviews = _load_submission_rounds_with_reviews(assignment, student_id, db)
    return _resolve_effective_due_at(assignment, rounds, reviews)


def _build_student_review_view(
    assignment, student_id: str, db: Session
) -> tuple[Optional[dict], Optional[int]]:
    rounds, reviews = _load_submission_rounds_with_reviews(assignment, student_id, db)
    effective_due_at = _resolve_effective_due_at(assignment, rounds, reviews)
    submission = next(
        (item for item in rounds if item.is_current == 1),
        None,
    )
    if submission is None:
        return None, effective_due_at
    review = reviews.get(submission.id)
    view = {
        "round_no": submission.round_no,
        "submitted_at": submission.submitted_at,
        "review_status": review.review_status if review else "pending",
    }
    if review and review.review_status == "reviewed":
        view.update(
            {
                "score": review.score,
                "overall_comment": review.overall_comment,
                "rubric": review.rubric_scores,
                "reviewed_at": review.reviewed_at,
            }
        )
    elif review and review.review_status == "returned":
        view.update(
            {
                "returned_comment": review.returned_comment,
                "resubmit_due_at": review.resubmit_due_at,
                "reviewed_at": review.reviewed_at,
            }
        )
    return view, effective_due_at


def _get_workspace_session_or_404(session_id: str, db: Session):
    session = Education.get_writing_session_by_id(session_id, db=db)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing session not found"
        )
    return session


def _ensure_workspace_session_owner(user, session):
    if user.role != "admin" and session.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _get_assignment_classroom_or_404(assignment, db: Session):
    classroom_id = assignment.classroom_id
    if classroom_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found",
        )
    classroom = Education.get_classroom_by_id(classroom_id, db=db)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found",
        )
    return classroom


async def _ensure_assignment_project(assignment, session, db: Session):
    project = (
        await Folders.get_folder_by_id_and_user_id(
            session.folder_id, session.owner_user_id, db=db
        )
        if session.folder_id
        else None
    )

    if project is None:
        project = await Folders.insert_new_folder(
            session.owner_user_id,
            FolderForm(
                name=assignment.title,
                meta=_make_assignment_project_meta(assignment.id, session.id),
                data={},
            ),
            db=db,
        )
        session = Education.update_writing_session_context(
            session.id,
            folder_id=project.id,
            chat_id=session.chat_id,
            active_chat_id=session.active_chat_id,
            db=db,
        )
    else:
        desired_meta = _make_assignment_project_meta(assignment.id, session.id)
        desired_name = assignment.title
        if desired_meta != (project.meta or {}) or desired_name != project.name:
            project = await Folders.update_folder_by_id_and_user_id(
                project.id,
                session.owner_user_id,
                FolderForm(
                    name=desired_name, meta=desired_meta, data=project.data or {}
                ),
                db=db,
            )

    legacy_chat = (
        await Chats.get_chat_by_id(session.chat_id, db=db) if session.chat_id else None
    )
    if legacy_chat is not None and legacy_chat.folder_id != project.id:
        await Chats.update_chat_folder_id_by_id_and_user_id(
            legacy_chat.id, session.owner_user_id, project.id, db=db
        )
        chat_meta = dict(legacy_chat.meta or {})
        if chat_meta.get("category") == "assignment_workspace":
            chat_meta.pop("category", None)
            chat_meta.pop("assignment_id", None)
            chat_meta.pop("writing_session_id", None)
            Chats.update_chat_meta_by_id(legacy_chat.id, chat_meta, db=db)

    return project


async def _ensure_personal_project(session, note, db: Session):
    project = (
        await Folders.get_folder_by_id_and_user_id(
            session.folder_id, session.owner_user_id, db=db
        )
        if session.folder_id
        else None
    )
    desired_name = note.title or "Untitled Writing"
    desired_meta = _make_personal_project_meta(session.id)

    if project is None:
        project = await Folders.insert_new_folder(
            session.owner_user_id,
            FolderForm(name=desired_name, meta=desired_meta, data={}),
            db=db,
        )
        session = Education.update_writing_session_context(
            session.id,
            folder_id=project.id if project else None,
            chat_id=session.chat_id,
            active_chat_id=session.active_chat_id,
            db=db,
        )
        return project, session

    if project.name != desired_name or (project.meta or {}) != desired_meta:
        project = await Folders.update_folder_by_id_and_user_id(
            project.id,
            session.owner_user_id,
            FolderForm(name=desired_name, meta=desired_meta, data=project.data or {}),
            db=db,
        )

    return project, session


async def _get_workspace_resources_or_409(assignment, session, db: Session):
    note = await Notes.get_note_by_id(session.note_id, db=db)
    project = await _ensure_assignment_project(assignment, session, db=db)

    active_chat_id = session.active_chat_id or session.chat_id
    active_chat = (
        await Chats.get_chat_by_id(active_chat_id, db=db) if active_chat_id else None
    )
    if active_chat_id and active_chat is None:
        session = Education.update_writing_session_context(
            session.id,
            chat_id=None,
            active_chat_id=None,
            db=db,
        )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ASSIGNMENT_WORKSPACE_CORRUPTED",
                "detail": "Assignment workspace is missing note resources.",
                "assignment_id": assignment.id,
                "writing_session_id": session.id,
                "missing_note": note is None,
                "missing_chat": False,
            },
        )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ASSIGNMENT_WORKSPACE_CORRUPTED",
                "detail": "Assignment workspace is missing project resources.",
                "assignment_id": assignment.id,
                "writing_session_id": session.id,
                "missing_note": False,
                "missing_chat": False,
                "missing_project": True,
            },
        )

    return note, project, session.active_chat_id or session.chat_id


def _ensure_assignment_access(
    user, assignment, db: Session, require_teacher: bool = False
):
    if user.role == "admin":
        return "admin"

    if assignment.teacher_id == user.id:
        return "teacher"

    classroom = _get_assignment_classroom_or_404(assignment, db)

    member = Education.get_classroom_member(classroom.id, user.id, db=db)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this assignment",
        )

    if require_teacher and member.member_role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher access is required",
        )

    return member.member_role


class TeacherSubmissionScope(NamedTuple):
    submission: SubmissionModel
    assignment: AssignmentModel


def require_teacher_classroom(
    classroom_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
) -> ClassroomModel:
    """路径含 {classroom_id} 的教师端接口:校验教学身份 + 班级教师权限。"""
    _ensure_teacher_identity(user)
    classroom = _get_classroom_or_404(classroom_id, db)
    _ensure_classroom_access(user, classroom, db, require_teacher=True)
    return classroom


def require_teacher_assignment(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
) -> AssignmentModel:
    """路径含 {assignment_id} 的教师端接口:校验教学身份 + 作业教师权限。"""
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    return assignment


def require_teacher_submission(
    submission_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
) -> TeacherSubmissionScope:
    """路径含 {submission_id} 的教师端接口:提交所属作业需具备教师权限。"""
    _ensure_teacher_identity(user)
    submission = _get_submission_or_404(submission_id, db)
    assignment = _get_assignment_or_404(submission.assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    return TeacherSubmissionScope(submission=submission, assignment=assignment)


def require_owned_writing_session(
    session_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
) -> WritingSessionModel:
    """路径含 {session_id} 的写作接口:会话必须属于当前用户。"""
    session = _get_workspace_session_or_404(session_id, db)
    _ensure_workspace_session_owner(user, session)
    return session






async def _build_personal_workspace_item(
    session, db: Session
) -> Optional[PersonalWorkspaceListItem]:
    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        return None
    preview_text = (((note.data or {}).get("content") or {}).get("md") or "").strip()[
        :160
    ] or None
    return PersonalWorkspaceListItem(
        project_mode=PROJECT_MODE_PERSONAL_WRITING,
        writing_session=session,
        project_id=session.folder_id,
        title=note.title or "Untitled Writing",
        updated_at=max(session.updated_at, note.updated_at),
        preview_text=preview_text,
    )


async def _build_recent_item(session, db: Session) -> Optional[WritingRecentItem]:
    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        return None
    assignment = (
        Education.get_assignment_by_id(session.assignment_id, db=db)
        if session.assignment_id and session.scope == "assignment"
        else None
    )
    title = (
        assignment.title
        if assignment is not None
        else (note.title or "Untitled Writing")
    )
    updated_at = max(session.updated_at, note.updated_at)
    return WritingRecentItem(
        project_mode=_get_project_mode_from_session(session),
        scope=session.scope,
        writing_session_id=session.id,
        title=title,
        updated_at=updated_at,
        status=session.status,
        assignment=assignment,
    )




@router.post("/assignments", response_model=list[AssignmentModel])
async def create_assignment(
    form_data: AssignmentCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    classroom_ids = list(
        dict.fromkeys(
            classroom_id.strip()
            for classroom_id in form_data.classroom_ids
            if classroom_id and classroom_id.strip()
        )
    )
    if not classroom_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one classroom is required",
        )
    if not form_data.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment title is required",
        )
    if not _is_valid_due_at(form_data.due_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment due time is required",
        )
    classrooms = []
    for classroom_id in classroom_ids:
        classroom = Education.get_classroom_by_id(classroom_id, db=db)
        if classroom is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Classroom not found",
            )
        _ensure_classroom_access(user, classroom, db, require_teacher=True)
        classrooms.append(classroom)

    assignments = []
    for classroom in classrooms:
        assignment = Education.insert_assignment(
            user.id, classroom.id, form_data, db=db
        )
        student_ids = [
            member.user_id
            for member in Education.get_classroom_members(
                assignment.classroom_id, member_role="student", db=db
            )
        ]
        await _send_education_notifications(
            student_ids,
            "assignment_published",
            {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "due_at": assignment.due_at,
            },
            db,
        )
        assignments.append(assignment)
    return assignments


@router.patch("/assignments/{assignment_id}", response_model=AssignmentModel)
async def update_assignment(
    assignment_id: str,
    form_data: AssignmentUpdateForm,
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    next_status = (
        form_data.status
        if "status" in form_data.model_fields_set
        else assignment.status
    )
    next_due_at = (
        form_data.due_at
        if "due_at" in form_data.model_fields_set
        else assignment.due_at
    )
    if next_status != "archived" and not _is_valid_due_at(next_due_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment due time is required",
        )

    if (
        (
            "score_max" in form_data.model_fields_set
            and form_data.score_max != assignment.score_max
        )
        or (
            "rubric_schema" in form_data.model_fields_set
            and form_data.rubric_schema != assignment.rubric_schema
        )
    ) and Education.get_submissions_by_assignment(assignment.id, db=db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scoring configuration cannot change after submissions exist",
        )

    next_score_max = form_data.score_max or assignment.score_max
    next_rubric = form_data.rubric_schema or assignment.rubric_schema
    if next_rubric.total_score != next_score_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rubric maximum scores must add up to assignment maximum score",
        )

    if form_data.classroom_id is not None:
        classroom = _get_classroom_or_404(form_data.classroom_id, db)
        _ensure_classroom_access(user, classroom, db, require_teacher=True)
        if form_data.classroom_id != assignment.classroom_id and Education.get_submissions_by_assignment(
            assignment.id, db=db
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Classroom cannot be changed after submissions exist",
            )

    previous_due_at = assignment.due_at
    try:
        updated_assignment = Education.update_assignment(
            assignment_id, form_data, db=db
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    if updated_assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    if (
        "due_at" in form_data.model_fields_set
        and updated_assignment.due_at != previous_due_at
        and updated_assignment.classroom_id
    ):
        student_ids = [
            member.user_id
            for member in Education.get_classroom_members(
                updated_assignment.classroom_id, member_role="student", db=db
            )
        ]
        await _send_education_notifications(
            student_ids,
            "assignment_updated",
            {
                "assignment_id": updated_assignment.id,
                "assignment_title": updated_assignment.title,
                "due_at": updated_assignment.due_at,
            },
            db,
        )
    return updated_assignment


@router.post("/assignments/{assignment_id}/archive", response_model=AssignmentModel)
async def archive_assignment(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    archived_assignment = Education.archive_assignment(assignment.id, db=db)
    if archived_assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    return archived_assignment


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    if Education.get_submissions_by_assignment(assignment.id, db=db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignments with submissions cannot be deleted; archive instead",
        )
    if Education.get_writing_sessions_by_assignment(assignment.id, db=db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignments with student writing activity cannot be deleted; archive instead",
        )
    Education.delete_assignment_notifications(assignment.id, db=db)
    Education.delete_assignment(assignment.id, db=db)
    return {"ok": True}


def _get_unsubmitted_members(assignment, db: Session):
    if not assignment.classroom_id:
        return []
    members = Education.get_classroom_members(
        assignment.classroom_id, member_role="student", db=db
    )
    submitted_ids = {
        submission.student_id
        for submission in Education.get_submissions_by_assignment(assignment.id, db=db)
    }
    return [member for member in members if member.user_id not in submitted_ids]


@router.get(
    "/teacher/assignments/{assignment_id}/unsubmitted",
    response_model=list[UnsubmittedStudentItem],
)
async def get_assignment_unsubmitted_students(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    items = []
    for member in _get_unsubmitted_members(assignment, db):
        member_user = await Users.get_user_by_id(member.user_id, db=db)
        items.append(
            UnsubmittedStudentItem(
                user_id=member.user_id,
                user_name=member_user.name if member_user else member.user_id,
                user_email=member_user.email if member_user else None,
            )
        )
    return items


@router.post(
    "/teacher/assignments/{assignment_id}/remind",
    response_model=AssignmentRemindResult,
)
async def remind_unsubmitted_students(
    form_data: AssignmentRemindForm,
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    unsubmitted_ids = [
        member.user_id for member in _get_unsubmitted_members(assignment, db)
    ]
    if form_data.user_ids is not None:
        requested_ids = set(form_data.user_ids)
        target_ids = [
            user_id for user_id in unsubmitted_ids if user_id in requested_ids
        ]
    else:
        target_ids = unsubmitted_ids

    await _send_education_notifications(
        target_ids,
        "assignment_reminder",
        {
            "assignment_id": assignment.id,
            "assignment_title": assignment.title,
            "due_at": assignment.due_at,
        },
        db,
    )
    return AssignmentRemindResult(reminded_count=len(target_ids), user_ids=target_ids)


@router.get("/me/classroom", response_model=ClassroomResponse)
async def get_my_classroom(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    education_role = _get_education_role(user)
    if education_role == "teacher" or user.role == "admin":
        classrooms = Education.get_classrooms_by_teacher(user.id, db=db)
        if not classrooms:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Classroom not found",
            )
        classroom = classrooms[0]
        membership = Education.get_classroom_member(classroom.id, user.id, db=db)
        return ClassroomResponse(classroom=classroom, membership=membership)

    membership = Education.get_classroom_member_by_user_id(user.id, db=db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found",
        )

    classroom = Education.get_classroom_by_id(membership.classroom_id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.post("/classrooms", response_model=ClassroomResponse)
async def create_classroom(
    form_data: ClassroomCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    if not form_data.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Classroom name is required",
        )
    try:
        classroom = Education.insert_classroom(user.id, form_data, db=db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    membership = Education.get_classroom_member(classroom.id, user.id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.post("/classrooms/join", response_model=ClassroomResponse)
async def join_classroom(
    form_data: ClassroomJoinForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if not form_data.invite_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Classroom invite code is required",
        )

    if _get_education_role(user) != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can join classrooms",
        )

    existing_membership = Education.get_classroom_member_by_user_id(user.id, db=db)
    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already linked to a classroom",
        )

    classroom = Education.get_classroom_by_invite_code(form_data.invite_code, db=db)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid classroom invite code",
        )

    membership = Education.ensure_classroom_member(
        classroom.id, user.id, "student", db=db
    )
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.post(
    "/classrooms/{classroom_id}/invite-code/regenerate",
    response_model=ClassroomResponse,
)
async def regenerate_classroom_invite_code(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    classroom = Education.regenerate_classroom_invite_code(classroom.id, db=db)
    membership = Education.get_classroom_member(classroom.id, user.id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.get("/teacher/classrooms", response_model=list[TeacherClassroomListItem])
async def get_teacher_classrooms(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    classrooms = Education.get_classrooms_by_teacher(user.id, db=db)

    items = []
    for classroom in classrooms:
        assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
        student_count = len(
            Education.get_classroom_members(classroom.id, member_role="student", db=db)
        )
        risk_summary = empty_risk_summary()
        submissions = [
            submission
            for assignment in assignments
            for submission in Education.get_submissions_by_assignment(
                assignment.id, db=db
            )
        ]
        sessions = Education.get_writing_sessions_by_ids(
            [submission.writing_session_id for submission in submissions], db=db
        )
        analyses = await get_or_build_submission_analyses(submissions, sessions, db)
        for submission in submissions:
            analysis = analyses.get(submission.id) or {}
            accumulate_risk_summary(risk_summary, analysis.get("summary"))
        items.append(
            TeacherClassroomListItem(
                classroom=classroom,
                student_count=student_count,
                assignment_count=len(assignments),
                risk_summary=finalize_risk_summary(risk_summary),
            )
        )

    return items


@router.get("/teacher/assignments", response_model=list[TeacherAssignmentListItem])
async def get_teacher_assignments(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignments = Education.get_assignments_by_teacher(user.id, db=db)
    return [
        await _build_teacher_assignment_list_item(assignment, db)
        for assignment in assignments
    ]


@router.get(
    "/teacher/assignments/{assignment_id}", response_model=TeacherAssignmentListItem
)
async def get_teacher_assignment(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    return await _build_teacher_assignment_list_item(assignment, db)


@router.get("/teacher/overview", response_model=TeacherOverviewResponse)
async def get_teacher_overview(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    classrooms = Education.get_classrooms_by_teacher(user.id, db=db)
    classroom_items = []
    assignment_items = []
    submission_items = []
    unsubmitted_count = 0
    pending_review_items = []

    for classroom in classrooms:
        assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
        student_count = len(
            Education.get_classroom_members(classroom.id, member_role="student", db=db)
        )
        classroom_risk_summary = empty_risk_summary()
        classroom_items.append(
            TeacherClassroomListItem(
                classroom=classroom,
                student_count=student_count,
                assignment_count=len(assignments),
                risk_summary=classroom_risk_summary,
            )
        )

        for assignment in assignments:
            submissions = Education.get_submissions_by_assignment(assignment.id, db=db)
            unsubmitted_count += max(student_count - len(submissions), 0)
            # 作业维度的风险汇总直接由提交项累加,不再走
            # _build_teacher_assignment_list_item 把每份提交的分析重算一遍。
            assignment_risk_summary = empty_risk_summary()
            for submission in submissions:
                submission_item = await _build_submission_list_item(
                    submission, assignment, db
                )
                submission_items.append(submission_item)
                accumulate_risk_summary(
                    assignment_risk_summary, submission_item.risk_summary or {}
                )
                accumulate_risk_summary(
                    classroom_risk_summary, submission_item.risk_summary or {}
                )
                if submission_item.review_status == "pending":
                    pending_review_items.append(submission_item)

            assignment_items.append(
                TeacherAssignmentListItem(
                    assignment=assignment,
                    classroom=classroom,
                    student_count=student_count,
                    submission_count=len(submissions),
                    latest_submission_at=max(
                        (submission.submitted_at for submission in submissions),
                        default=None,
                    ),
                    risk_summary=finalize_risk_summary(assignment_risk_summary),
                )
            )

        classroom_items[-1].risk_summary = finalize_risk_summary(
            classroom_risk_summary
        )

    assignment_items.sort(
        key=lambda item: max(
            item.latest_submission_at or 0,
            item.assignment.updated_at,
            item.assignment.created_at,
        ),
        reverse=True,
    )
    submission_items.sort(key=lambda item: item.submission.submitted_at, reverse=True)
    pending_review_items.sort(
        key=lambda item: item.submission.submitted_at, reverse=True
    )
    now_ts = int(time.time())
    due_assignments = sorted(
        [
            item
            for item in assignment_items
            if item.assignment.due_at is not None
            and item.assignment.status == "active"
            and item.assignment.due_at >= now_ts
        ],
        key=lambda item: item.assignment.due_at or 0,
    )

    return TeacherOverviewResponse(
        classroom_count=len(classroom_items),
        assignment_count=len(assignment_items),
        submission_count=len(submission_items),
        review_count=len(pending_review_items),
        pending_review_count=len(pending_review_items),
        unsubmitted_count=unsubmitted_count,
        classrooms=classroom_items[:5],
        recent_assignments=assignment_items[:5],
        recent_submissions=submission_items[:5],
        pending_review_items=pending_review_items[:5],
        upcoming_due_assignments=due_assignments[:5],
    )


REVIEW_QUEUE_MAX_LIMIT = 200


def _review_sort_key(item: SubmissionListItem, sort: str):
    summary = item.risk_summary or {}
    if sort == "suspected":
        return summary.get("suspected_unmarked_import_count", 0) or 0
    if sort == "burst":
        return summary.get("burst_count", 0) or 0
    if sort == "rewrite":
        return summary.get("average_rewrite_ratio", 0) or 0
    return item.submission.submitted_at


@router.get("/teacher/review", response_model=TeacherReviewResponse)
async def get_teacher_review(
    review_status: Optional[str] = None,
    classroom_id: Optional[str] = None,
    assignment_id: Optional[str] = None,
    sort: str = "latest",
    only_suspected: bool = False,
    only_bursts: bool = False,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignments = Education.get_assignments_by_teacher(user.id, db=db)
    if assignment_id:
        assignments = [
            assignment for assignment in assignments if assignment.id == assignment_id
        ]
    if classroom_id:
        assignments = [
            assignment
            for assignment in assignments
            if assignment.classroom_id == classroom_id
        ]

    candidates = [
        (submission, assignment)
        for assignment in assignments
        for submission in Education.get_submissions_by_assignment(assignment.id, db=db)
    ]

    if review_status:
        reviews = Education.get_submission_reviews_by_submission_ids(
            [submission.id for submission, _ in candidates], db=db
        )
        candidates = [
            (submission, assignment)
            for submission, assignment in candidates
            if (
                reviews[submission.id].review_status
                if submission.id in reviews
                else "pending"
            )
            == review_status
        ]

    limit = max(1, min(limit, REVIEW_QUEUE_MAX_LIMIT))
    offset = max(offset, 0)

    if sort not in ("suspected", "burst", "rewrite") and not (
        only_suspected or only_bursts
    ):
        # 排序与筛选都不依赖分析结果:先分页再构建,整个队列只为当前这一页构建分析。
        candidates.sort(key=lambda pair: pair[0].submitted_at, reverse=True)
        return TeacherReviewResponse(
            items=[
                await _build_submission_list_item(submission, assignment, db)
                for submission, assignment in candidates[offset : offset + limit]
            ],
            total=len(candidates),
        )

    # 疑似导入/爆发/改写率的筛选与排序键都来自分析摘要,只能全量构建后再分页。
    items = [
        await _build_submission_list_item(submission, assignment, db)
        for submission, assignment in candidates
    ]
    if only_suspected:
        items = [
            item
            for item in items
            if (item.risk_summary or {}).get("suspected_unmarked_import_count", 0) > 0
        ]
    if only_bursts:
        items = [
            item for item in items if (item.risk_summary or {}).get("burst_count", 0) > 0
        ]
    items.sort(key=lambda item: _review_sort_key(item, sort), reverse=True)
    return TeacherReviewResponse(items=items[offset : offset + limit], total=len(items))


@router.get("/teacher/classrooms/{classroom_id}", response_model=ClassroomResponse)
async def get_teacher_classroom(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    membership = Education.get_classroom_member(classroom.id, user.id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.get(
    "/teacher/classrooms/{classroom_id}/members",
    response_model=list[ClassroomMemberDetail],
)
async def get_classroom_members(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    members = Education.get_classroom_members(
        classroom.id, member_role="student", db=db
    )
    return [await _build_classroom_member_detail(member, db) for member in members]


@router.post(
    "/teacher/classrooms/{classroom_id}/members",
    response_model=ClassroomMemberDetail,
)
async def add_classroom_member(
    form_data: ClassroomMemberCreateForm,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    member_user = await Users.get_user_by_id(form_data.user_id, db=db)
    if member_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    education_role = (
        (member_user.info or {}).get("education_role") if member_user.info else None
    )
    if education_role != "student":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only users with student identity can be added",
        )

    existing_membership = Education.get_classroom_member_by_user_id(
        member_user.id, db=db
    )
    if (
        existing_membership is not None
        and existing_membership.classroom_id != classroom.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already linked to another classroom",
        )

    member = Education.ensure_classroom_member(
        classroom.id, member_user.id, "student", db=db
    )
    return await _build_classroom_member_detail(member, db)


@router.delete("/teacher/classrooms/{classroom_id}/members/{member_user_id}")
async def delete_classroom_member(
    member_user_id: str,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    if classroom.teacher_id == member_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teacher membership cannot be removed",
        )

    deleted = Education.delete_classroom_member(classroom.id, member_user_id, db=db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom member not found",
        )

    return {"ok": True}


@router.post(
    "/teacher/classrooms/{classroom_id}/bulk-import",
    response_model=ClassroomBulkImportResult,
)
async def bulk_import_classroom_members(
    form_data: ClassroomBulkImportForm,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    result = ClassroomBulkImportResult()
    candidate_ids = {
        item.strip() for item in form_data.user_ids if item and item.strip()
    }
    for email in form_data.emails:
        normalized_email = email.strip().lower()
        if not normalized_email:
            continue
        member_user = await Users.get_user_by_email(normalized_email, db=db)
        if member_user is None:
            result.failed_users.append(
                {"value": normalized_email, "reason": "User not found"}
            )
            continue
        candidate_ids.add(member_user.id)

    for user_id in candidate_ids:
        member_user = await Users.get_user_by_id(user_id, db=db)
        if member_user is None:
            result.failed_users.append({"value": user_id, "reason": "User not found"})
            continue

        education_role = (
            (member_user.info or {}).get("education_role") if member_user.info else None
        )
        if education_role != "student":
            result.failed_users.append(
                {"value": user_id, "reason": "Only student users can be imported"}
            )
            continue

        existing_membership = Education.get_classroom_member_by_user_id(
            member_user.id, db=db
        )
        if (
            existing_membership is not None
            and existing_membership.classroom_id != classroom.id
        ):
            result.failed_users.append(
                {
                    "value": user_id,
                    "reason": "Student is already linked to another classroom",
                }
            )
            continue

        if (
            existing_membership is not None
            and existing_membership.classroom_id == classroom.id
        ):
            result.skipped_users.append(user_id)
            continue

        Education.ensure_classroom_member(
            classroom.id, member_user.id, "student", db=db
        )
        result.added_users.append(user_id)

    result.added_count = len(result.added_users)
    result.skipped_count = len(result.skipped_users)
    result.failed_count = len(result.failed_users)
    return result


@router.post(
    "/teacher/classrooms/{classroom_id}/members/bulk-remove",
    response_model=ClassroomMembersActionResult,
)
async def bulk_remove_classroom_members(
    form_data: ClassroomMembersActionForm,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    result = ClassroomMembersActionResult()
    for user_id in dict.fromkeys(form_data.user_ids):
        if not user_id or classroom.teacher_id == user_id:
            result.skipped_users.append(user_id)
            continue
        if Education.delete_classroom_member(classroom.id, user_id, db=db):
            result.affected_count += 1
        else:
            result.skipped_users.append(user_id)
    return result


@router.post(
    "/teacher/classrooms/{classroom_id}/members/transfer",
    response_model=ClassroomMembersActionResult,
)
async def transfer_classroom_members(
    form_data: ClassroomMemberTransferForm,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    target_classroom = Education.get_classroom_by_id(
        form_data.target_classroom_id.strip(), db=db
    )
    if target_classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target classroom not found",
        )
    _ensure_classroom_access(user, target_classroom, db, require_teacher=True)
    if target_classroom.id == classroom.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target classroom must be different",
        )

    result = ClassroomMembersActionResult()
    for user_id in dict.fromkeys(form_data.user_ids):
        member = (
            Education.get_classroom_member(classroom.id, user_id, db=db)
            if user_id
            else None
        )
        if member is None or member.member_role != "student":
            result.skipped_users.append(user_id)
            continue
        Education.delete_classroom_member(classroom.id, user_id, db=db)
        Education.ensure_classroom_member(target_classroom.id, user_id, "student", db=db)
        result.affected_count += 1
    return result


@router.get(
    "/teacher/classrooms/{classroom_id}/progress",
    response_model=ClassroomProgressResponse,
)
async def get_classroom_progress(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    students = Education.get_classroom_members(
        classroom.id, member_role="student", db=db
    )
    assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
    progress_items = []
    submitted_total = 0
    unsubmitted_total = 0
    reviewed_total = 0
    pending_total = 0

    # 提交、批改、写作会话都先一次性取回,避免「作业 × 提交」两层循环里逐条查库。
    submissions_by_assignment = {
        assignment.id: Education.get_submissions_by_assignment(assignment.id, db=db)
        for assignment in assignments
    }
    all_submissions = [
        submission
        for submissions in submissions_by_assignment.values()
        for submission in submissions
    ]
    reviews = Education.get_submission_reviews_by_submission_ids(
        [submission.id for submission in all_submissions], db=db
    )
    sessions = Education.get_writing_sessions_by_ids(
        [submission.writing_session_id for submission in all_submissions], db=db
    )
    analyses = await get_or_build_submission_analyses(all_submissions, sessions, db)

    for assignment in assignments:
        submissions = submissions_by_assignment[assignment.id]
        submitted_count = len(submissions)
        unsubmitted_count = max(len(students) - submitted_count, 0)
        reviewed_count = 0
        pending_count = 0
        risk_summary = empty_risk_summary()
        for submission in submissions:
            review = reviews.get(submission.id)
            if review and review.review_status in {"reviewed", "returned"}:
                reviewed_count += 1
            else:
                pending_count += 1
            analysis = analyses.get(submission.id) or {}
            accumulate_risk_summary(risk_summary, analysis.get("summary"))

        progress_items.append(
            ClassroomProgressAssignmentItem(
                assignment=assignment,
                submitted_count=submitted_count,
                unsubmitted_count=unsubmitted_count,
                reviewed_count=reviewed_count,
                pending_review_count=pending_count,
                risk_summary=finalize_risk_summary(risk_summary),
            )
        )
        submitted_total += submitted_count
        unsubmitted_total += unsubmitted_count
        reviewed_total += reviewed_count
        pending_total += pending_count

    return ClassroomProgressResponse(
        classroom=classroom,
        student_count=len(students),
        assignment_count=len(assignments),
        submitted_count=submitted_total,
        unsubmitted_count=unsubmitted_total,
        reviewed_count=reviewed_total,
        pending_review_count=pending_total,
        risk_summary=finalize_risk_summary(
            {
                "submission_count": sum(
                    item.risk_summary.get("submission_count", 0)
                    for item in progress_items
                ),
                "ai_inserted_chars": sum(
                    item.risk_summary.get("ai_inserted_chars", 0)
                    for item in progress_items
                ),
                "ai_pasted_chars": sum(
                    item.risk_summary.get("ai_pasted_chars", 0)
                    for item in progress_items
                ),
                "suspected_unmarked_import_count": sum(
                    item.risk_summary.get("suspected_unmarked_import_count", 0)
                    for item in progress_items
                ),
                "burst_count": sum(
                    item.risk_summary.get("burst_count", 0) for item in progress_items
                ),
                "average_rewrite_ratio": sum(
                    item.risk_summary.get("average_rewrite_ratio", 0)
                    * item.risk_summary.get("submission_count", 0)
                    for item in progress_items
                ),
            }
        ),
        assignments=progress_items,
    )


@router.get("/teacher/classrooms/{classroom_id}/export")
async def export_classroom_progress(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    students = Education.get_classroom_members(
        classroom.id, member_role="student", db=db
    )
    assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "student_name",
            "student_email",
            "assignment_title",
            "submitted_at",
            "review_status",
            "score",
            "overall_comment",
        ]
    )

    # 每份作业的提交只查一次并按学生建索引,避免学生 × 作业的嵌套全表扫描。
    submissions_by_assignment = {
        assignment.id: {
            submission.student_id: submission
            for submission in Education.get_submissions_by_assignment(
                assignment.id, db=db
            )
        }
        for assignment in assignments
    }
    reviews_by_submission = Education.get_submission_reviews_by_submission_ids(
        [
            submission.id
            for submissions in submissions_by_assignment.values()
            for submission in submissions.values()
        ],
        db=db,
    )

    for student_member in students:
        student_detail = await _build_classroom_member_detail(student_member, db)
        for assignment in assignments:
            latest_submission = submissions_by_assignment[assignment.id].get(
                student_member.user_id
            )
            if latest_submission is not None:
                review = reviews_by_submission.get(latest_submission.id)
                writer.writerow(
                    [
                        student_detail.user_name,
                        student_detail.user_email,
                        assignment.title,
                        _format_export_timestamp(latest_submission.submitted_at),
                        review.review_status if review else "pending",
                        review.score if review else "",
                        (review.overall_comment or "") if review else "",
                    ]
                )
            else:
                writer.writerow(
                    [
                        student_detail.user_name,
                        student_detail.user_email,
                        assignment.title,
                        "",
                        "unsubmitted",
                        "",
                        "",
                    ]
                )

    filename = f"classroom-{classroom.id}-progress.csv"
    # utf-8-sig BOM 前缀,避免 Excel 打开含中文的 CSV 乱码
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/teacher/classrooms/{classroom_id}/students/{student_user_id}/profile",
    response_model=StudentProfileResponse,
)
async def get_student_profile(
    student_user_id: str,
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    member = Education.get_classroom_member(classroom.id, student_user_id, db=db)
    if member is None or member.member_role != "student":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found in classroom",
        )

    student = await Users.get_user_by_id(student_user_id, db=db)
    assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
    return await build_student_profile(
        student, student_user_id, classroom, assignments, db
    )


@router.get(
    "/teacher/classrooms/{classroom_id}/assignments",
    response_model=list[TeacherAssignmentListItem],
)
async def get_teacher_classroom_assignments(
    classroom: ClassroomModel = Depends(require_teacher_classroom),
    db: Session = Depends(get_session),
):
    assignments = Education.get_assignments_by_classroom(classroom.id, db=db)
    return [
        await _build_teacher_assignment_list_item(assignment, db)
        for assignment in assignments
    ]


@router.get(
    "/assignments/{assignment_id}/workspace", response_model=AssignmentWorkspaceResponse
)
async def get_assignment_workspace(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignment = Education.get_assignment_by_id(assignment_id, db=db)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )

    role = _ensure_assignment_access(user, assignment, db)
    if role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can open the writing workspace",
        )

    session = Education.get_assignment_writing_session(assignment_id, user.id, db=db)
    if session is None:
        note = await Notes.insert_new_note(
            user.id, _make_default_note(assignment.title, assignment_id), db=db
        )
        if note is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ASSIGNMENT_WORKSPACE_CORRUPTED",
                    "detail": "Assignment workspace note could not be created.",
                    "assignment_id": assignment.id,
                    "missing_note": True,
                    "missing_chat": False,
                    "missing_project": False,
                },
            )
        writing_session_id = str(uuid.uuid4())
        project = await Folders.insert_new_folder(
            user.id,
            FolderForm(
                name=assignment.title,
                meta=_make_assignment_project_meta(assignment.id, writing_session_id),
                data={},
            ),
            db=db,
        )
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ASSIGNMENT_WORKSPACE_CORRUPTED",
                    "detail": "Assignment workspace project could not be created.",
                    "assignment_id": assignment.id,
                    "missing_note": False,
                    "missing_chat": False,
                    "missing_project": True,
                },
            )
        session = Education.insert_writing_session(
            assignment_id,
            user.id,
            "assignment",
            note.id,
            project.id,
            None,
            None,
            session_id=writing_session_id,
            db=db,
        )
    else:
        note, project, active_chat_id = await _get_workspace_resources_or_409(
            assignment, session, db=db
        )
        session = Education.get_writing_session_by_id(session.id, db=db)
        review_view, effective_due_at = _build_student_review_view(
            assignment, user.id, db
        )
        return AssignmentWorkspaceResponse(
            assignment=assignment,
            membership_role="student",
            writing_session=session,
            note=note.model_dump(),
            project=project.model_dump(),
            active_chat_id=active_chat_id,
            source_map=Education.get_provenance_segments(session.id, db=db),
            review=review_view,
            effective_due_at=effective_due_at,
        )

    review_view, effective_due_at = _build_student_review_view(assignment, user.id, db)
    return AssignmentWorkspaceResponse(
        assignment=assignment,
        membership_role="student",
        writing_session=session,
        note=note.model_dump(),
        project=project.model_dump(),
        active_chat_id=None,
        source_map=[],
        review=review_view,
        effective_due_at=effective_due_at,
    )


@router.get("/me/writing/home", response_model=WritingHomeResponse)
async def get_writing_home(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    education_role = _get_education_role(user)
    classroom = (
        Education.get_classroom_by_id(
            Education.get_classroom_member_by_user_id(user.id, db=db).classroom_id,
            db=db,
        )
        if education_role == "student"
        and Education.get_classroom_member_by_user_id(user.id, db=db)
        else None
    )

    sessions = Education.get_writing_sessions_by_owner(user.id, db=db)
    personal_items = []
    recent_items = []
    for session in sessions:
        if session.scope == "personal":
            item = await _build_personal_workspace_item(session, db)
            if item is not None:
                personal_items.append(item)
        recent_item = await _build_recent_item(session, db)
        if recent_item is not None:
            recent_items.append(recent_item)

    assignment_items = []
    if education_role == "student":
        assignments = Education.get_assignments_by_student(user.id, db=db)[
            :MAX_STUDENT_ASSIGNMENTS
        ]
        for assignment in assignments:
            session = Education.get_assignment_writing_session(
                assignment.id, user.id, db=db
            )
            if session is None:
                assignment_items.append(
                    AssignmentWorkspaceListItem(
                        project_mode=PROJECT_MODE_ASSIGNMENT_WRITING,
                        assignment=assignment,
                        project_id=None,
                        writing_session_id=None,
                        status="not_started",
                        updated_at=assignment.updated_at,
                        effective_due_at=assignment.due_at,
                    )
                )
                continue

            submitted_at = None
            if session.submitted_submission_id:
                submission = Education.get_submission_by_id(
                    session.submitted_submission_id, db=db
                )
                submitted_at = submission.submitted_at if submission else None

            review_view, effective_due_at = _build_student_review_view(
                assignment, user.id, db
            )

            assignment_items.append(
                AssignmentWorkspaceListItem(
                    project_mode=PROJECT_MODE_ASSIGNMENT_WRITING,
                    assignment=assignment,
                    project_id=session.folder_id,
                    writing_session_id=session.id,
                    status=session.status,
                    updated_at=max(assignment.updated_at, session.updated_at),
                    submitted_at=submitted_at,
                    review_status=review_view["review_status"] if review_view else None,
                    score=(review_view or {}).get("score"),
                    round_no=(review_view or {}).get("round_no"),
                    effective_due_at=effective_due_at,
                )
            )

    recent_items = sorted(recent_items, key=lambda item: item.updated_at, reverse=True)[
        :12
    ]
    personal_items = sorted(
        personal_items, key=lambda item: item.updated_at, reverse=True
    )
    assignment_items = sorted(
        assignment_items, key=lambda item: item.updated_at, reverse=True
    )

    return WritingHomeResponse(
        role=education_role or user.role,
        classroom=classroom,
        recent_items=recent_items,
        assignment_items=assignment_items,
        personal_items=personal_items,
    )


@router.post("/me/writing/personal", response_model=UnifiedWritingWorkspaceResponse)
async def create_personal_writing(
    form_data: PersonalWritingCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    title = (form_data.title or "").strip() or "Untitled Writing"
    note = await Notes.insert_new_note(user.id, _make_personal_note(title), db=db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Unable to create note"
        )

    session = Education.insert_writing_session(
        None,
        user.id,
        "personal",
        note.id,
        None,
        None,
        None,
        status="active",
        db=db,
    )
    project = await Folders.insert_new_folder(
        user.id,
        FolderForm(name=title, meta=_make_personal_project_meta(session.id), data={}),
        db=db,
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Unable to create project"
        )

    session = Education.update_writing_session_context(
        session.id,
        folder_id=project.id,
        chat_id=None,
        active_chat_id=None,
        db=db,
    )
    return UnifiedWritingWorkspaceResponse(
        scope="personal",
        owner_role=_get_education_role(user) or user.role,
        assignment=None,
        writing_session=session,
        note=note.model_dump(),
        project=project.model_dump(),
        active_chat_id=None,
        source_map=[],
    )


@router.get(
    "/writing/{session_id}/workspace", response_model=UnifiedWritingWorkspaceResponse
)
async def get_writing_workspace(
    session: WritingSessionModel = Depends(require_owned_writing_session),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Writing note is missing"
        )

    assignment = None
    if session.scope == "assignment":
        assignment = _get_assignment_or_404(session.assignment_id, db)
        role = _ensure_assignment_access(user, assignment, db)
        if role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can open the writing workspace",
            )
        project = await _ensure_assignment_project(assignment, session, db=db)
    else:
        project, session = await _ensure_personal_project(session, note, db=db)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Writing project is missing"
        )

    active_chat_id = session.active_chat_id or session.chat_id
    active_chat = (
        await Chats.get_chat_by_id(active_chat_id, db=db) if active_chat_id else None
    )
    if active_chat_id and active_chat is None:
        session = Education.update_writing_session_context(
            session.id,
            chat_id=None,
            active_chat_id=None,
            db=db,
        )
        active_chat_id = None

    return UnifiedWritingWorkspaceResponse(
        scope=session.scope,
        owner_role=_get_education_role(user) or user.role,
        assignment=assignment,
        writing_session=session,
        note=note.model_dump(),
        project=project.model_dump(),
        active_chat_id=active_chat_id,
        source_map=Education.get_provenance_segments(session.id, db=db),
    )


@router.delete("/me/writing/personal/{session_id}", response_model=dict)
async def delete_personal_writing(
    session: WritingSessionModel = Depends(require_owned_writing_session),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if session.scope != "personal":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid writing scope"
        )

    deleted = await Education.delete_personal_writing_session(session.id, user.id, db=db)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing session not found"
        )
    return {"ok": True, **deleted}


@router.get("/me/writing/workspaces", response_model=list[AssignmentWorkspaceListItem])
async def get_student_assignment_workspaces(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    education_role = _get_education_role(user)
    if education_role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access writing workspaces",
        )

    assignments = Education.get_assignments_by_student(user.id, db=db)
    items = []

    for assignment in assignments[:MAX_STUDENT_ASSIGNMENTS]:
        session = Education.get_assignment_writing_session(
            assignment.id, user.id, db=db
        )
        if session is None:
            items.append(
                AssignmentWorkspaceListItem(
                    project_mode=PROJECT_MODE_ASSIGNMENT_WRITING,
                    assignment=assignment,
                    project_id=None,
                    status="not_started",
                    updated_at=assignment.updated_at,
                )
            )
            continue

        submitted_at = None
        if session.submitted_submission_id:
            submission = Education.get_submission_by_id(
                session.submitted_submission_id, db=db
            )
            submitted_at = submission.submitted_at if submission else None

        items.append(
            AssignmentWorkspaceListItem(
                project_mode=PROJECT_MODE_ASSIGNMENT_WRITING,
                assignment=assignment,
                project_id=session.folder_id,
                writing_session_id=session.id,
                status=session.status,
                updated_at=max(assignment.updated_at, session.updated_at),
                submitted_at=submitted_at,
            )
        )

    return sorted(items, key=lambda item: item.updated_at, reverse=True)


@router.post("/writing-sessions/{session_id}/autosave")
async def autosave_writing_session(
    form_data: AutosaveForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    db: Session = Depends(get_session),
):
    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Writing note is missing"
        )
    await Notes.update_note_by_id(
        session.note_id,
        NoteForm(
            title=note.title,
            data={
                "content": {
                    "json": form_data.content_json,
                    "html": form_data.content_html,
                    "md": form_data.content_text,
                }
            },
            meta=note.meta,
            access_grants=note.access_grants,
        ),
        db=db,
    )
    Education.touch_writing_session(session.id, db=db)
    return {"ok": True, "saved_at": int(time.time())}


@router.post("/writing-sessions/{session_id}/versions")
async def create_writing_version(
    form_data: VersionCreateForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    db: Session = Depends(get_session),
):
    version = Education.insert_version(
        session.id,
        form_data.trigger_type,
        form_data.content_json,
        form_data.content_text,
        db=db,
    )
    Education.touch_writing_session(session.id, db=db)
    return version


@router.post("/writing-sessions/{session_id}/provenance")
async def create_provenance_segments(
    form_data: ProvenanceCreateForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    db: Session = Depends(get_session),
):
    return Education.insert_provenance_segments(
        session.id,
        form_data.segments,
        version_id=form_data.version_id,
        replace_existing=form_data.replace_existing,
        db=db,
    )


@router.post("/writing-sessions/{session_id}/operations")
async def create_editor_operations(
    form_data: EditorOperationCreateForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    return Education.insert_editor_operations(
        session.id,
        user.id,
        form_data.operations,
        db=db,
    )


@router.post("/writing-sessions/{session_id}/chat/messages/{message_id}")
async def upsert_writing_chat_message(
    message_id: str,
    form_data: ChatMessageUpsertForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    active_chat_id = session.active_chat_id or session.chat_id
    if active_chat_id is None:
        prompt_preview = (form_data.message or {}).get("content", "")[
            :50
        ].strip() or "New Chat"
        chat = await Chats.insert_new_chat(
            str(uuid.uuid4()),
            user.id,
            ChatForm(
                chat={
                    "title": prompt_preview,
                    "models": [],
                    "params": {},
                    "history": {"messages": {}, "currentId": None},
                    "messages": [],
                },
                folder_id=session.folder_id,
            ),
            db=db,
        )
        session = Education.update_writing_session_context(
            session.id,
            chat_id=chat.id,
            active_chat_id=chat.id,
            db=db,
        )
        active_chat_id = chat.id

    # Current signature is (id, message_id, message) — no db kwarg.
    chat = await Chats.upsert_message_to_chat_by_id_and_message_id(
        active_chat_id,
        message_id,
        form_data.message,
    )
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to upsert chat message",
        )
    return {"ok": True}


@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    form_data: SubmissionCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignment = _get_assignment_or_404(assignment_id, db)
    role = _ensure_assignment_access(user, assignment, db)
    if role not in ("student", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can submit assignments",
        )
    if assignment.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment is not open for submission",
        )

    session = _get_workspace_session_or_404(form_data.writing_session_id, db)
    if session.scope != "assignment":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid writing scope"
        )
    if session.assignment_id != assignment.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Mismatched session"
        )
    _ensure_workspace_session_owner(user, session)

    # 已批改即定稿,提前拦下,免得白跑一遍保存与分析。
    current_submission = Education.get_current_submission(
        assignment.id, session.owner_user_id, db=db
    )
    if current_submission is not None:
        current_review = Education.get_submission_review_by_submission_id(
            current_submission.id, db=db
        )
        if current_review is not None and current_review.review_status == "reviewed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Submission has already been reviewed",
            )

    # 截止时间按会话归属人算:管理员代提交时不应套用管理员自己的轮次。
    effective_due_at = _get_effective_due_at(assignment, session.owner_user_id, db)
    if effective_due_at is not None and effective_due_at <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment due time has passed",
        )

    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Writing note is missing"
        )
    await Notes.update_note_by_id(
        session.note_id,
        NoteForm(
            title=note.title,
            data={
                "content": {
                    "json": form_data.final_content_json,
                    "html": form_data.final_content_html,
                    "md": form_data.final_content_text,
                }
            },
            meta=note.meta,
            access_grants=note.access_grants,
        ),
        db=db,
    )

    final_version = Education.insert_version(
        session.id,
        "submit",
        form_data.final_content_json,
        form_data.final_content_text,
        db=db,
    )
    versions = Education.get_versions(session.id, db=db)
    provenance_segments = Education.get_provenance_segments(session.id, db=db)
    normalized_segments = [
        NormalizedSegment(segment) for segment in provenance_segments
    ]
    source_map_highlights = build_source_map_highlights(
        form_data.final_content_text,
        normalized_segments,
    )
    segments = (
        source_map_highlights
        if source_map_highlights is not None
        else filter_segments_for_final_text(
            form_data.final_content_text, normalized_segments
        )
    )
    prompt_timeline = await get_prompt_timeline(session, db)
    prompt_count = len(
        [message for message in prompt_timeline if message.get("role") == "user"]
    )
    if source_map_highlights is not None:
        stats = compute_stats_from_highlights(
            form_data.final_content_text,
            source_map_highlights,
            prompt_count=prompt_count,
            version_count=len(versions),
        )
    else:
        stats = compute_stats(
            form_data.final_content_text,
            segments,
            prompt_count=prompt_count,
            version_count=len(versions),
        )
    reflection = Education.insert_micro_reflection(
        assignment.id,
        session.owner_user_id,
        session.id,
        form_data.ai_used,
        form_data.ai_help_types,
        form_data.reflection,
        db=db,
    )
    try:
        submission = Education.insert_submission(
            assignment.id,
            session.owner_user_id,
            session.id,
            final_version.id,
            stats,
            reflection.id,
            db=db,
        )
    except SubmissionAlreadyReviewedError:
        # 上面已提前拦过一次,这里兜住「批改与提交并发」的窄窗口。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submission has already been reviewed",
        )
    except IntegrityError:
        # 唯一约束 (assignment_id, student_id, round_no):同一轮已被并发请求写入。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A submission for this round is already being processed",
        )
    analysis_payload = build_submission_analysis(
        submission,
        session,
        versions,
        Education.get_provenance_segments(session.id, db=db),
        Education.get_editor_operations(session.id, db=db),
        prompt_timeline,
    )
    Education.upsert_analysis_result(
        session.id,
        "submission_analysis",
        analysis_payload,
        submission_id=submission.id,
        db=db,
    )
    await _send_education_notifications(
        [assignment.teacher_id],
        "submission_created",
        {
            "assignment_id": assignment.id,
            "assignment_title": assignment.title,
            "submission_id": submission.id,
            "student_id": user.id,
            "student_name": user.name,
            "round_no": submission.round_no,
        },
        db,
    )
    return {"submission_id": submission.id, "final_version_id": final_version.id}


@router.get(
    "/assignments/{assignment_id}/me/submissions",
    response_model=MyAssignmentSubmissionsResponse,
)
async def get_my_assignment_submissions(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignment = _get_assignment_or_404(assignment_id, db)
    role = _ensure_assignment_access(user, assignment, db)
    if role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view their own submission history",
        )

    submissions = sorted(
        Education.get_submission_rounds(assignment.id, user.id, db=db),
        key=lambda submission: submission.round_no,
    )

    rounds = []
    for submission in submissions:
        version = Education.get_version_by_id(submission.final_version_id, db=db)
        review = Education.get_submission_review_by_submission_id(
            submission.id, db=db
        )
        rounds.append(
            MySubmissionRound(
                submission_id=submission.id,
                round_no=submission.round_no,
                is_current=submission.is_current,
                submitted_at=submission.submitted_at,
                content=MySubmissionRoundContent(
                    content_json=version.note_snapshot_json if version else None,
                    content_text=(version.note_snapshot_text if version else "")
                    or "",
                ),
                review=(
                    MySubmissionRoundReview(
                        review_status=review.review_status,
                        score=review.score,
                        rubric=review.rubric_scores,
                        overall_comment=review.overall_comment,
                        returned_comment=review.returned_comment,
                        resubmit_due_at=review.resubmit_due_at,
                        reviewed_at=review.reviewed_at,
                    )
                    if review is not None
                    else None
                ),
            )
        )

    return MyAssignmentSubmissionsResponse(assignment_id=assignment.id, rounds=rounds)


@router.get(
    "/teacher/assignments/{assignment_id}/submissions",
    response_model=list[SubmissionListItem],
)
async def get_assignment_submissions(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    submissions = Education.get_submissions_by_assignment(assignment.id, db=db)

    return [
        await _build_submission_list_item(submission, assignment, db)
        for submission in submissions
    ]


@router.get(
    "/teacher/submissions/{submission_id}", response_model=SubmissionDetailResponse
)
async def get_submission_detail(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    submission, assignment = scope
    session = _get_workspace_session_or_404(submission.writing_session_id, db)
    versions = Education.get_versions(session.id, db=db)
    analysis = await get_or_build_submission_analysis(submission, session, db)
    provenance_segments = filter_segments_for_final_text(
        (versions[-1].note_snapshot_text if versions else "") or "",
        Education.get_provenance_segments(session.id, db=db),
    )
    reflection = Education.get_micro_reflection_by_id(
        submission.micro_reflection_id, db=db
    )
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    prompt_timeline = await get_prompt_timeline(session, db)
    student = await Users.get_user_by_id(submission.student_id, db=db)
    note = await Notes.get_note_by_id(session.note_id, db=db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Writing note is missing"
        )
    final_version = next(
        (version for version in versions if version.id == submission.final_version_id),
        None,
    )
    if final_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission final version not found",
        )

    rounds = []
    for item in Education.get_submission_rounds(
        submission.assignment_id, submission.student_id, db=db
    ):
        item_review = Education.get_submission_review_by_submission_id(item.id, db=db)
        rounds.append(
            {
                "submission_id": item.id,
                "round_no": item.round_no,
                "submitted_at": item.submitted_at,
                "is_current": item.is_current,
                "review_status": (
                    item_review.review_status if item_review else "pending"
                ),
                "score": item_review.score if item_review else None,
            }
        )

    return SubmissionDetailResponse(
        submission=submission,
        assignment=assignment,
        writing_session=session,
        final_version=final_version,
        versions=[
            WritingVersionSummaryModel.model_validate(version)
            for version in versions[-SUBMISSION_DETAIL_VERSION_LIMIT:]
        ],
        version_count=len(versions),
        provenance_segments=provenance_segments,
        prompt_timeline=prompt_timeline,
        micro_reflection=reflection,
        review=review,
        note=note.model_dump(),
        student_name=student.name if student else submission.student_id,
        analysis=analysis,
        rounds=rounds,
    )


@router.get(
    "/teacher/submissions/{submission_id}/versions",
    response_model=list[WritingVersionSummaryModel],
)
async def get_submission_versions(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    session = _get_workspace_session_or_404(scope.submission.writing_session_id, db)
    return [
        WritingVersionSummaryModel.model_validate(version)
        for version in Education.get_versions(session.id, db=db)
    ]


@router.get("/teacher/submissions/{submission_id}/diff")
async def get_submission_round_diff(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    submission = scope.submission
    previous = next(
        (
            item
            for item in Education.get_submission_rounds(
                submission.assignment_id, submission.student_id, db=db
            )
            if item.round_no == submission.round_no - 1
        ),
        None,
    )
    if previous is None:
        return {"has_previous": False, "previous_round_no": None, "blocks": []}

    current_version = Education.get_version_by_id(submission.final_version_id, db=db)
    previous_version = Education.get_version_by_id(previous.final_version_id, db=db)
    old_text = (previous_version.note_snapshot_text or "") if previous_version else ""
    new_text = (current_version.note_snapshot_text or "") if current_version else ""
    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    blocks = [
        {
            "op": op,
            "old_text": old_text[i1:i2],
            "new_text": new_text[j1:j2],
        }
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
    ]
    return {
        "has_previous": True,
        "previous_round_no": previous.round_no,
        "blocks": blocks,
    }


@router.post("/teacher/submissions/{submission_id}/analysis")
async def recompute_submission_analysis(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    submission = scope.submission
    if submission.is_current != 1:
        # 历史轮只读:重算会用当前会话数据覆盖该轮的 analysis_result
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Historical submission rounds are read-only",
        )
    session = _get_workspace_session_or_404(submission.writing_session_id, db)
    versions = Education.get_versions(session.id, db=db)
    prompt_timeline = await get_prompt_timeline(session, db)
    payload = build_submission_analysis(
        submission,
        session,
        versions,
        Education.get_provenance_segments(session.id, db=db),
        Education.get_editor_operations(session.id, db=db),
        prompt_timeline,
    )
    Education.upsert_analysis_result(
        session.id,
        "submission_analysis",
        payload,
        submission_id=submission.id,
        db=db,
    )
    return payload


async def _load_submission_analysis(
    scope: TeacherSubmissionScope, db: Session
) -> dict:
    session = _get_workspace_session_or_404(scope.submission.writing_session_id, db)
    return await get_or_build_submission_analysis(scope.submission, session, db)


@router.get("/teacher/submissions/{submission_id}/analysis")
async def get_submission_analysis(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    return await _load_submission_analysis(scope, db)


@router.get("/teacher/submissions/{submission_id}/analysis/summary")
async def get_submission_analysis_summary(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    analysis = await _load_submission_analysis(scope, db)
    return analysis.get("summary", {})


@router.get("/teacher/submissions/{submission_id}/analysis/timeline")
async def get_submission_analysis_timeline(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    analysis = await _load_submission_analysis(scope, db)
    return analysis.get("timeline", [])


@router.get("/teacher/submissions/{submission_id}/analysis/highlights")
async def get_submission_analysis_highlights(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    analysis = await _load_submission_analysis(scope, db)
    return analysis.get("highlights", [])


@router.get("/teacher/submissions/{submission_id}/analysis/segments")
async def get_submission_analysis_segments(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    analysis = await _load_submission_analysis(scope, db)
    return analysis.get("segments", [])


@router.get("/teacher/submissions/{submission_id}/analysis/segments/{segment_id}")
async def get_submission_analysis_segment_detail(
    segment_id: str,
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    analysis = await _load_submission_analysis(scope, db)
    segment = next(
        (
            item
            for item in analysis.get("segments", [])
            if item.get("segment_id") == segment_id
        ),
        None,
    )
    if segment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found"
        )
    return segment


@router.get("/teacher/submissions/{submission_id}/review")
async def get_submission_review(
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    db: Session = Depends(get_session),
):
    submission = scope.submission
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    return (
        review.model_dump()
        if review
        else {"submission_id": submission.id, "review_status": "pending"}
    )


@router.post("/teacher/submissions/{submission_id}/review")
async def save_submission_review(
    form_data: SubmissionReviewForm,
    scope: TeacherSubmissionScope = Depends(require_teacher_submission),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    submission, assignment = scope
    if form_data.review_status not in {"pending", "reviewed", "returned"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review status",
        )
    if form_data.score is not None and form_data.score > assignment.score_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Score must be between 0 and {assignment.score_max}",
        )
    rubric_criteria = {
        criterion.key: criterion for criterion in assignment.rubric_schema.criteria
    }
    if form_data.rubric_scores is not None:
        if set(form_data.rubric_scores) != set(rubric_criteria):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rubric scores must include every configured criterion exactly once",
            )
        for key, value in form_data.rubric_scores.items():
            if value < 0 or value > rubric_criteria[key].max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Rubric score for {key} must be between 0 and {rubric_criteria[key].max_score}",
                )
        rubric_total = sum(form_data.rubric_scores.values())
        if form_data.score is not None and rubric_total != form_data.score:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Total score must equal the sum of rubric scores",
            )
    if form_data.review_status == "reviewed" and (
        form_data.score is None or form_data.rubric_scores is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviewed submissions require a total score and complete rubric scores",
        )
    if not submission.is_current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Historical submission rounds are read-only",
        )
    if form_data.review_status == "returned":
        if (
            form_data.resubmit_due_at is None
            or form_data.resubmit_due_at <= int(time.time())
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A future resubmit due time is required when returning",
            )

    review = Education.upsert_submission_review(
        submission.id,
        assignment.id,
        user.id,
        form_data,
        db=db,
    )
    if form_data.review_status == "returned":
        Education.set_writing_session_status(
            submission.writing_session_id, "draft", db=db
        )

    if form_data.review_status == "reviewed":
        await _send_education_notifications(
            [submission.student_id],
            "review_completed",
            {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "score": form_data.score,
            },
            db,
        )
    elif form_data.review_status == "returned":
        await _send_education_notifications(
            [submission.student_id],
            "submission_returned",
            {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "returned_comment": form_data.returned_comment,
                "resubmit_due_at": form_data.resubmit_due_at,
            },
            db,
        )
    return review


@router.get(
    "/teacher/assignments/{assignment_id}/dashboard", response_model=DashboardResponse
)
async def get_teacher_dashboard(
    assignment: AssignmentModel = Depends(require_teacher_assignment),
    db: Session = Depends(get_session),
):
    submissions = Education.get_submissions_by_assignment(assignment.id, db=db)

    items = []
    rewrite_distribution = {
        "unchanged": 0,
        "lightly_edited": 0,
        "moderately_rewritten": 0,
        "deeply_rewritten": 0,
    }
    summary = empty_risk_summary()
    # 学生、写作会话、微反思都按批取回,班级规模变大时看板不再是 N+1。
    students = {
        student.id: student
        for student in await Users.get_users_by_user_ids(
            list({submission.student_id for submission in submissions}), db=db
        )
    }
    sessions = Education.get_writing_sessions_by_ids(
        [submission.writing_session_id for submission in submissions], db=db
    )
    reflections = Education.get_micro_reflections_by_ids(
        [submission.micro_reflection_id for submission in submissions], db=db
    )
    analyses = await get_or_build_submission_analyses(submissions, sessions, db)
    for submission in submissions:
        student = students.get(submission.student_id)
        analysis = analyses.get(submission.id) or {}
        accumulate_risk_summary(summary, analysis.get("summary"))
        for segment in analysis.get("segments", []):
            rewrite_level = segment.get("rewrite_level")
            if rewrite_level in rewrite_distribution:
                rewrite_distribution[rewrite_level] += 1
        items.append(
            DashboardItem(
                submission_id=submission.id,
                student_id=submission.student_id,
                student_name=student.name if student else submission.student_id,
                source_stats=submission.stats_json,
                prompt_count=submission.stats_json.get("prompt_count", 0),
                has_reflection=submission.micro_reflection_id in reflections,
                submitted_at=submission.submitted_at,
                risk_summary=analysis.get("summary", {}),
            )
        )
    return DashboardResponse(
        items=items,
        summary=finalize_risk_summary(summary),
        distributions={
            "rewrite_levels": rewrite_distribution,
            "submission_count": len(items),
        },
    )


@router.get("/me/writing/profile", response_model=StudentProfileResponse)
async def get_my_writing_profile(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    membership = Education.get_classroom_member_by_user_id(user.id, db=db)
    classroom = (
        Education.get_classroom_by_id(membership.classroom_id, db=db)
        if membership
        else None
    )
    assignments = Education.get_assignments_by_student(user.id, db=db)[
        :MAX_STUDENT_ASSIGNMENTS
    ]
    return await build_student_profile(user, user.id, classroom, assignments, db)


@router.get("/me/writing/assignments", response_model=list[StudentAssignmentListItem])
async def get_student_assignments(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignments = Education.get_assignments_by_student(user.id, db=db)[
        :MAX_STUDENT_ASSIGNMENTS
    ]
    membership = Education.get_classroom_member_by_user_id(user.id, db=db)
    items = []

    for assignment in assignments:
        session = Education.get_assignment_writing_session(
            assignment.id, user.id, db=db
        )
        submission = None
        if session and session.submitted_submission_id:
            submission = Education.get_submission_by_id(
                session.submitted_submission_id, db=db
            )

        items.append(
            StudentAssignmentListItem(
                assignment=assignment,
                membership=membership,
                has_submission=submission is not None,
                submission_id=submission.id if submission else None,
                writing_session_id=session.id if session else None,
            )
        )

    return items


@router.post("/writing-sessions/{session_id}/active-chat", response_model=dict)
async def update_writing_session_active_chat(
    form_data: ActiveChatUpdateForm,
    session: WritingSessionModel = Depends(require_owned_writing_session),
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    chat_id = form_data.chat_id
    if chat_id is not None:
        chat = await Chats.get_chat_by_id_and_user_id(chat_id, user.id, db=db)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        if session.folder_id and chat.folder_id != session.folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chat does not belong to this assignment project",
            )

    updated = Education.update_writing_session_context(
        session.id,
        chat_id=session.chat_id,
        active_chat_id=chat_id,
        db=db,
    )
    return {
        "writing_session": updated.model_dump(),
        "active_chat_id": updated.active_chat_id,
    }


@router.get("/me/notifications/summary")
async def get_my_notification_summary(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    return Education.get_unread_notification_summary(user.id, db=db)


@router.post("/me/notifications/mark-read")
async def mark_my_notifications_read(
    form_data: NotificationMarkReadForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    marked = Education.mark_notifications_read(
        user.id,
        types=form_data.types,
        assignment_id=form_data.assignment_id,
        db=db,
    )
    return {"marked": marked}
