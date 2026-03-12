import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.chats import ChatForm, Chats
from open_webui.models.chat_messages import ChatMessages
from open_webui.models.education import (
    AssignmentModel,
    AssignmentMemberCreateForm,
    AssignmentCreateForm,
    AssignmentWorkspaceResponse,
    AutosaveForm,
    ClassroomCreateForm,
    ClassroomJoinForm,
    ClassroomMemberDetail,
    ClassroomResponse,
    DashboardItem,
    DashboardResponse,
    Education,
    ProvenanceCreateForm,
    Submission,
    SubmissionCreateForm,
    SubmissionDetailResponse,
    SubmissionListItem,
    StudentAssignmentListItem,
    TeacherAssignmentListItem,
    VersionCreateForm,
)
from open_webui.models.notes import NoteForm, Notes
from open_webui.models.users import Users
from open_webui.utils.auth import get_verified_user

router = APIRouter()

MAX_STUDENT_ASSIGNMENTS = 100
MAX_DASHBOARD_ITEMS = 50


class ChatMessageUpsertForm(BaseModel):
    message: dict


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


def _build_assignment_member_detail(member, db: Session):
    linked_user = Users.get_user_by_id(member.user_id, db=db)
    linked_user_info = linked_user.info if linked_user and linked_user.info else {}
    return AssignmentMemberDetail(
        member=member,
        user_name=linked_user.name if linked_user else member.user_id,
        user_email=linked_user.email if linked_user else None,
        education_role=linked_user_info.get("education_role"),
    )


def _build_classroom_member_detail(member, db: Session):
    linked_user = Users.get_user_by_id(member.user_id, db=db)
    linked_user_info = linked_user.info if linked_user and linked_user.info else {}
    return ClassroomMemberDetail(
        member=member,
        user_name=linked_user.name if linked_user else member.user_id,
        user_email=linked_user.email if linked_user else None,
        education_role=linked_user_info.get("education_role"),
    )


def _ensure_classroom_access(user, classroom, db: Session, require_teacher: bool = False):
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


def _make_default_chat(title: str) -> dict:
    return {
        "title": title,
        "models": [],
        "params": {},
        "history": {"messages": {}, "currentId": None},
        "messages": [],
    }


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


def _get_assignment_or_404(assignment_id: str, db: Session) -> AssignmentModel:
    assignment = Education.get_assignment_by_id(assignment_id, db=db)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    return assignment


def _get_workspace_session_or_404(session_id: str, db: Session):
    session = Education.get_writing_session_by_id(session_id, db=db)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing session not found"
        )
    return session


def _get_assignment_classroom_or_404(assignment, db: Session):
    classroom_id = assignment.classroom_id
    if classroom_id is None:
        classroom_id = Education.ensure_default_classroom_for_teacher(
            assignment.teacher_id, db=db
        ).id
        assignment = Education.update_assignment_classroom(assignment.id, classroom_id, db=db)

    classroom = Education.get_classroom_by_id(classroom_id, db=db)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found",
        )
    return classroom


def _ensure_assignment_access(user, assignment, db: Session, require_teacher: bool = False):
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


def _filter_segments_for_final_text(final_text: str, segments):
    remaining_text = final_text or ""
    filtered_segments = []
    for segment in segments:
        segment_text = segment.segment_text or ""
        if not segment_text:
            continue
        index = remaining_text.find(segment_text)
        if index == -1:
            continue
        filtered_segments.append(segment)
        remaining_text = (
            remaining_text[:index]
            + (" " * len(segment_text))
            + remaining_text[index + len(segment_text) :]
        )
    return filtered_segments


def _compute_stats(final_text: str, segments, prompt_count: int, version_count: int) -> dict:
    stats = {
        "total_chars": len(final_text or ""),
        "user_typed_chars": 0,
        "ai_inserted_chars": 0,
        "ai_pasted_chars": 0,
        "prompt_count": prompt_count,
        "version_count": version_count,
    }
    for segment in segments:
        key = f"{segment.source_type}_chars"
        if key in stats:
            stats[key] += len(segment.segment_text or "")
    return stats


def _get_chat_history_messages(chat) -> list[dict]:
    if chat is None:
        return []

    chat_payload = getattr(chat, "chat", None) or {}
    history = chat_payload.get("history") or {}
    messages = history.get("messages") or {}
    current_id = history.get("currentId")
    ordered_messages = []
    visited = set()

    while current_id and current_id in messages and current_id not in visited:
        message = messages[current_id]
        ordered_messages.append(message)
        visited.add(current_id)
        current_id = message.get("parentId")

    ordered_messages.reverse()
    return ordered_messages


def _get_prompt_timeline(session, db: Session) -> list[dict]:
    chat_messages = ChatMessages.get_messages_by_chat_id(session.chat_id, db=db)
    if chat_messages:
        return [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in chat_messages
        ]

    chat = Chats.get_chat_by_id(session.chat_id, db=db)
    history_messages = _get_chat_history_messages(chat)
    return [
        {
            "id": message.get("id"),
            "role": message.get("role"),
            "content": message.get("content"),
            "created_at": message.get("timestamp"),
        }
        for message in history_messages
    ]


@router.post("/assignments", response_model=AssignmentModel)
async def create_assignment(
    form_data: AssignmentCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    return Education.insert_assignment(user.id, form_data, db=db)


@router.get("/me/classroom", response_model=ClassroomResponse)
async def get_my_classroom(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    education_role = _get_education_role(user)
    if education_role == "teacher" or user.role == "admin":
        classroom = Education.ensure_default_classroom_for_teacher(user.id, db=db)
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
    existing = Education.get_classroom_by_teacher(user.id, db=db)
    classroom = existing or Education.insert_classroom(user.id, form_data, db=db)
    membership = Education.get_classroom_member(classroom.id, user.id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.post("/classrooms/join", response_model=ClassroomResponse)
async def join_classroom(
    form_data: ClassroomJoinForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
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

    membership = Education.ensure_classroom_member(classroom.id, user.id, "student", db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.post("/classrooms/{classroom_id}/invite-code/regenerate", response_model=ClassroomResponse)
async def regenerate_classroom_invite_code(
    classroom_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    classroom = Education.get_classroom_by_id(classroom_id, db=db)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found",
        )
    _ensure_classroom_access(user, classroom, db, require_teacher=True)

    classroom = Education.regenerate_classroom_invite_code(classroom_id, db=db)
    membership = Education.get_classroom_member(classroom.id, user.id, db=db)
    return ClassroomResponse(classroom=classroom, membership=membership)


@router.get("/teacher/assignments", response_model=list[TeacherAssignmentListItem])
async def get_teacher_assignments(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    Education.ensure_default_classroom_for_teacher(user.id, db=db)
    assignments = Education.get_assignments_by_teacher(user.id, db=db)

    items = []
    for assignment in assignments:
        classroom_id = assignment.classroom_id or Education.ensure_default_classroom_for_teacher(
            user.id, db=db
        ).id
        student_count = len(Education.get_classroom_members(classroom_id, member_role="student", db=db))
        submission_count = len(Education.get_submissions_by_assignment(assignment.id, db=db))
        items.append(
            TeacherAssignmentListItem(
                assignment=assignment,
                student_count=student_count,
                submission_count=submission_count,
            )
        )

    return items


@router.get(
    "/teacher/assignments/{assignment_id}/members",
    response_model=list[ClassroomMemberDetail],
)
async def get_assignment_members(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    classroom = _get_assignment_classroom_or_404(assignment, db)
    members = Education.get_classroom_members(classroom.id, member_role="student", db=db)
    return [_build_classroom_member_detail(member, db) for member in members]


@router.post(
    "/teacher/assignments/{assignment_id}/members",
    response_model=ClassroomMemberDetail,
)
async def add_assignment_member(
    assignment_id: str,
    form_data: AssignmentMemberCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    classroom = _get_assignment_classroom_or_404(assignment, db)
    member_user = Users.get_user_by_id(form_data.user_id, db=db)
    if member_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    education_role = ((member_user.info or {}).get("education_role") if member_user.info else None)
    if education_role != "student":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only users with student identity can be added",
        )

    existing_membership = Education.get_classroom_member_by_user_id(member_user.id, db=db)
    if existing_membership is not None and existing_membership.classroom_id != classroom.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already linked to another classroom",
        )

    member = Education.ensure_classroom_member(
        classroom.id, member_user.id, "student", db=db
    )
    return _build_classroom_member_detail(member, db)


@router.delete("/teacher/assignments/{assignment_id}/members/{member_user_id}")
async def delete_assignment_member(
    assignment_id: str,
    member_user_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    classroom = _get_assignment_classroom_or_404(assignment, db)

    if assignment.teacher_id == member_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teacher membership cannot be removed",
        )

    deleted = Education.delete_classroom_member(classroom.id, member_user_id, db=db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment member not found",
        )

    return {"ok": True}


@router.get("/assignments/{assignment_id}/workspace", response_model=AssignmentWorkspaceResponse)
async def get_assignment_workspace(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignment = Education.get_assignment_by_id(assignment_id, db=db)
    if assignment is None:
        if user.role == "admin":
            classroom = Education.ensure_default_classroom_for_teacher(user.id, db=db)
            assignment = Education.insert_assignment(
                user.id,
                AssignmentCreateForm(
                    title="Growth Writing Assignment",
                    description="Autocreated writing assignment",
                    classroom_id=classroom.id,
                ),
                db=db,
            )
            assignment_id = assignment.id
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
            )

    _ensure_assignment_access(user, assignment, db)
    classroom_member = None
    if assignment.classroom_id:
        classroom_member = Education.get_classroom_member(assignment.classroom_id, user.id, db=db)
    membership_role = "teacher" if assignment.teacher_id == user.id else classroom_member.member_role

    session = Education.get_writing_session(assignment_id, user.id, db=db)
    if session is None:
        note = Notes.insert_new_note(
            user.id, _make_default_note(assignment.title, assignment_id), db=db
        )
        chat = Chats.insert_new_chat(
            user.id, ChatForm(chat=_make_default_chat(assignment.title)), db=db
        )
        session = Education.insert_writing_session(
            assignment_id, user.id, note.id, chat.id, db=db
        )
    else:
        note = Notes.get_note_by_id(session.note_id, db=db)
        chat = Chats.get_chat_by_id(session.chat_id, db=db)

    return AssignmentWorkspaceResponse(
        assignment=assignment,
        membership_role=membership_role,
        writing_session=session,
        note=note.model_dump(),
        chat=chat.model_dump(),
    )


@router.post("/writing-sessions/{session_id}/autosave")
async def autosave_writing_session(
    session_id: str,
    form_data: AutosaveForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    session = _get_workspace_session_or_404(session_id, db)
    if user.role != "admin" and session.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    note = Notes.get_note_by_id(session.note_id, db=db)
    Notes.update_note_by_id(
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
    Education.touch_writing_session(session_id, db=db)
    return {"ok": True, "saved_at": int(time.time())}


@router.post("/writing-sessions/{session_id}/versions")
async def create_writing_version(
    session_id: str,
    form_data: VersionCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    session = _get_workspace_session_or_404(session_id, db)
    if user.role != "admin" and session.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    version = Education.insert_version(
        session_id,
        form_data.trigger_type,
        form_data.content_json,
        form_data.content_text,
        db=db,
    )
    Education.touch_writing_session(session_id, db=db)
    return version


@router.post("/writing-sessions/{session_id}/provenance")
async def create_provenance_segments(
    session_id: str,
    form_data: ProvenanceCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    session = _get_workspace_session_or_404(session_id, db)
    if user.role != "admin" and session.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return Education.insert_provenance_segments(
        session_id, form_data.segments, version_id=form_data.version_id, db=db
    )


@router.post("/writing-sessions/{session_id}/chat/messages/{message_id}")
async def upsert_writing_chat_message(
    session_id: str,
    message_id: str,
    form_data: ChatMessageUpsertForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    session = _get_workspace_session_or_404(session_id, db)
    if user.role != "admin" and session.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    chat = Chats.upsert_message_to_chat_by_id_and_message_id(
        session.chat_id,
        message_id,
        form_data.message,
        db=db,
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
    if len(form_data.reflection_text.strip()) < 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reflection text must be at least 30 characters",
        )

    assignment = _get_assignment_or_404(assignment_id, db)
    session = _get_workspace_session_or_404(form_data.writing_session_id, db)
    if session.assignment_id != assignment.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mismatched session")
    if user.role != "admin" and session.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    note = Notes.get_note_by_id(session.note_id, db=db)
    Notes.update_note_by_id(
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
    segments = _filter_segments_for_final_text(
        form_data.final_content_text,
        Education.get_provenance_segments(session.id, db=db),
    )
    prompt_timeline = _get_prompt_timeline(session, db)
    prompt_count = len([message for message in prompt_timeline if message.get("role") == "user"])
    stats = _compute_stats(
        form_data.final_content_text,
        segments,
        prompt_count=prompt_count,
        version_count=len(versions),
    )
    reflection = Education.insert_micro_reflection(
        assignment.id,
        session.student_id,
        session.id,
        form_data.ai_help_type,
        form_data.reflection_text,
        db=db,
    )
    submission = Education.insert_submission(
        assignment.id,
        session.student_id,
        session.id,
        final_version.id,
        stats,
        reflection.id,
        db=db,
    )
    return {"submission_id": submission.id, "final_version_id": final_version.id}


@router.get("/teacher/assignments/{assignment_id}/submissions", response_model=list[SubmissionListItem])
async def get_assignment_submissions(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    submissions = Education.get_submissions_by_assignment(assignment_id, db=db)

    items = []
    for submission in submissions:
        session = Education.get_writing_session_by_id(submission.writing_session_id, db=db)
        reflection = Education.get_micro_reflection_by_id(submission.micro_reflection_id, db=db)
        student = Users.get_user_by_id(submission.student_id, db=db)
        items.append(
            SubmissionListItem(
                submission=submission,
                session=session,
                assignment=assignment,
                reflection=reflection,
                student_name=student.name if student else submission.student_id,
            )
        )
    return items


@router.get("/teacher/submissions/{submission_id}", response_model=SubmissionDetailResponse)
async def get_submission_detail(
    submission_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    submission = Education.get_submission_by_id(submission_id, db=db)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    assignment = _get_assignment_or_404(submission.assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    session = _get_workspace_session_or_404(submission.writing_session_id, db)
    versions = Education.get_versions(session.id, db=db)
    provenance_segments = _filter_segments_for_final_text(
        (versions[-1].note_snapshot_text if versions else "") or "",
        Education.get_provenance_segments(session.id, db=db),
    )
    reflection = Education.get_micro_reflection_by_id(submission.micro_reflection_id, db=db)
    prompt_timeline = _get_prompt_timeline(session, db)
    student = Users.get_user_by_id(submission.student_id, db=db)
    note = Notes.get_note_by_id(session.note_id, db=db)
    final_version = next(
        version for version in versions if version.id == submission.final_version_id
    )

    return SubmissionDetailResponse(
        submission=submission,
        assignment=assignment,
        writing_session=session,
        final_version=final_version,
        versions=versions,
        provenance_segments=provenance_segments,
        prompt_timeline=prompt_timeline,
        micro_reflection=reflection,
        note=note.model_dump(),
        student_name=student.name if student else submission.student_id,
    )


@router.get("/teacher/assignments/{assignment_id}/dashboard", response_model=DashboardResponse)
async def get_teacher_dashboard(
    assignment_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    assignment = _get_assignment_or_404(assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)
    submissions = Education.get_submissions_by_assignment(assignment_id, db=db)

    items = []
    for submission in submissions:
        student = Users.get_user_by_id(submission.student_id, db=db)
        items.append(
            DashboardItem(
                submission_id=submission.id,
                student_id=submission.student_id,
                student_name=student.name if student else submission.student_id,
                source_stats=submission.stats_json,
                prompt_count=submission.stats_json.get("prompt_count", 0),
                has_reflection=True,
                submitted_at=submission.submitted_at,
            )
        )
    return DashboardResponse(items=items)


@router.get("/me/writing/dashboard", response_model=DashboardResponse)
async def get_student_dashboard(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    rows = (
        db.query(Submission)
        .filter(Submission.student_id == user.id)
        .order_by(Submission.submitted_at.desc())
        .limit(MAX_DASHBOARD_ITEMS)
        .all()
    )
    items = [
        DashboardItem(
            submission_id=row.id,
            student_id=row.student_id,
            student_name=user.name,
            source_stats=row.stats_json,
            prompt_count=row.stats_json.get("prompt_count", 0),
            has_reflection=True,
            submitted_at=row.submitted_at,
        )
        for row in rows
    ]
    return DashboardResponse(items=items)


@router.get("/me/writing/assignments", response_model=list[StudentAssignmentListItem])
async def get_student_assignments(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    assignments = Education.get_assignments_by_student(user.id, db=db)[:MAX_STUDENT_ASSIGNMENTS]
    items = []

    for assignment in assignments:
        membership = Education.get_classroom_member_by_user_id(user.id, db=db)
        session = Education.get_writing_session(assignment.id, user.id, db=db)
        submission = None
        if session and session.submitted_submission_id:
            submission = Education.get_submission_by_id(session.submitted_submission_id, db=db)

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
