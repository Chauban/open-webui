import asyncio
import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.internal.db import get_session
from open_webui.models.access_grants import AccessGrant
from open_webui.models.automations import AutomationRun
from open_webui.models.chats import Chat
from open_webui.models.chat_messages import ChatMessage
from open_webui.models.shared_chats import SharedChat
from open_webui.models.education import (
    Assignment,
    Classroom,
    ClassroomMember,
    EducationNotification,
    MicroReflection,
    ProvenanceSegment,
    Submission,
    SubmissionReview,
    WritingSession,
    WritingVersion,
)
from open_webui.models.config import Config
from open_webui.models.folders import Folder, FolderForm, FolderUpdateForm, Folders
from open_webui.models.groups import Group, GroupMember
from open_webui.models.notes import Note, PinnedNote
from open_webui.models.users import User, UserModel
import open_webui.routers.education as education_router_module
from open_webui.routers.education import router as education_router
from open_webui.routers.chats import router as chats_router
from open_webui.routers.notes import router as notes_router
from open_webui.utils.auth import get_verified_user


def test_filter_segments_prioritizes_full_ai_insert_over_short_typed_fragments():
    final_text = "明白了，你是在追问 Claude 4 的情况。"
    segments = [
        SimpleNamespace(
            segment_id="typed-de", source_type="user_typed", segment_text="de"
        ),
        SimpleNamespace(
            segment_id="typed-h", source_type="user_typed", segment_text="h"
        ),
        SimpleNamespace(
            segment_id="ai-full",
            source_type="ai_inserted",
            segment_text="明白了，你是在追问 Claude 4 的情况。",
        ),
    ]

    filtered = education_router_module._filter_segments_for_final_text(
        final_text, segments
    )

    assert [segment.segment_id for segment in filtered] == ["ai-full"]


def test_filter_segments_removes_low_signal_manual_fragments():
    final_text = "Claude h de 哈哈哈哈"
    segments = [
        SimpleNamespace(
            segment_id="typed-de", source_type="user_typed", segment_text="de"
        ),
        SimpleNamespace(
            segment_id="typed-h", source_type="user_typed", segment_text="h"
        ),
        SimpleNamespace(
            segment_id="typed-laugh", source_type="user_typed", segment_text="哈哈哈哈"
        ),
    ]

    filtered = education_router_module._filter_segments_for_final_text(
        final_text, segments
    )

    assert [segment.segment_id for segment in filtered] == ["typed-laugh"]


def test_submission_analysis_separates_source_map_counts_from_process_events():
    final_text = "typedAIpaste?"
    version = SimpleNamespace(
        id="version-1",
        version_no=1,
        trigger_type="submit",
        created_at=10,
        note_snapshot_text=final_text,
    )
    submission = SimpleNamespace(
        id="submission-1",
        final_version_id="version-1",
        submitted_at=20,
    )
    source_map_segments = [
        SimpleNamespace(
            segment_id="source-map-0",
            source_type="user_typed",
            segment_text="typed",
            source_message_id=None,
            start_offset=0,
            end_offset=5,
            version_id="version-1",
            metadata_json={"provenance_kind": "source_map"},
        ),
        SimpleNamespace(
            segment_id="source-map-1",
            source_type="ai_inserted",
            segment_text="AI",
            source_message_id="assistant-1",
            start_offset=5,
            end_offset=7,
            version_id="version-1",
            metadata_json={"provenance_kind": "source_map"},
        ),
        SimpleNamespace(
            segment_id="source-map-2",
            source_type="external_paste",
            segment_text="paste",
            source_message_id=None,
            start_offset=7,
            end_offset=12,
            version_id="version-1",
            metadata_json={"provenance_kind": "source_map"},
        ),
        SimpleNamespace(
            segment_id="source-map-3",
            source_type="unknown",
            segment_text="?",
            source_message_id=None,
            start_offset=12,
            end_offset=13,
            version_id="version-1",
            metadata_json={"provenance_kind": "source_map"},
        ),
    ]
    operations = [
        SimpleNamespace(
            id="copy-1",
            op_type="ai_copy_button_clicked",
            source_type="ai_pasted",
            start_offset=None,
            end_offset=None,
            inserted_text=None,
            deleted_text=None,
            batch_id="batch-copy",
            metadata_json={"copy_length": 100},
            created_at=11,
        ),
        SimpleNamespace(
            id="insert-1",
            op_type="ai_insert_clicked",
            source_type="ai_inserted",
            start_offset=5,
            end_offset=7,
            inserted_text="AI",
            deleted_text=None,
            batch_id="batch-insert",
            metadata_json=None,
            created_at=12,
        ),
        SimpleNamespace(
            id="paste-1",
            op_type="paste_detected",
            source_type="external_paste",
            start_offset=7,
            end_offset=12,
            inserted_text="paste",
            deleted_text=None,
            batch_id="batch-paste",
            metadata_json={"has_source_metadata": False},
            created_at=13,
        ),
        SimpleNamespace(
            id="delete-1",
            op_type="delete_text",
            source_type="user_typed",
            start_offset=0,
            end_offset=0,
            inserted_text=None,
            deleted_text="old",
            batch_id="batch-delete",
            metadata_json=None,
            created_at=14,
        ),
    ]

    analysis = education_router_module._build_submission_analysis(
        submission,
        SimpleNamespace(id="session-1"),
        [version],
        source_map_segments,
        operations,
        [{"role": "user", "content": "help", "created_at": 9}],
    )

    summary = analysis["summary"]
    assert summary["total_chars"] == len(final_text)
    assert summary["typed_chars"] == 5
    assert summary["ai_inserted_chars"] == 2
    assert summary["ai_pasted_chars"] == 0
    assert summary["external_paste_chars"] == 5
    assert summary["unknown_chars"] == 1
    assert summary["source_mapped_chars"] == len(final_text)
    assert summary["suspected_unmarked_import_count"] == 1
    assert summary["process_summary"] == {
        "prompt_sent_count": 1,
        "assistant_message_received_count": 0,
        "ai_copy_button_clicked_count": 1,
        "ai_reply_selection_copied_count": 0,
        "ai_insert_clicked_count": 1,
        "paste_detected_count": 1,
        "large_burst_detected_count": 0,
        "delete_text_count": 1,
        "replace_text_count": 0,
        "version_saved_count": 1,
        "assignment_submitted_count": 1,
    }
    assert [
        (segment["source_type"], segment["segment_text"])
        for segment in analysis["highlights"]
    ] == [
        ("user_typed", "typed"),
        ("ai_inserted", "AI"),
        ("external_paste", "paste"),
        ("unknown", "?"),
    ]


class UserContext:
    current_user = None


def _seed_user(session, user_id: str, name: str, email: str, education_role: str):
    # NOTE: Users.insert_new_user / get_user_by_id / update_user_by_id are async
    # (they take an AsyncSession bound to the app's global async engine) since the
    # v0.10.2 merge. This fixture's `session` is a plain sync Session bound to a
    # throwaway per-test sqlite file, so we seed the User row directly via the ORM
    # instead of going through the (now async, and differently-sessioned) Users
    # table API. See education_client() below for how async model calls (Folders/
    # Chats/Notes/Users) made *by the router* are redirected to this same sqlite
    # file for the duration of the test.
    now = int(time.time())
    user_row = User(
        id=user_id,
        email=email,
        name=name,
        role="user",
        profile_image_url="/user.png",
        info={"education_role": education_role},
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(user_row)
    session.commit()
    session.refresh(user_row)
    return UserModel.model_validate(user_row)


def _prepare_assignment_flow(client, teacher, student):
    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing Missing Due"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "description": "Write a short argument essay.",
            "classroom_id": classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    workspace = workspace_res.json()
    session_id = workspace["writing_session"]["id"]

    version_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/versions",
        json={
            "trigger_type": "autosave",
            "content_json": None,
            "content_text": "AI outline draft. My final draft.",
        },
    )
    assert version_res.status_code == 200, version_res.text
    version_id = version_res.json()["id"]

    provenance_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/provenance",
        json={
            "version_id": version_id,
            "segments": [
                {
                    "segment_id": "seed-ai-insert",
                    "source_type": "ai_inserted",
                    "segment_text": "AI outline draft.",
                    "source_message_id": "msg-seed",
                    "start_offset": 0,
                    "end_offset": 17,
                }
            ],
        },
    )
    assert provenance_res.status_code == 200, provenance_res.text

    operations_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/operations",
        json={
            "operations": [
                {
                    "op_type": "platform_ai_insert",
                    "source_type": "ai_inserted",
                    "start_offset": 0,
                    "end_offset": 17,
                    "inserted_text": "AI outline draft.",
                    "deleted_text": "",
                    "batch_id": "batch-ai-seed",
                },
                {
                    "op_type": "keyboard_input",
                    "source_type": "user_typed",
                    "start_offset": 18,
                    "end_offset": 150,
                    "inserted_text": "This looks like a very large typed burst that should be treated as suspicious imported text for teacher review.",
                    "deleted_text": "",
                    "batch_id": "batch-suspected-seed",
                },
            ]
        },
    )
    assert operations_res.status_code == 200, operations_res.text

    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": None,
            "final_content_html": "<p>AI outline draft. My final draft. This looks like a very large typed burst that should be treated as suspicious imported text for teacher review.</p>",
            "final_content_text": "AI outline draft. My final draft. This looks like a very large typed burst that should be treated as suspicious imported text for teacher review.",
            "ai_help_types": ["Outline"],
            "reflection_text": "I used AI to create a first outline and then rewrote the ideas myself.",
        },
    )
    assert submit_res.status_code == 200, submit_res.text

    return {
        "classroom": classroom,
        "assignment": assignment,
        "workspace": workspace,
        "submission": submit_res.json(),
    }


@pytest.fixture
def education_client():
    internal_db.DATABASE_ENABLE_SESSION_SHARING = True

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "education_smoke.db"
        sync_url = f"sqlite:///{db_path}"
        engine = create_engine(
            sync_url,
            connect_args={"check_same_thread": False},
        )
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False,
        )

        for table in [
            User.__table__,
            Config.__table__,
            AccessGrant.__table__,
            Note.__table__,
            PinnedNote.__table__,
            Group.__table__,
            GroupMember.__table__,
            Folder.__table__,
            Chat.__table__,
            ChatMessage.__table__,
            AutomationRun.__table__,
            SharedChat.__table__,
            Classroom.__table__,
            ClassroomMember.__table__,
            Assignment.__table__,
            WritingSession.__table__,
            WritingVersion.__table__,
            ProvenanceSegment.__table__,
            MicroReflection.__table__,
            Submission.__table__,
            SubmissionReview.__table__,
            EducationNotification.__table__,
        ]:
            table.create(bind=engine, checkfirst=True)

        with engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX IF EXISTS classroom_member_user_idx")

        # The education router (open_webui/routers/education.py) still takes a
        # sync `db: Session = Depends(get_session)`, but forwards it as `db=db`
        # into Users/Folders/Chats/Notes table methods that became async (and
        # AsyncSession-typed) in the v0.10.2 merge. Passing a sync Session fails
        # `isinstance(db, AsyncSession)` inside get_async_db_context(), so those
        # calls silently fall back to the app's *global* async engine/session
        # (open_webui.internal.db.AsyncSessionLocal) -- which, unless redirected,
        # points at the real dev DATABASE_URL (webui.db). To keep this test fully
        # isolated (and to make the router's Folder/Chat/Note/User records land in
        # the same sqlite file the test's own sync session and assertions use), we
        # point the process-wide AsyncSessionLocal at an async engine bound to the
        # exact same sqlite file for the lifetime of this fixture, then restore it.
        async_engine = create_async_engine(
            internal_db._make_async_url(sync_url),
            connect_args={"check_same_thread": False},
        )
        TestAsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        original_async_session_local = internal_db.AsyncSessionLocal
        internal_db.AsyncSessionLocal = TestAsyncSessionLocal

        with SessionLocal() as session:
            teacher = _seed_user(
                session, "teacher-1", "Teacher One", "teacher@example.com", "teacher"
            )
            other_teacher = _seed_user(
                session, "teacher-2", "Teacher Two", "teacher2@example.com", "teacher"
            )
            student = _seed_user(
                session, "student-1", "Student One", "student@example.com", "student"
            )
            outsider = _seed_user(
                session, "student-2", "Student Two", "student2@example.com", "student"
            )

        app = FastAPI()
        app.include_router(education_router, prefix="/api/v1")
        app.include_router(chats_router, prefix="/api/v1/chats")
        app.include_router(notes_router, prefix="/api/v1/notes")
        app.state.config = SimpleNamespace(
            USER_PERMISSIONS={"chat": {"delete": True}, "features": {"notes": True}},
            ENABLE_COMMUNITY_SHARING=True,
        )
        # chats_router's delete endpoint calls stop_item_tasks(request.app.state.redis, ...);
        # the task-tracking helpers in open_webui/tasks.py already handle a falsy `redis`
        # by falling back to no-op/in-memory behavior, so None is a safe stub here.
        app.state.redis = None

        def override_session():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_verified_user():
            if UserContext.current_user is None:
                raise HTTPException(status_code=401, detail="Missing test user")
            return UserContext.current_user

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_verified_user] = override_verified_user

        client = TestClient(app)
        try:
            yield client, teacher, other_teacher, student, outsider, SessionLocal
        finally:
            client.close()
            engine.dispose()
            asyncio.run(async_engine.dispose())
            internal_db.AsyncSessionLocal = original_async_session_local
            UserContext.current_user = None


def test_education_classroom_main_flow(education_client):
    client, teacher, _, student, outsider, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    classroom = flow["classroom"]
    assignment = flow["assignment"]
    workspace = flow["workspace"]
    submission_payload = flow["submission"]

    assert workspace["writing_session"]["owner_user_id"] == student.id
    assert workspace["assignment"]["id"] == assignment["id"]
    assert submission_payload["submission_id"]

    UserContext.current_user = teacher
    teacher_workspace_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/workspace"
    )
    assert teacher_workspace_res.status_code == 403, teacher_workspace_res.text

    submissions_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    )
    assert submissions_res.status_code == 200, submissions_res.text
    submissions = submissions_res.json()
    assert len(submissions) == 1
    assert submissions[0]["submission"]["id"] == submission_payload["submission_id"]
    assert submissions[0]["student_name"] == "Student One"
    assert submissions[0]["review_status"] == "pending"

    dashboard_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    )
    assert dashboard_res.status_code == 200, dashboard_res.text
    dashboard = dashboard_res.json()
    assert len(dashboard["items"]) == 1
    assert dashboard["items"][0]["student_name"] == "Student One"
    assert dashboard["items"][0]["has_reflection"] is True

    detail_res = client.get(
        f"/api/v1/teacher/submissions/{submission_payload['submission_id']}"
    )
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json()
    assert detail["submission"]["id"] == submission_payload["submission_id"]
    assert detail["micro_reflection"]["ai_help_types"] == ["Outline"]
    assert detail["final_version"]["trigger_type"] == "submit"
    assert len(detail["versions"]) >= 1
    assert detail["analysis"]["summary"]["ai_inserted_chars"] >= 1
    assert detail["analysis"]["summary"]["suspected_unmarked_import_count"] >= 1
    assert len(detail["analysis"]["timeline"]) >= 2

    analysis_summary_res = client.get(
        f"/api/v1/teacher/submissions/{submission_payload['submission_id']}/analysis/summary"
    )
    assert analysis_summary_res.status_code == 200, analysis_summary_res.text
    assert analysis_summary_res.json()["burst_count"] >= 1

    analysis_segments_res = client.get(
        f"/api/v1/teacher/submissions/{submission_payload['submission_id']}/analysis/segments"
    )
    assert analysis_segments_res.status_code == 200, analysis_segments_res.text
    assert len(analysis_segments_res.json()) >= 2
    segment_id = analysis_segments_res.json()[0]["segment_id"]

    analysis_segment_detail_res = client.get(
        f"/api/v1/teacher/submissions/{submission_payload['submission_id']}/analysis/segments/{segment_id}"
    )
    assert (
        analysis_segment_detail_res.status_code == 200
    ), analysis_segment_detail_res.text
    assert analysis_segment_detail_res.json()["segment_id"] == segment_id

    second_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 9 Writing"}
    )
    assert second_classroom_res.status_code == 200, second_classroom_res.text
    second_classroom = second_classroom_res.json()["classroom"]

    UserContext.current_user = student
    rejoin_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": second_classroom["invite_code"]},
    )
    assert rejoin_res.status_code == 400, rejoin_res.text

    UserContext.current_user = outsider
    foreign_workspace_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/workspace"
    )
    assert foreign_workspace_res.status_code == 403, foreign_workspace_res.text


def test_submission_accepts_multiple_ai_help_types(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Multi Help"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Reflective Essay",
            "description": "Write and reflect on AI help.",
            "classroom_id": classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    session_id = workspace_res.json()["writing_session"]["id"]

    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": None,
            "final_content_html": "<p>I revised the essay after reviewing AI suggestions.</p>",
            "final_content_text": "I revised the essay after reviewing AI suggestions.",
            "ai_help_types": ["Outline", "Examples", "Strengthen Reasoning"],
            "reflection_text": "I used AI for planning and examples, then rejected weak claims and rewrote the reasoning.",
        },
    )
    assert submit_res.status_code == 200, submit_res.text
    submission_id = submit_res.json()["submission_id"]

    UserContext.current_user = teacher
    detail_res = client.get(f"/api/v1/teacher/submissions/{submission_id}")
    assert detail_res.status_code == 200, detail_res.text
    assert detail_res.json()["micro_reflection"]["ai_help_types"] == [
        "Outline",
        "Examples",
        "Strengthen Reasoning",
    ]


def test_student_resubmission_overwrites_previous_submission(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    session_id = flow["workspace"]["writing_session"]["id"]
    first_submission_id = flow["submission"]["submission_id"]

    UserContext.current_user = student
    second_submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": {"type": "doc", "content": []},
            "final_content_html": "<p>Second final draft with substantial revisions.</p>",
            "final_content_text": "Second final draft with substantial revisions.",
            "ai_help_types": ["Polish"],
            "reflection_text": "I revised the final answer again before the deadline and replaced my earlier submission.",
        },
    )
    assert second_submit_res.status_code == 200, second_submit_res.text
    second_submission = second_submit_res.json()
    assert second_submission["submission_id"] == first_submission_id
    assert (
        second_submission["final_version_id"] != flow["submission"]["final_version_id"]
    )

    UserContext.current_user = teacher
    submissions_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    )
    assert submissions_res.status_code == 200, submissions_res.text
    submissions = submissions_res.json()
    assert len(submissions) == 1
    assert submissions[0]["submission"]["id"] == first_submission_id
    assert (
        submissions[0]["submission"]["final_version_id"]
        == second_submission["final_version_id"]
    )
    assert submissions[0]["reflection"]["ai_help_types"] == ["Polish"]

    with SessionLocal() as session:
        stored_submissions = (
            session.query(Submission)
            .filter(
                Submission.assignment_id == assignment["id"],
                Submission.student_id == student.id,
            )
            .all()
        )
        assert len(stored_submissions) == 1
        stored_session = session.get(WritingSession, session_id)
        assert stored_session.submitted_submission_id == first_submission_id


def test_student_cannot_submit_after_assignment_due_time(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Past Due Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Past Due Essay",
            "description": "This assignment is closed.",
            "classroom_id": classroom["id"],
            "due_at": 1,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    session_id = workspace_res.json()["writing_session"]["id"]

    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": None,
            "final_content_html": "<p>Late submission.</p>",
            "final_content_text": "Late submission.",
            "ai_help_types": ["Outline"],
            "reflection_text": "I tried to submit this after the assignment due time had already passed.",
        },
    )
    assert submit_res.status_code == 400, submit_res.text
    assert submit_res.json()["detail"] == "Assignment due time has passed"


def test_education_teacher_review_access_control(education_client):
    client, teacher, other_teacher, student, outsider, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    submission_id = flow["submission"]["submission_id"]

    UserContext.current_user = other_teacher
    foreign_submissions_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    )
    assert foreign_submissions_res.status_code == 403, foreign_submissions_res.text

    foreign_dashboard_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    )
    assert foreign_dashboard_res.status_code == 403, foreign_dashboard_res.text

    foreign_detail_res = client.get(f"/api/v1/teacher/submissions/{submission_id}")
    assert foreign_detail_res.status_code == 403, foreign_detail_res.text

    UserContext.current_user = outsider
    outsider_submissions_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    )
    assert outsider_submissions_res.status_code == 403, outsider_submissions_res.text


def test_assignment_requires_due_time_on_create_and_update(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    missing_due_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "description": "Write a short argument essay.",
            "classroom_id": classroom["id"],
        },
    )
    assert missing_due_res.status_code == 400, missing_due_res.text
    assert missing_due_res.json()["detail"] == "Assignment due time is required"

    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]

    UserContext.current_user = teacher
    clear_due_res = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"due_at": None},
    )
    assert clear_due_res.status_code == 400, clear_due_res.text
    assert clear_due_res.json()["detail"] == "Assignment due time is required"


def test_teacher_overview_and_assignment_listing(education_client):
    client, teacher, _, student, _, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    submission_id = flow["submission"]["submission_id"]

    UserContext.current_user = teacher

    overview_res = client.get("/api/v1/teacher/overview")
    assert overview_res.status_code == 200, overview_res.text
    overview = overview_res.json()
    assert overview["classroom_count"] == 1
    assert overview["assignment_count"] == 1
    assert overview["submission_count"] == 1
    assert overview["review_count"] == 1
    assert overview["pending_review_count"] == 1
    assert overview["unsubmitted_count"] == 0
    assert overview["recent_assignments"][0]["assignment"]["id"] == assignment["id"]
    assert overview["recent_submissions"][0]["submission"]["id"] == submission_id
    assert overview["pending_review_items"][0]["submission"]["id"] == submission_id
    assert overview["recent_submissions"][0]["analysis_summary"]["burst_count"] >= 1

    review_res = client.get("/api/v1/teacher/review")
    assert review_res.status_code == 200, review_res.text
    review_items = review_res.json()
    assert len(review_items) == 1
    assert review_items[0]["submission"]["id"] == submission_id
    assert review_items[0]["review_status"] == "pending"
    assert review_items[0]["analysis_summary"]["ai_inserted_chars"] >= 1


def test_teacher_review_lifecycle_assignment_update_and_classroom_progress(
    education_client,
):
    client, teacher, _, student, outsider, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    classroom = flow["classroom"]
    submission_id = flow["submission"]["submission_id"]

    UserContext.current_user = teacher

    review_save_res = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 92,
            "overall_comment": "Strong revision and clear structure.",
            "rubric_json": {"ideas": 30, "structure": 31, "evidence": 31},
        },
    )
    assert review_save_res.status_code == 200, review_save_res.text
    review = review_save_res.json()
    assert review["review_status"] == "reviewed"
    assert review["score"] == 92

    review_get_res = client.get(f"/api/v1/teacher/submissions/{submission_id}/review")
    assert review_get_res.status_code == 200, review_get_res.text
    assert review_get_res.json()["review_status"] == "reviewed"

    review_queue_res = client.get(
        "/api/v1/teacher/review", params={"review_status": "reviewed"}
    )
    assert review_queue_res.status_code == 200, review_queue_res.text
    assert len(review_queue_res.json()) == 1
    assert review_queue_res.json()[0]["review_status"] == "reviewed"

    assignment_update_res = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={
            "title": "Argument Essay Final",
            "description": "Updated description.",
            "status": "active",
            "due_at": 2000000000,
        },
    )
    assert assignment_update_res.status_code == 200, assignment_update_res.text
    updated_assignment = assignment_update_res.json()
    assert updated_assignment["title"] == "Argument Essay Final"
    assert updated_assignment["due_at"] == 2000000000

    archive_assignment_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/archive"
    )
    assert archive_assignment_res.status_code == 200, archive_assignment_res.text
    assert archive_assignment_res.json()["status"] == "archived"
    assert archive_assignment_res.json()["archived_at"] is not None

    progress_res = client.get(f"/api/v1/teacher/classrooms/{classroom['id']}/progress")
    assert progress_res.status_code == 200, progress_res.text
    progress = progress_res.json()
    assert progress["student_count"] == 1
    assert progress["assignment_count"] == 1
    assert progress["submitted_count"] == 1
    assert progress["reviewed_count"] == 1
    assert progress["pending_review_count"] == 0
    assert progress["risk_summary"]["burst_count"] >= 1
    assert (
        progress["assignments"][0]["risk_summary"]["suspected_unmarked_import_count"]
        >= 1
    )

    export_res = client.get(f"/api/v1/teacher/classrooms/{classroom['id']}/export")
    assert export_res.status_code == 200, export_res.text
    assert "text/csv" in export_res.headers["content-type"]
    assert "Argument Essay Final" in export_res.text
    assert "reviewed" in export_res.text

    outsider_import_res = client.post(
        f"/api/v1/teacher/classrooms/{classroom['id']}/bulk-import",
        json={"user_ids": [outsider.id]},
    )
    assert outsider_import_res.status_code == 200, outsider_import_res.text
    assert outsider_import_res.json()["added_count"] == 1

    failed_import_res = client.post(
        f"/api/v1/teacher/classrooms/{classroom['id']}/bulk-import",
        json={"user_ids": ["missing-student"]},
    )
    assert failed_import_res.status_code == 200, failed_import_res.text
    assert failed_import_res.json()["failed_count"] == 1

    assignments_res = client.get("/api/v1/teacher/assignments")
    assert assignments_res.status_code == 200, assignments_res.text
    assignments = assignments_res.json()
    assert len(assignments) == 1
    assert assignments[0]["assignment"]["id"] == assignment["id"]
    assert assignments[0]["classroom"]["id"] == flow["classroom"]["id"]
    assert assignments[0]["student_count"] == 2
    assert assignments[0]["submission_count"] == 1
    assert assignments[0]["latest_submission_at"] is not None
    assert assignments[0]["risk_summary"]["burst_count"] >= 1
    assert assignments[0]["risk_summary"]["suspected_unmarked_import_count"] >= 1


def test_student_assignment_and_dashboard_views(education_client):
    client, teacher, _, student, _, _session_local = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    classroom = flow["classroom"]
    submission_id = flow["submission"]["submission_id"]

    UserContext.current_user = teacher
    teacher_classroom_res = client.get("/api/v1/me/classroom")
    assert teacher_classroom_res.status_code == 200, teacher_classroom_res.text
    assert teacher_classroom_res.json()["classroom"]["id"] == classroom["id"]

    UserContext.current_user = student
    student_classroom_res = client.get("/api/v1/me/classroom")
    assert student_classroom_res.status_code == 200, student_classroom_res.text
    assert student_classroom_res.json()["classroom"]["id"] == classroom["id"]

    UserContext.current_user = teacher
    classrooms_res = client.get("/api/v1/teacher/classrooms")
    assert classrooms_res.status_code == 200, classrooms_res.text
    classrooms = classrooms_res.json()
    assert classrooms[0]["risk_summary"]["burst_count"] >= 1

    dashboard_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    )
    assert dashboard_res.status_code == 200, dashboard_res.text
    assert (
        dashboard_res.json()["items"][0]["risk_summary"][
            "suspected_unmarked_import_count"
        ]
        >= 1
    )
    assert dashboard_res.json()["summary"]["burst_count"] >= 1
    assert "rewrite_levels" in dashboard_res.json()["distributions"]

    UserContext.current_user = student
    assignments_res = client.get("/api/v1/me/writing/assignments")
    assert assignments_res.status_code == 200, assignments_res.text
    assignments = assignments_res.json()
    assert len(assignments) == 1
    assert assignments[0]["assignment"]["id"] == assignment["id"]
    assert assignments[0]["membership"]["classroom_id"] == classroom["id"]
    assert assignments[0]["has_submission"] is True
    assert assignments[0]["submission_id"] == submission_id
    assert (
        assignments[0]["writing_session_id"]
        == flow["workspace"]["writing_session"]["id"]
    )

    dashboard_res = client.get("/api/v1/me/writing/dashboard")
    assert dashboard_res.status_code == 200, dashboard_res.text
    dashboard = dashboard_res.json()
    assert len(dashboard["items"]) == 1
    assert dashboard["items"][0]["submission_id"] == submission_id
    assert dashboard["items"][0]["student_id"] == student.id
    assert dashboard["items"][0]["student_name"] == "Student One"
    assert dashboard["items"][0]["has_reflection"] is True

    blank_invite_res = client.post(
        "/api/v1/classrooms/join", json={"invite_code": "   "}
    )
    assert blank_invite_res.status_code == 400, blank_invite_res.text


def test_teacher_classroom_listing_and_member_management(education_client):
    client, teacher, other_teacher, student, outsider, _ = education_client

    UserContext.current_user = teacher
    empty_classroom_res = client.post("/api/v1/classrooms", json={"name": "   "})
    assert empty_classroom_res.status_code == 400, empty_classroom_res.text

    first_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert first_classroom_res.status_code == 200, first_classroom_res.text
    first_classroom = first_classroom_res.json()["classroom"]

    second_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 9 Writing"}
    )
    assert second_classroom_res.status_code == 200, second_classroom_res.text
    second_classroom = second_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Narrative Essay",
            "description": "Write a short narrative essay.",
            "classroom_id": first_classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text

    add_member_res = client.post(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members",
        json={"user_id": student.id},
    )
    assert add_member_res.status_code == 200, add_member_res.text
    assert add_member_res.json()["member"]["user_id"] == student.id

    teacher_classrooms_res = client.get("/api/v1/teacher/classrooms")
    assert teacher_classrooms_res.status_code == 200, teacher_classrooms_res.text
    teacher_classrooms = teacher_classrooms_res.json()
    assert len(teacher_classrooms) == 2

    first_item = next(
        item
        for item in teacher_classrooms
        if item["classroom"]["id"] == first_classroom["id"]
    )
    second_item = next(
        item
        for item in teacher_classrooms
        if item["classroom"]["id"] == second_classroom["id"]
    )
    assert first_item["student_count"] == 1
    assert first_item["assignment_count"] == 1
    assert second_item["student_count"] == 0
    assert second_item["assignment_count"] == 0

    members_res = client.get(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members"
    )
    assert members_res.status_code == 200, members_res.text
    members = members_res.json()
    assert len(members) == 1
    assert members[0]["member"]["user_id"] == student.id

    classroom_assignments_res = client.get(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/assignments"
    )
    assert classroom_assignments_res.status_code == 200, classroom_assignments_res.text
    classroom_assignments = classroom_assignments_res.json()
    assert len(classroom_assignments) == 1
    assert (
        classroom_assignments[0]["assignment"]["id"]
        == create_assignment_res.json()["id"]
    )
    assert classroom_assignments[0]["student_count"] == 1
    assert classroom_assignments[0]["submission_count"] == 0

    add_teacher_res = client.post(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members",
        json={"user_id": other_teacher.id},
    )
    assert add_teacher_res.status_code == 400, add_teacher_res.text

    repeat_classroom_link_res = client.post(
        f"/api/v1/teacher/classrooms/{second_classroom['id']}/members",
        json={"user_id": student.id},
    )
    assert repeat_classroom_link_res.status_code == 400, repeat_classroom_link_res.text

    remove_teacher_res = client.delete(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members/{teacher.id}"
    )
    assert remove_teacher_res.status_code == 400, remove_teacher_res.text

    UserContext.current_user = other_teacher
    foreign_members_res = client.get(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members"
    )
    assert foreign_members_res.status_code == 403, foreign_members_res.text

    UserContext.current_user = teacher
    remove_member_res = client.delete(
        f"/api/v1/teacher/classrooms/{first_classroom['id']}/members/{student.id}"
    )
    assert remove_member_res.status_code == 200, remove_member_res.text
    assert remove_member_res.json()["ok"] is True

    UserContext.current_user = student
    foreign_workspace_res = client.get(
        f"/api/v1/assignments/{create_assignment_res.json()['id']}/workspace"
    )
    assert foreign_workspace_res.status_code == 403, foreign_workspace_res.text

    student_assignments_res = client.get("/api/v1/me/writing/assignments")
    assert student_assignments_res.status_code == 200, student_assignments_res.text
    assert student_assignments_res.json() == []


def test_workspace_editing_and_submission_validation(education_client):
    client, teacher, _, student, outsider, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)
    assignment = flow["assignment"]
    workspace = flow["workspace"]
    session_id = workspace["writing_session"]["id"]

    UserContext.current_user = student
    autosave_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/autosave",
        json={
            "content_json": {"type": "doc", "content": []},
            "content_html": "<p>Draft update</p>",
            "content_text": "Draft update",
            "save_reason": "manual",
        },
    )
    assert autosave_res.status_code == 200, autosave_res.text

    version_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/versions",
        json={
            "trigger_type": "manual",
            "content_json": {"type": "doc", "content": []},
            "content_text": "Draft update",
        },
    )
    assert version_res.status_code == 200, version_res.text
    version = version_res.json()

    provenance_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/provenance",
        json={
            "version_id": version["id"],
            "segments": [
                {
                    "segment_id": "seg-1",
                    "source_type": "user_typed",
                    "segment_text": "Draft update",
                }
            ],
        },
    )
    assert provenance_res.status_code == 200, provenance_res.text
    assert provenance_res.json()[0]["segment_id"] == "seg-1"

    chat_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/chat/messages/msg-1",
        json={
            "message": {
                "id": "msg-1",
                "role": "user",
                "content": "Help me outline this essay.",
            }
        },
    )
    assert chat_res.status_code == 200, chat_res.text

    repeat_workspace_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/workspace"
    )
    assert repeat_workspace_res.status_code == 200, repeat_workspace_res.text
    assert repeat_workspace_res.json()["writing_session"]["id"] == session_id

    short_reflection_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": None,
            "final_content_html": "<p>Too short reflection test.</p>",
            "final_content_text": "Too short reflection test.",
            "ai_help_types": ["Outline"],
            "reflection_text": "Too short",
        },
    )
    assert short_reflection_res.status_code == 400, short_reflection_res.text

    UserContext.current_user = outsider
    forbidden_autosave_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/autosave",
        json={
            "content_json": None,
            "content_html": "<p>Blocked</p>",
            "content_text": "Blocked",
        },
    )
    assert forbidden_autosave_res.status_code == 403, forbidden_autosave_res.text

    forbidden_version_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/versions",
        json={
            "trigger_type": "manual",
            "content_json": None,
            "content_text": "Blocked",
        },
    )
    assert forbidden_version_res.status_code == 403, forbidden_version_res.text

    forbidden_provenance_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/provenance",
        json={
            "segments": [
                {
                    "segment_id": "seg-2",
                    "source_type": "user_typed",
                    "segment_text": "Blocked",
                }
            ],
        },
    )
    assert forbidden_provenance_res.status_code == 403, forbidden_provenance_res.text

    forbidden_chat_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/chat/messages/msg-2",
        json={"message": {"id": "msg-2", "role": "user", "content": "Blocked"}},
    )
    assert forbidden_chat_res.status_code == 403, forbidden_chat_res.text


def test_invite_regeneration_and_assignment_errors(education_client):
    client, teacher, _, student, outsider, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]
    old_invite_code = classroom["invite_code"]

    blank_assignment_res = client.post(
        "/api/v1/assignments",
        json={"title": "   ", "description": "x", "classroom_id": classroom["id"]},
    )
    assert blank_assignment_res.status_code == 400, blank_assignment_res.text

    regenerated_res = client.post(
        f"/api/v1/classrooms/{classroom['id']}/invite-code/regenerate"
    )
    assert regenerated_res.status_code == 200, regenerated_res.text
    new_classroom = regenerated_res.json()["classroom"]
    assert new_classroom["invite_code"] != old_invite_code

    UserContext.current_user = student
    old_join_res = client.post(
        "/api/v1/classrooms/join", json={"invite_code": old_invite_code}
    )
    assert old_join_res.status_code == 404, old_join_res.text

    new_join_res = client.post(
        "/api/v1/classrooms/join", json={"invite_code": new_classroom["invite_code"]}
    )
    assert new_join_res.status_code == 200, new_join_res.text

    UserContext.current_user = outsider
    student_create_classroom_res = client.post(
        "/api/v1/classrooms",
        json={"name": "Should Fail"},
    )
    assert (
        student_create_classroom_res.status_code == 403
    ), student_create_classroom_res.text

    student_create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Should Fail",
            "description": "No teacher access",
            "classroom_id": classroom["id"],
        },
    )
    assert (
        student_create_assignment_res.status_code == 403
    ), student_create_assignment_res.text


def test_assignment_workspace_returns_assignment_project(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "description": "Write a short argument essay.",
            "classroom_id": classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    workspace = workspace_res.json()
    assert workspace["project"]["meta"]["mode"] == "assignment_writing"
    assert workspace["writing_session"]["folder_id"] == workspace["project"]["id"]
    assert workspace["active_chat_id"] is None


def test_assignment_workspace_clears_missing_active_chat(education_client):
    client, teacher, _, student, _, session_local = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "description": "Write a short argument essay.",
            "classroom_id": classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    workspace = workspace_res.json()
    session_id = workspace["writing_session"]["id"]
    project_id = workspace["project"]["id"]

    with session_local() as session:
        session.add(
            Chat(
                id="assignment-project-chat",
                user_id=student.id,
                title="Project Chat",
                chat={
                    "title": "Project Chat",
                    "models": [],
                    "history": {"messages": {}, "currentId": None},
                    "messages": [],
                },
                folder_id=project_id,
                meta={},
                created_at=1,
                updated_at=1,
            )
        )
        writing_session = session.get(WritingSession, session_id)
        writing_session.chat_id = "assignment-project-chat"
        writing_session.active_chat_id = "assignment-project-chat"
        session.commit()

    with session_local() as session:
        session.query(ChatMessage).filter_by(chat_id="assignment-project-chat").delete()
        session.query(Chat).filter_by(id="assignment-project-chat").delete()
        session.commit()

    repaired_workspace_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/workspace"
    )
    assert repaired_workspace_res.status_code == 200, repaired_workspace_res.text
    payload = repaired_workspace_res.json()
    assert payload["writing_session"]["id"] == session_id
    assert payload["project"]["id"] == project_id
    assert payload["active_chat_id"] is None


def test_student_assignment_workspaces_endpoint_returns_statuses(education_client):
    client, teacher, _, student, _, _ = education_client
    flow = _prepare_assignment_flow(client, teacher, student)

    UserContext.current_user = student
    workspaces_res = client.get("/api/v1/me/writing/workspaces")
    assert workspaces_res.status_code == 200, workspaces_res.text
    items = workspaces_res.json()
    assert len(items) == 1
    assert items[0]["assignment"]["id"] == flow["assignment"]["id"]
    assert items[0]["project_id"] == flow["workspace"]["project"]["id"]
    assert items[0]["writing_session_id"] == flow["workspace"]["writing_session"]["id"]
    assert items[0]["status"] == "submitted"
    assert items[0]["submitted_at"] is not None


def test_delete_chat_endpoint_persists_sidebar_chat_deletion(education_client):
    client, _, _, student, _, session_local = education_client
    UserContext.current_user = student

    with session_local() as session:
        session.add(
            Chat(
                id="sidebar-chat-delete",
                user_id=student.id,
                title="Sidebar Chat Delete",
                chat={
                    "title": "Sidebar Chat Delete",
                    "models": [],
                    "history": {"messages": {}, "currentId": None},
                    "messages": [],
                },
                folder_id=None,
                meta={},
                created_at=1,
                updated_at=1,
            )
        )
        session.add(
            ChatMessage(
                id="sidebar-chat-delete-message",
                chat_id="sidebar-chat-delete",
                user_id=student.id,
                content="delete me",
                role="user",
                created_at=1,
                updated_at=1,
            )
        )
        session.commit()

    delete_res = client.delete("/api/v1/chats/sidebar-chat-delete")
    assert delete_res.status_code == 200, delete_res.text
    assert delete_res.json() is True

    with session_local() as session:
        assert session.get(Chat, "sidebar-chat-delete") is None
        assert (
            session.query(ChatMessage).filter_by(chat_id="sidebar-chat-delete").count()
            == 0
        )


def test_workspace_project_creation_failure_returns_409(education_client, monkeypatch):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "description": "Write a short argument essay.",
            "classroom_id": classroom["id"],
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    async def _broken_insert_new_folder(*args, **kwargs):
        return None

    monkeypatch.setattr(
        education_router_module.Folders,
        "insert_new_folder",
        _broken_insert_new_folder,
    )

    broken_workspace_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/workspace"
    )
    assert broken_workspace_res.status_code == 409, broken_workspace_res.text
    detail = broken_workspace_res.json()["detail"]
    assert detail["code"] == "ASSIGNMENT_WORKSPACE_CORRUPTED"
    assert detail["missing_project"] is True


def test_writing_home_and_personal_workspace_flow(education_client):
    client, teacher, _, student, _, _ = education_client
    _prepare_assignment_flow(client, teacher, student)

    UserContext.current_user = teacher
    create_personal_res = client.post(
        "/api/v1/me/writing/personal", json={"title": "Teacher Draft"}
    )
    assert create_personal_res.status_code == 200, create_personal_res.text
    personal_workspace = create_personal_res.json()
    assert personal_workspace["scope"] == "personal"
    assert personal_workspace["writing_session"]["owner_user_id"] == teacher.id

    teacher_home_res = client.get("/api/v1/me/writing/home")
    assert teacher_home_res.status_code == 200, teacher_home_res.text
    teacher_home = teacher_home_res.json()
    assert teacher_home["role"] == "teacher"
    assert len(teacher_home["personal_items"]) == 1
    assert teacher_home["personal_items"][0]["project_mode"] == "personal_writing"
    assert teacher_home["assignment_items"] == []

    UserContext.current_user = student
    student_home_res = client.get("/api/v1/me/writing/home")
    assert student_home_res.status_code == 200, student_home_res.text
    student_home = student_home_res.json()
    assert student_home["role"] == "student"
    assert len(student_home["assignment_items"]) == 1
    assert student_home["assignment_items"][0]["project_mode"] == "assignment_writing"
    assert any(
        item["project_mode"] == "assignment_writing"
        for item in student_home["recent_items"]
    )

    personal_workspace_res = client.get(
        f"/api/v1/writing/{personal_workspace['writing_session']['id']}/workspace"
    )
    assert personal_workspace_res.status_code == 403, personal_workspace_res.text


def test_writing_notes_are_hidden_from_notes_module(education_client):
    client, teacher, _, _, _, _ = education_client

    UserContext.current_user = teacher
    create_personal_res = client.post(
        "/api/v1/me/writing/personal", json={"title": "Hidden In Notes"}
    )
    assert create_personal_res.status_code == 200, create_personal_res.text
    workspace = create_personal_res.json()
    note_id = workspace["note"]["id"]

    notes_res = client.get("/api/v1/notes/")
    assert notes_res.status_code == 200, notes_res.text
    assert all(note["id"] != note_id for note in notes_res.json())

    note_detail_res = client.get(f"/api/v1/notes/{note_id}")
    assert note_detail_res.status_code == 404, note_detail_res.text


def test_personal_writing_reopens_sidebar_and_can_be_deleted(education_client):
    client, teacher, _, _, _, session_local = education_client

    UserContext.current_user = teacher
    create_personal_res = client.post(
        "/api/v1/me/writing/personal", json={"title": "Hidden Draft"}
    )
    assert create_personal_res.status_code == 200, create_personal_res.text
    workspace = create_personal_res.json()
    session_id = workspace["writing_session"]["id"]
    project_id = workspace["project"]["id"]

    client.post(
        f"/api/v1/folders/{project_id}/update",
        json={
            "name": workspace["project"]["name"],
            "meta": {
                **(workspace["project"].get("meta") or {}),
                "hidden_from_sidebar": True,
            },
            "data": workspace["project"].get("data") or {},
        },
    )

    reopened_res = client.get(f"/api/v1/writing/{session_id}/workspace")
    assert reopened_res.status_code == 200, reopened_res.text
    reopened = reopened_res.json()
    assert reopened["project"]["meta"]["mode"] == "personal_writing"
    assert reopened["project"]["meta"]["hidden_from_sidebar"] is False

    # Folders.insert_new_folder is async (post v0.10.2); with AsyncSessionLocal
    # redirected to this fixture's sqlite file (see education_client()), db=None
    # here correctly lands in the same isolated database.
    orphan_project = asyncio.run(
        Folders.insert_new_folder(
            teacher.id,
            FolderForm(
                name="Ghost Hidden Draft",
                meta={
                    "mode": "personal_writing",
                    "writing_session_id": session_id,
                    "hidden_from_sidebar": False,
                },
                data={},
            ),
        )
    )
    assert orphan_project is not None

    delete_res = client.delete(f"/api/v1/me/writing/personal/{session_id}")
    assert delete_res.status_code == 200, delete_res.text
    deleted_payload = delete_res.json()
    assert project_id in deleted_payload["deleted_folder_ids"]

    with session_local() as session:
        assert session.get(WritingSession, session_id) is None
        assert session.get(Folder, project_id) is None
        assert session.get(Folder, orphan_project.id) is None
        assert all(
            (folder.meta or {}).get("writing_session_id") != session_id
            for folder in session.query(Folder).filter_by(user_id=teacher.id).all()
        )


def test_personal_writing_folder_rename_allows_duplicate_titles(education_client):
    client, teacher, _, _, _, session_local = education_client

    UserContext.current_user = teacher
    first_res = client.post("/api/v1/me/writing/personal", json={"title": "茶叶001"})
    assert first_res.status_code == 200, first_res.text
    first_workspace = first_res.json()

    second_res = client.post(
        "/api/v1/me/writing/personal", json={"title": "未命名写作"}
    )
    assert second_res.status_code == 200, second_res.text
    second_workspace = second_res.json()

    # Folders.get_folder_by_id_and_user_id / update_folder_by_id_and_user_id are
    # async (post v0.10.2); AsyncSessionLocal is redirected to this fixture's
    # sqlite file (see education_client()), so db=None lands in the same
    # isolated database as `session_local`.
    second_folder = asyncio.run(
        Folders.get_folder_by_id_and_user_id(
            second_workspace["project"]["id"], teacher.id
        )
    )
    assert second_folder is not None

    renamed = asyncio.run(
        Folders.update_folder_by_id_and_user_id(
            second_workspace["project"]["id"],
            teacher.id,
            FolderUpdateForm(
                name="茶叶001",
                meta=second_workspace["project"].get("meta") or {},
                data=second_workspace["project"].get("data") or {},
            ),
        )
    )

    assert renamed is not None
    assert renamed.name == "茶叶001"
    assert renamed.meta["mode"] == "personal_writing"
    assert first_workspace["project"]["id"] != second_workspace["project"]["id"]


def _submit_body(session_id: str, text: str):
    return {
        "writing_session_id": session_id,
        "final_content_json": None,
        "final_content_html": f"<p>{text}</p>",
        "final_content_text": text,
        "ai_help_types": ["Outline"],
        "reflection_text": "I used AI for outlining then rewrote every paragraph in my own words.",
    }


def _setup_submitted_assignment(client, teacher, student, title="Round Essay"):
    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": f"CR {title}"}).json()[
        "classroom"
    ]
    UserContext.current_user = student
    client.post("/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]})

    UserContext.current_user = teacher
    assignment = client.post(
        "/api/v1/assignments",
        json={"title": title, "classroom_id": classroom["id"], "due_at": 2000000000},
    ).json()

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    session_id = workspace["writing_session"]["id"]
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "first draft text for the round essay"),
    )
    assert submit_res.status_code == 200, submit_res.text
    return assignment, session_id, submit_res.json()["submission_id"]


def test_student_workspace_exposes_review_after_grading(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Student View"
    )

    # 批改前:pending,不泄露评分字段
    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "pending"
    assert "score" not in workspace["review"]
    assert workspace["effective_due_at"] == 2000000000

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 88,
            "overall_comment": "Strong structure",
            "rubric_json": {"ideas": 30, "structure": 29, "evidence": 29},
        },
    )

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "reviewed"
    assert workspace["review"]["score"] == 88
    assert workspace["review"]["overall_comment"] == "Strong structure"
    assert workspace["review"]["rubric"]["ideas"] == 30

    home = client.get("/api/v1/me/writing/home").json()
    item = next(
        i for i in home["assignment_items"] if i["assignment"]["id"] == assignment["id"]
    )
    assert item["review_status"] == "reviewed"
    assert item["score"] == 88


def test_student_workspace_exposes_returned_state(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Returned View"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Add evidence in paragraph two",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "returned"
    assert workspace["review"]["returned_comment"] == "Add evidence in paragraph two"
    assert workspace["review"]["resubmit_due_at"] == 2100000000
    assert workspace["effective_due_at"] == 2100000000
    assert workspace["writing_session"]["status"] == "draft"


def test_resubmit_before_review_overwrites_same_round(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Overwrite Round"
    )

    resubmit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "second draft replacing the first one entirely"),
    )
    assert resubmit_res.status_code == 200, resubmit_res.text
    assert resubmit_res.json()["submission_id"] == submission_id

    UserContext.current_user = teacher
    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    ).json()
    assert len(submissions) == 1
    assert submissions[0]["submission"]["round_no"] == 1


def test_returned_submission_opens_new_round_and_keeps_history(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Return Round"
    )

    UserContext.current_user = teacher
    # 退回必须带未来的 resubmit_due_at
    missing_due = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "returned", "returned_comment": "Please revise"},
    )
    assert missing_due.status_code == 400, missing_due.text

    returned = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Please revise the argument",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["resubmit_due_at"] == 2100000000

    # 退回后学生会话解锁为 draft
    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["writing_session"]["status"] == "draft"

    # 重交 → 新轮,旧轮与旧评语保留
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "revised draft after teacher returned it"),
    )
    assert resubmit.status_code == 200, resubmit.text
    new_submission_id = resubmit.json()["submission_id"]
    assert new_submission_id != submission_id

    UserContext.current_user = teacher
    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    ).json()
    assert len(submissions) == 1  # 列表只显示当前轮
    assert submissions[0]["submission"]["id"] == new_submission_id
    assert submissions[0]["submission"]["round_no"] == 2

    old_review = client.get(
        f"/api/v1/teacher/submissions/{submission_id}/review"
    ).json()
    assert old_review["review_status"] == "returned"
    assert old_review["returned_comment"] == "Please revise the argument"

    # 历史轮禁止再保存评语
    historic_save = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "reviewed", "score": 80},
    )
    assert historic_save.status_code == 400, historic_save.text


def test_effective_due_uses_resubmit_due_after_return(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Due Round"
    )

    UserContext.current_user = teacher
    past_due = int(time.time()) - 3600
    # 先把作业原截止改到过去(PATCH /assignments/{id})
    client.patch(f"/api/v1/assignments/{assignment['id']}", json={"due_at": past_due})

    UserContext.current_user = student
    blocked = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "late resubmit should be blocked now"),
    )
    assert blocked.status_code == 400, blocked.text

    UserContext.current_user = teacher
    future_due = int(time.time()) + 3600
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Late but returned for revision",
            "resubmit_due_at": future_due,
        },
    )

    UserContext.current_user = student
    allowed = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "resubmit within the new resubmit window"),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["submission_id"] != submission_id


def test_teacher_sees_rounds_and_diff(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "Rounds Diff"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Rewrite the ending",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "first draft text for the round essay with a new ending"),
    )
    second_submission_id = resubmit.json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{second_submission_id}").json()
    rounds = detail["rounds"]
    assert [r["round_no"] for r in rounds] == [2, 1]
    assert rounds[0]["is_current"] == 1
    assert rounds[1]["review_status"] == "returned"

    diff = client.get(
        f"/api/v1/teacher/submissions/{second_submission_id}/diff"
    ).json()
    assert diff["has_previous"] is True
    assert diff["previous_round_no"] == 1
    ops = {block["op"] for block in diff["blocks"]}
    assert "equal" in ops
    assert ("insert" in ops) or ("replace" in ops)

    first_diff = client.get(
        f"/api/v1/teacher/submissions/{first_submission_id}/diff"
    ).json()
    assert first_diff["has_previous"] is False


def test_notifications_flow(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Notify Round"
    )

    # 学生:布置作业时收到 assignment_published
    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("assignment_published") == 1

    # 老师:学生提交后收到 submission_created
    UserContext.current_user = teacher
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("submission_created") == 1

    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "reviewed", "score": 90},
    )

    # 学生:批改完成收到 review_completed
    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("review_completed") == 1

    # 按作业上下文标已读
    marked = client.post(
        "/api/v1/me/notifications/mark-read",
        json={"assignment_id": assignment["id"]},
    ).json()
    assert marked["marked"] >= 2  # assignment_published + review_completed
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["total"] == 0


def test_returned_review_sends_return_notification(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Notify Return"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Needs another pass",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("submission_returned") == 1
