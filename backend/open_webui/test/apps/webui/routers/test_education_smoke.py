import asyncio
import json
import tempfile
import time
import uuid
from contextlib import contextmanager
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
    AnalysisResult,
    Assignment,
    AssignmentExtension,
    ChallengeInsight,
    ChallengeSession,
    CritiqueAttempt,
    ChallengeTurn,
    Classroom,
    ClassroomMember,
    EditorOperation,
    EditorOperationInput,
    Education,
    EducationNotification,
    MicroReflection,
    ProvenanceSegment,
    ProfileAlgorithmRelease,
    ProfileEvidenceSnapshot,
    ProfileMetricProjection,
    ProfileProjectionRun,
    Submission,
    SubmissionCreateForm,
    SubmissionReview,
    StudentGrowthGoal,
    StudentProfileHelpTypeShift,
    StudentProfileHelpTypeSummary,
    StudentProfileMetricTrend,
    StudentProfileReflectionQuality,
    StudentProfileAggregateProjection,
    SubmissionReviewEvent,
    TeacherStudentNote,
    TeacherStudentNoteRevision,
    WritingSession,
    WritingVersion,
)
from open_webui.models.config import Config
from open_webui.models.folders import Folder, FolderForm, FolderUpdateForm, Folders
from open_webui.models.groups import Group, GroupMember
from open_webui.models.notes import Note, PinnedNote
from open_webui.models.users import User, UserModel
from open_webui.services.education.identity import GROUP_ID_BY_ROLE
import open_webui.routers.education as education_router_module
import open_webui.services.education.analysis as education_analysis_module
import open_webui.services.education.challenge as education_challenge_module
import open_webui.services.education.profile as education_profile_module
import open_webui.services.education.profile_snapshots as profile_snapshots_module
import open_webui.services.education.profile_recompute as profile_recompute_module
from open_webui.routers.education import router as education_router
from open_webui.routers.chats import router as chats_router
from open_webui.routers.notes import router as notes_router
from open_webui.services.education.analysis import (
    collect_clarification_exchanges,
    build_submission_analysis,
    count_clarifications,
    filter_segments_for_final_text,
)
from open_webui.services.education.profile_recompute import (
    recompute_profile_projections,
)
from open_webui.services.education.profile import (
    PROFILE_METRIC_VERSION,
)
from open_webui.services.education.profile_evidence import (
    PROFILE_EVIDENCE_SCHEMA_VERSION,
    build_analysis_from_evidence,
    canonical_json_hash,
)
from open_webui.services.education.profile_aggregates import (
    materialize_student_profile_aggregate,
)
from open_webui.utils.auth import get_verified_user


def _reflection_payload(
    action="I rewrote the claim and replaced weak evidence with a clearer example.",
    location="The second paragraph and conclusion",
    judgement="The original reasoning was vague, so the revision better supports my own conclusion.",
    next_step="I will verify the evidence before writing the final draft.",
    other_ai_help=None,
):
    return {
        "action": action,
        "location": location,
        "judgement": judgement,
        "next_step": next_step,
        "other_ai_help": other_ai_help,
    }


def _evidence_completeness(source_tracking_complete=True):
    return {
        "version_data_complete": True,
        "editor_operations_complete": True,
        "source_tracking_complete": source_tracking_complete,
    }


def _rubric_schema(score_max=100):
    base, remainder = divmod(score_max, 3)
    maxima = [base + (1 if index < remainder else 0) for index in range(3)]
    return {
        "criteria": [
            {"key": "ideas", "label": "Ideas", "max_score": maxima[0]},
            {"key": "structure", "label": "Structure", "max_score": maxima[1]},
            {"key": "evidence", "label": "Evidence", "max_score": maxima[2]},
        ]
    }


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

    filtered = filter_segments_for_final_text(final_text, segments)

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

    filtered = filter_segments_for_final_text(final_text, segments)

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

    analysis = build_submission_analysis(
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
        "clarification_question_count": 0,
        "clarification_answered_count": 0,
        "clarification_free_text_count": 0,
        "clarification_declined_count": 0,
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
        info={},
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(user_row)

    # Teaching identity is group membership, so seed the group and the member
    # row in the same session the router will read through.
    group_id = GROUP_ID_BY_ROLE[education_role]
    if session.get(Group, group_id) is None:
        session.add(
            Group(
                id=group_id,
                user_id="",
                name=group_id,
                description="",
                created_at=now,
                updated_at=now,
            )
        )
    session.add(
        GroupMember(
            id=str(uuid.uuid4()),
            group_id=group_id,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
    )

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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
                    "occurred_at_ms": int(time.time() * 1000),
                    "client_sequence": 0,
                },
                {
                    "op_type": "keyboard_input",
                    "source_type": "user_typed",
                    "start_offset": 18,
                    "end_offset": 150,
                    "inserted_text": "This looks like a very large typed burst that should be treated as suspicious imported text for teacher review.",
                    "deleted_text": "",
                    "batch_id": "batch-suspected-seed",
                    "occurred_at_ms": int(time.time() * 1000),
                    "client_sequence": 1,
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
            "ai_used": True,
            "ai_help_types": ["Outline"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(),
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
            AssignmentExtension.__table__,
            WritingSession.__table__,
            ChallengeSession.__table__,
            ChallengeTurn.__table__,
            ChallengeInsight.__table__,
            CritiqueAttempt.__table__,
            WritingVersion.__table__,
            ProvenanceSegment.__table__,
            EditorOperation.__table__,
            MicroReflection.__table__,
            Submission.__table__,
            AnalysisResult.__table__,
            SubmissionReview.__table__,
            ProfileEvidenceSnapshot.__table__,
            SubmissionReviewEvent.__table__,
            ProfileAlgorithmRelease.__table__,
            ProfileProjectionRun.__table__,
            ProfileMetricProjection.__table__,
            StudentProfileAggregateProjection.__table__,
            StudentGrowthGoal.__table__,
            TeacherStudentNote.__table__,
            TeacherStudentNoteRevision.__table__,
            EducationNotification.__table__,
        ]:
            table.create(bind=engine, checkfirst=True)

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


def test_teaching_identity_is_permission_group_membership(education_client):
    """身份即权限组:进班接口只认组成员关系,不再有第二份身份记录。"""
    client, teacher, _, student, outsider, SessionLocal = education_client

    UserContext.current_user = teacher
    classroom_res = client.post(
        "/api/v1/classrooms",
        json={"name": "Group Identity Class", "description": ""},
    )
    assert classroom_res.status_code == 200, classroom_res.text
    classroom = classroom_res.json()["classroom"]

    def group_ids_of(user_id):
        with SessionLocal() as session:
            return {
                row[0]
                for row in session.query(GroupMember.group_id)
                .filter(GroupMember.user_id == user_id)
                .all()
            }

    assert group_ids_of(teacher.id) == {GROUP_ID_BY_ROLE["teacher"]}
    assert group_ids_of(student.id) == {GROUP_ID_BY_ROLE["student"]}

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    # 教师不在学生组里,同一个邀请码对他就是 403 —— 判定只看组
    UserContext.current_user = teacher
    teacher_join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert teacher_join_res.status_code == 403, teacher_join_res.text

    # 身份从组里被摘掉后,进班资格随之消失,不存在第二处身份来源兜底
    with SessionLocal() as session:
        session.query(GroupMember).filter(
            GroupMember.user_id == outsider.id
        ).delete(synchronize_session=False)
        session.commit()

    UserContext.current_user = outsider
    outsider_join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert outsider_join_res.status_code == 403, outsider_join_res.text


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
    assert detail["micro_reflection"]["ai_used"] is True
    assert detail["micro_reflection"]["ai_help_types"] == ["Outline"]
    assert "action" in detail["micro_reflection"]["reflection_json"]
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
    assert rejoin_res.status_code == 200, rejoin_res.text

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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
            "ai_used": True,
            "ai_help_types": ["Outline", "Examples", "Strengthen Reasoning"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(),
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
            "ai_used": True,
            "ai_help_types": ["Polish"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(),
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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 1,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
            "ai_used": True,
            "ai_help_types": ["Outline"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(),
        },
    )
    assert submit_res.status_code == 400, submit_res.text
    assert submit_res.json()["detail"] == "Assignment due time has passed"


def _open_past_due_assignment(client, teacher, students):
    """一个已经截止的作业 + 若干已加入班级的学生,返回 (assignment, classroom)。"""
    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Extension Writing"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Extension Essay",
            "description": "Closed for everyone but the extended student.",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 1,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

    for student in students:
        UserContext.current_user = student
        join_res = client.post(
            "/api/v1/classrooms/join",
            json={"invite_code": classroom["invite_code"]},
        )
        assert join_res.status_code == 200, join_res.text

    return assignment, classroom


def _submit_assignment(client, assignment_id, html="<p>Essay body.</p>"):
    workspace_res = client.get(f"/api/v1/assignments/{assignment_id}/workspace")
    assert workspace_res.status_code == 200, workspace_res.text
    session_id = workspace_res.json()["writing_session"]["id"]
    return client.post(
        f"/api/v1/assignments/{assignment_id}/submit",
        json={
            "writing_session_id": session_id,
            "final_content_json": None,
            "final_content_html": html,
            "final_content_text": "Essay body.",
            "ai_used": True,
            "ai_help_types": ["Outline"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(),
        },
    )


def test_assignment_extension_reopens_submission_for_one_student(education_client):
    client, teacher, _, student, outsider, _ = education_client
    assignment, _classroom = _open_past_due_assignment(
        client, teacher, [student, outsider]
    )
    extended_due_at = int(time.time()) + 3600

    UserContext.current_user = teacher
    grant_res = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}",
        json={"due_at": extended_due_at, "reason": "Sick leave"},
    )
    assert grant_res.status_code == 200, grant_res.text
    assert grant_res.json()["due_at"] == extended_due_at
    assert grant_res.json()["reason"] == "Sick leave"

    # 名单页要能看出谁被放开了,以及放开到什么时候。
    unsubmitted_res = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/unsubmitted"
    )
    assert unsubmitted_res.status_code == 200, unsubmitted_res.text
    by_user = {item["user_id"]: item for item in unsubmitted_res.json()}
    assert by_user[student.id]["effective_due_at"] == extended_due_at
    assert by_user[student.id]["extension"]["reason"] == "Sick leave"
    assert by_user[outsider.id]["extension"] is None
    assert by_user[outsider.id]["effective_due_at"] == 1

    UserContext.current_user = student
    assert _submit_assignment(client, assignment["id"]).status_code == 200

    # 延期只对被授予的学生生效,同班其他人仍然按原截止时间关闭。
    UserContext.current_user = outsider
    blocked_res = _submit_assignment(client, assignment["id"])
    assert blocked_res.status_code == 400, blocked_res.text
    assert blocked_res.json()["detail"] == "Assignment due time has passed"

    # 学生收到个人截止时间变更的通知。
    UserContext.current_user = student
    summary_res = client.get("/api/v1/me/notifications/summary")
    assert summary_res.status_code == 200, summary_res.text
    assert summary_res.json()["by_type"].get("assignment_extension_granted") == 1


def test_assignment_extension_revoke_restores_class_due_time(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, _classroom = _open_past_due_assignment(client, teacher, [student])

    UserContext.current_user = teacher
    grant_res = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}",
        json={"due_at": int(time.time()) + 3600},
    )
    assert grant_res.status_code == 200, grant_res.text

    revoke_res = client.delete(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}"
    )
    assert revoke_res.status_code == 200, revoke_res.text

    UserContext.current_user = student
    blocked_res = _submit_assignment(client, assignment["id"])
    assert blocked_res.status_code == 400, blocked_res.text
    assert blocked_res.json()["detail"] == "Assignment due time has passed"

    UserContext.current_user = teacher
    missing_res = client.delete(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}"
    )
    assert missing_res.status_code == 404, missing_res.text


def test_assignment_extension_rejects_bad_targets(education_client):
    client, teacher, other_teacher, student, outsider, _ = education_client
    assignment, _classroom = _open_past_due_assignment(client, teacher, [student])
    future_due_at = int(time.time()) + 3600

    UserContext.current_user = other_teacher
    foreign_res = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}",
        json={"due_at": future_due_at},
    )
    assert foreign_res.status_code == 403, foreign_res.text

    UserContext.current_user = teacher
    # outsider 没有加入这个班级
    stranger_res = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{outsider.id}",
        json={"due_at": future_due_at},
    )
    assert stranger_res.status_code == 404, stranger_res.text

    past_res = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}/extensions/{student.id}",
        json={"due_at": 1},
    )
    assert past_res.status_code == 400, past_res.text
    assert past_res.json()["detail"] == "Extension due time must be in the future"


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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
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
    assert overview["pending_review_count"] == 1
    assert overview["unsubmitted_count"] == 0
    assert overview["recent_assignments"][0]["assignment"]["id"] == assignment["id"]
    assert overview["recent_submissions"][0]["submission"]["id"] == submission_id
    assert overview["recent_submissions"][0]["review_status"] == "pending"
    assert overview["recent_submissions"][0]["risk_summary"]["burst_count"] >= 1

    review_res = client.get("/api/v1/teacher/review")
    assert review_res.status_code == 200, review_res.text
    review_payload = review_res.json()
    assert review_payload["total"] == 1
    review_items = review_payload["items"]
    assert len(review_items) == 1
    assert review_items[0]["submission"]["id"] == submission_id
    assert review_items[0]["review_status"] == "pending"
    assert review_items[0]["risk_summary"]["ai_inserted_chars"] >= 1


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
            "rubric_scores": {"ideas": 30, "structure": 31, "evidence": 31},
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
    review_queue = review_queue_res.json()
    assert review_queue["total"] == 1
    assert review_queue["items"][0]["review_status"] == "reviewed"

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


def test_student_assignment_and_profile_views(education_client):
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

    profile_res = client.get("/api/v1/me/writing/profile")
    assert profile_res.status_code == 200, profile_res.text
    profile = profile_res.json()
    assert profile["student_id"] == student.id
    assert profile["portfolio_summary"]["submitted_count"] == 1
    assert len(profile["timeline"]) == 1
    point = profile["timeline"][0]
    assert point["submission_id"] == submission_id
    assert point["assignment_id"] == assignment["id"]
    assert point["ai_help_types"] == ["Outline"]
    assert point["reflection_quality"] > 0
    assert point["process_index"] is None or 0 <= point["process_index"] <= 100
    assert point["data_completeness"] == {
        "version_data": "complete",
        "editor_operations": "complete",
        "source_tracking": "missing",
        "scoring": "pending",
    }
    # 来源证据缺失不是「AI 占比为 0」；所有依赖来源追踪的值都必须为空。
    assert point["ai_ratio"] is None
    assert point["digestion_ratio"] is None
    assert point["collaboration_index"] is None
    # 一次提交看不出趋势,画像要如实说「数据不够」而不是编一条曲线。
    assert profile["trends"] == []
    insight_codes = [insight["code"] for insight in profile["insights"]]
    assert insight_codes[0] == "not_enough_data"
    assert "reflection_thin" not in insight_codes
    assert profile["insights"][0]["action_code"] == "complete_more_submissions"
    assert profile["index_formula"]["process_index"]["revision_depth"]["target"] > 0

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
            "classroom_ids": [first_classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
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
        == create_assignment_res.json()[0]["id"]
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
    assert repeat_classroom_link_res.status_code == 200, repeat_classroom_link_res.text

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
        f"/api/v1/assignments/{create_assignment_res.json()[0]['id']}/workspace"
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
            "ai_used": True,
            "ai_help_types": ["Outline"],
            "data_completeness": _evidence_completeness(),
            "reflection": _reflection_payload(action="Too short"),
        },
    )
    assert short_reflection_res.status_code == 422, short_reflection_res.text

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
        json={
            "title": "   ",
            "description": "x",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
        },
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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    )
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

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
        "ai_used": True,
        "ai_help_types": ["Outline"],
        "data_completeness": _evidence_completeness(),
        "reflection": _reflection_payload(),
    }


def _setup_submitted_assignment(
    client, teacher, student, title="Round Essay", score_max=100
):
    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": f"CR {title}"}).json()[
        "classroom"
    ]
    UserContext.current_user = student
    client.post(
        "/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]}
    )

    UserContext.current_user = teacher
    assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": title,
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": score_max,
            "rubric_schema": _rubric_schema(score_max),
        },
    ).json()[0]

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
            "rubric_scores": {"ideas": 30, "structure": 29, "evidence": 29},
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
    client, teacher, _, student, _, session_local = education_client
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

    with session_local() as session:
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .order_by(ProfileEvidenceSnapshot.evidence_revision.asc())
            .all()
        )
        assert [item.evidence_revision for item in evidence] == [1, 2]
        assert evidence[0].evidence_hash != evidence[1].evidence_hash

    profile = client.get(
        f"/api/v1/teacher/classrooms/{assignment['classroom_id']}/students/{student.id}/profile"
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["timeline_pagination"]["total"] == 1


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

    # 历史轮从自己冻结的 evidence 显式重算，不读取后续轮次会话数据。
    historic_recompute = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/analysis"
    )
    assert historic_recompute.status_code == 200, historic_recompute.text

    current_recompute = client.post(
        f"/api/v1/teacher/submissions/{new_submission_id}/analysis"
    )
    assert current_recompute.status_code == 200, current_recompute.text
    assert (
        historic_recompute.json()["summary"]["total_chars"]
        < current_recompute.json()["summary"]["total_chars"]
    )


def test_reviewed_submission_cannot_be_resubmitted(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Graded Final"
    )

    UserContext.current_user = teacher
    graded = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 85,
            "rubric_scores": {"ideas": 29, "structure": 28, "evidence": 28},
        },
    )
    assert graded.status_code == 200, graded.text

    # 已批改即定稿:截止时间还没到也不能再交,否则该学生会被打回「待批改」、
    # 旧分数进历史轮后不再计入平均分
    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "sneaking in a revision after being graded"),
    )
    assert resubmit.status_code == 409, resubmit.text
    assert resubmit.json()["detail"] == "Submission has already been reviewed"

    # 分数与轮次都没被动过
    UserContext.current_user = teacher
    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    ).json()
    assert len(submissions) == 1
    assert submissions[0]["submission"]["id"] == submission_id
    assert submissions[0]["submission"]["round_no"] == 1
    assert submissions[0]["review_status"] == "reviewed"
    assert submissions[0]["score"] == 85

    # 老师退回后重新解锁,这时才开新轮
    returned = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Please expand the second paragraph",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text

    UserContext.current_user = student
    after_return = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "revised draft after the teacher returned it"),
    )
    assert after_return.status_code == 200, after_return.text
    assert after_return.json()["submission_id"] != submission_id


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
        json=_submit_body(
            session_id, "first draft text for the round essay with a new ending"
        ),
    )
    second_submission_id = resubmit.json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{second_submission_id}").json()
    rounds = detail["rounds"]
    assert [r["round_no"] for r in rounds] == [2, 1]
    assert rounds[0]["is_current"] == 1
    assert rounds[1]["review_status"] == "returned"

    diff = client.get(f"/api/v1/teacher/submissions/{second_submission_id}/diff").json()
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
        json={
            "review_status": "reviewed",
            "score": 90,
            "rubric_scores": {"ideas": 30, "structure": 30, "evidence": 30},
        },
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


def test_my_assignment_submissions_returns_rounds_with_content_and_review(
    education_client,
):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "My Submissions Rounds"
    )

    UserContext.current_user = teacher
    returned = client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Please add more evidence",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text

    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "second draft with more evidence added"),
    )
    assert resubmit.status_code == 200, resubmit.text
    second_submission_id = resubmit.json()["submission_id"]
    assert second_submission_id != first_submission_id

    my_submissions_res = client.get(
        f"/api/v1/assignments/{assignment['id']}/me/submissions"
    )
    assert my_submissions_res.status_code == 200, my_submissions_res.text
    payload = my_submissions_res.json()
    assert payload["assignment_id"] == assignment["id"]

    rounds = payload["rounds"]
    assert [r["round_no"] for r in rounds] == [1, 2]

    first_round, second_round = rounds
    assert first_round["submission_id"] == first_submission_id
    assert first_round["is_current"] == 0
    assert first_round["review"]["review_status"] == "returned"
    assert first_round["review"]["returned_comment"] == "Please add more evidence"
    assert first_round["review"]["resubmit_due_at"] == 2100000000
    assert (
        first_round["content"]["content_text"] == "first draft text for the round essay"
    )

    assert second_round["submission_id"] == second_submission_id
    assert second_round["is_current"] == 1
    assert second_round["review"] is None
    assert (
        second_round["content"]["content_text"]
        == "second draft with more evidence added"
    )


def test_my_assignment_submissions_access_control(education_client):
    client, teacher, _, student, outsider, _ = education_client
    assignment, _session_id, _submission_id = _setup_submitted_assignment(
        client, teacher, student, "My Submissions Access"
    )

    # 老师(非学生角色)不能访问该端点,即便是本作业的老师
    UserContext.current_user = teacher
    teacher_res = client.get(f"/api/v1/assignments/{assignment['id']}/me/submissions")
    assert teacher_res.status_code == 403, teacher_res.text

    # 未加入班级的学生完全无访问权限
    UserContext.current_user = outsider
    outsider_res = client.get(f"/api/v1/assignments/{assignment['id']}/me/submissions")
    assert outsider_res.status_code == 403, outsider_res.text

    # 加入同一班级但未提交过的学生只应看到自己的空历史,不会拿到别的学生的数据
    UserContext.current_user = teacher
    assignments = client.get("/api/v1/teacher/assignments").json()
    classroom_id = next(
        item["classroom"]["id"]
        for item in assignments
        if item["assignment"]["id"] == assignment["id"]
    )
    add_member_res = client.post(
        f"/api/v1/teacher/classrooms/{classroom_id}/members",
        json={"user_id": outsider.id},
    )
    assert add_member_res.status_code == 200, add_member_res.text

    UserContext.current_user = outsider
    member_res = client.get(f"/api/v1/assignments/{assignment['id']}/me/submissions")
    assert member_res.status_code == 200, member_res.text
    assert member_res.json()["rounds"] == []


def test_my_assignment_submissions_missing_assignment_returns_404(education_client):
    client, _, _, student, _, _ = education_client

    UserContext.current_user = student
    res = client.get("/api/v1/assignments/does-not-exist/me/submissions")
    assert res.status_code == 404, res.text


def test_submit_requires_current_classroom_membership(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, _ = _setup_submitted_assignment(
        client, teacher, student, "Membership Guard"
    )

    # 退班后,学生手里的旧写作会话不应再能提交到原班级的作业
    UserContext.current_user = teacher
    classroom_id = client.get(f"/api/v1/teacher/assignments/{assignment['id']}").json()[
        "classroom"
    ]["id"]
    remove_res = client.delete(
        f"/api/v1/teacher/classrooms/{classroom_id}/members/{student.id}"
    )
    assert remove_res.status_code == 200, remove_res.text

    UserContext.current_user = student
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "draft submitted after leaving the classroom"),
    )
    assert submit_res.status_code == 403, submit_res.text


def test_submit_rejected_for_archived_assignment(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, _ = _setup_submitted_assignment(
        client, teacher, student, "Archived Guard"
    )

    UserContext.current_user = teacher
    archive_res = client.post(f"/api/v1/assignments/{assignment['id']}/archive")
    assert archive_res.status_code == 200, archive_res.text

    UserContext.current_user = student
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "draft submitted after the assignment archived"),
    )
    assert submit_res.status_code == 400, submit_res.text
    assert submit_res.json()["detail"] == "Assignment is not open for submission"


def test_update_assignment_rejects_null_and_unknown_status(education_client):
    client, teacher, _, _, _, _ = education_client

    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": "Patch Guard"}).json()[
        "classroom"
    ]
    assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": "Patch Essay",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    ).json()[0]

    for payload in ({"title": None}, {"classroom_id": None}, {"status": "deleted"}):
        res = client.patch(f"/api/v1/assignments/{assignment['id']}", json=payload)
        assert res.status_code == 400, f"{payload} -> {res.status_code} {res.text}"

    # description 允许清空
    res = client.patch(
        f"/api/v1/assignments/{assignment['id']}", json={"description": None}
    )
    assert res.status_code == 200, res.text
    assert res.json()["description"] is None


def test_unsubmitted_listing_and_reminder_targets_only_unsubmitted(education_client):
    client, teacher, _, student, outsider, _ = education_client

    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": "Remind CR"}).json()[
        "classroom"
    ]
    assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": "Remind Essay",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    ).json()[0]

    for member in (student, outsider):
        UserContext.current_user = member
        join = client.post(
            "/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]}
        )
        assert join.status_code == 200, join.text

    # student 提交,outsider 未提交
    UserContext.current_user = student
    session_id = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()[
        "writing_session"
    ]["id"]
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "submitted draft for the reminder test"),
    )
    assert submit_res.status_code == 200, submit_res.text

    UserContext.current_user = teacher
    unsubmitted = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/unsubmitted"
    )
    assert unsubmitted.status_code == 200, unsubmitted.text
    assert [item["user_id"] for item in unsubmitted.json()] == [outsider.id]

    # 指定名单要和未提交名单取交集,已提交的学生不该收到催交
    remind = client.post(
        f"/api/v1/teacher/assignments/{assignment['id']}/remind",
        json={"user_ids": [student.id, outsider.id]},
    )
    assert remind.status_code == 200, remind.text
    assert remind.json()["user_ids"] == [outsider.id]
    assert remind.json()["reminded_count"] == 1

    UserContext.current_user = student
    student_summary = client.get("/api/v1/me/notifications/summary").json()
    assert student_summary["by_type"].get("assignment_reminder") is None
    UserContext.current_user = outsider
    outsider_summary = client.get("/api/v1/me/notifications/summary").json()
    assert outsider_summary["by_type"].get("assignment_reminder") == 1


def test_transfer_classroom_members_between_classrooms(education_client):
    client, teacher, other_teacher, student, outsider, _ = education_client

    UserContext.current_user = teacher
    source = client.post("/api/v1/classrooms", json={"name": "Transfer From"}).json()[
        "classroom"
    ]
    target = client.post("/api/v1/classrooms", json={"name": "Transfer To"}).json()[
        "classroom"
    ]

    UserContext.current_user = student
    client.post("/api/v1/classrooms/join", json={"invite_code": source["invite_code"]})

    UserContext.current_user = other_teacher
    foreign = client.post("/api/v1/classrooms", json={"name": "Foreign CR"}).json()[
        "classroom"
    ]

    UserContext.current_user = teacher
    # 目标班不属于自己
    forbidden = client.post(
        f"/api/v1/teacher/classrooms/{source['id']}/members/transfer",
        json={"user_ids": [student.id], "target_classroom_id": foreign["id"]},
    )
    assert forbidden.status_code == 403, forbidden.text

    # 目标班不能是自己
    same = client.post(
        f"/api/v1/teacher/classrooms/{source['id']}/members/transfer",
        json={"user_ids": [student.id], "target_classroom_id": source["id"]},
    )
    assert same.status_code == 400, same.text

    # 非本班成员跳过,不计入 affected_count
    res = client.post(
        f"/api/v1/teacher/classrooms/{source['id']}/members/transfer",
        json={
            "user_ids": [student.id, outsider.id],
            "target_classroom_id": target["id"],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["affected_count"] == 1
    assert res.json()["skipped_users"] == [outsider.id]

    source_members = client.get(
        f"/api/v1/teacher/classrooms/{source['id']}/members"
    ).json()
    target_members = client.get(
        f"/api/v1/teacher/classrooms/{target['id']}/members"
    ).json()
    assert [item["member"]["user_id"] for item in source_members] == []
    assert [item["member"]["user_id"] for item in target_members] == [student.id]


def test_delete_assignment_guards_and_notification_cleanup(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": "Delete CR"}).json()[
        "classroom"
    ]
    assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": "Deletable Essay",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    ).json()[0]

    UserContext.current_user = student
    join = client.post(
        "/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]}
    )
    assert join.status_code == 200, join.text

    # 学生打开工作区后产生写作会话 → 不允许删除
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
    assert workspace.status_code == 200, workspace.text

    UserContext.current_user = teacher
    blocked = client.delete(f"/api/v1/assignments/{assignment['id']}")
    assert blocked.status_code == 400, blocked.text

    # 没有任何学生活动的作业可以删除,并清掉相关通知
    clean_assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": "Untouched Essay",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
        },
    ).json()[0]

    UserContext.current_user = student
    before = client.get("/api/v1/me/notifications/summary").json()["total"]
    assert before >= 1

    UserContext.current_user = teacher
    deleted = client.delete(f"/api/v1/assignments/{clean_assignment['id']}")
    assert deleted.status_code == 200, deleted.text
    assert (
        client.get(f"/api/v1/teacher/assignments/{clean_assignment['id']}").status_code
        == 404
    )

    UserContext.current_user = student
    after = client.get("/api/v1/me/notifications/summary").json()["total"]
    assert after == before - 1


def test_active_writing_seconds_ignores_idle_gaps():
    # 两块写作(各 60s),中间隔了一小时 —— 空档不该被算成写作时长。
    marks = [0, 30, 60, 3660, 3690, 3720]

    assert education_profile_module._estimate_active_writing_seconds(marks) == 120
    # 单次操作没有跨度,按一个最小块计,而不是 0。
    assert education_profile_module._estimate_active_writing_seconds([100]) == 30
    assert education_profile_module._estimate_active_writing_seconds([]) is None


def test_end_loaded_ratio_counts_only_the_final_tenth():
    diffs = [
        {"created_at": 0, "inserted_length": 100},
        {"created_at": 950, "inserted_length": 300},
    ]

    ratio = education_profile_module._compute_end_loaded_ratio(diffs, 0, 1000)

    assert ratio == 0.75


def test_deadline_window_ratio_uses_the_final_24_hours():
    due_at = 200000
    diffs = [
        {"inserted_length": 50, "created_at": due_at - 90000},
        {"inserted_length": 30, "created_at": due_at - 3600},
        {"inserted_length": 20, "created_at": due_at + 60},
    ]
    assert education_profile_module._compute_deadline_window_ratio(diffs, due_at) == 0.5


def test_reflection_score_separates_concrete_from_generic():
    generic = education_profile_module._score_reflection(
        _reflection_payload(
            action="改了部分内容",
            location="第二段",
            judgement="感觉这样会更好一些",
            next_step="继续改进",
        )
    )
    concrete = education_profile_module._score_reflection(_reflection_payload())

    assert concrete["score"] > generic["score"]
    assert concrete["score"] >= 60
    assert education_profile_module._score_reflection(None)["score"] == 0


def test_collaboration_index_falls_back_to_reflection_without_ai():
    # 完全没用 AI 的提交不该被「消化度 0」拖成低分。
    without_ai = education_profile_module._compute_collaboration_index(
        digestion_ratio=0,
        prompt_count=0,
        reflection_quality=80,
        ai_ratio=0.0,
        ai_used=False,
    )
    with_ai = education_profile_module._compute_collaboration_index(
        digestion_ratio=0,
        prompt_count=0,
        reflection_quality=80,
        ai_ratio=0.5,
        ai_used=True,
    )

    assert without_ai == 80
    assert with_ai < without_ai


def test_submission_form_allows_no_ai_and_rejects_unknown_help_types():
    form = SubmissionCreateForm(
        writing_session_id="session",
        final_content_text="student draft",
        ai_used=False,
        ai_help_types=[],
        data_completeness=_evidence_completeness(),
        reflection=_reflection_payload(),
    )
    assert form.ai_help_types == []
    with pytest.raises(ValueError):
        SubmissionCreateForm(
            writing_session_id="session",
            final_content_text="draft",
            ai_used=True,
            ai_help_types=["Magic answer generator"],
            data_completeness=_evidence_completeness(),
            reflection=_reflection_payload(),
        )
    with pytest.raises(ValueError):
        SubmissionCreateForm(
            writing_session_id="session",
            final_content_text="draft",
            ai_used=False,
            ai_help_types=[],
            data_completeness=_evidence_completeness(),
            reflection=_reflection_payload(),
            legacy_reflection_text="not accepted",
        )


def test_editor_operation_requires_client_event_ordering():
    operation = EditorOperationInput(
        op_type="keyboard_input",
        source_type="user_typed",
        start_offset=0,
        end_offset=1,
        inserted_text="a",
        batch_id="batch",
        occurred_at_ms=1_700_000_000_000,
        client_sequence=7,
    )
    assert operation.occurred_at_ms == 1_700_000_000_000
    assert operation.client_sequence == 7
    with pytest.raises(ValueError):
        EditorOperationInput(
            op_type="keyboard_input",
            source_type="user_typed",
            batch_id="batch",
        )


def test_profile_normalizes_scores_by_assignment_maximum(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Fifty Point Essay", score_max=50
    )
    UserContext.current_user = teacher
    too_high = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "reviewed", "score": 51},
    )
    assert too_high.status_code == 400
    invalid_rubric = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 40,
            "rubric_scores": {"ideas": 40, "structure": 0, "evidence": 0},
        },
    )
    assert invalid_rubric.status_code == 400
    reviewed = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 40,
            "rubric_scores": {"ideas": 14, "structure": 13, "evidence": 13},
        },
    )
    assert reviewed.status_code == 200
    profile = client.get(
        f"/api/v1/teacher/classrooms/{assignment['classroom_id']}/students/{student.id}/profile"
    ).json()
    assert profile["timeline"][0]["score_max"] == 50
    assert profile["timeline"][0]["normalized_score"] == 80
    assert profile["portfolio_summary"]["average_score_percent"] == 80


def test_student_profile_tracks_round_progress_and_trends(
    education_client, monkeypatch
):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "Growth Essay"
    )

    UserContext.current_user = teacher
    returned = client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "score": 70,
            "returned_comment": "Add evidence to the second paragraph",
            "resubmit_due_at": 2100000000,
            "rubric_scores": {"ideas": 24, "structure": 23, "evidence": 23},
        },
    )
    assert returned.status_code == 200, returned.text

    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(
            session_id,
            "a substantially longer revised draft that adds the evidence"
            " the teacher asked for",
        ),
    )
    assert resubmit.status_code == 200, resubmit.text
    second_submission_id = resubmit.json()["submission_id"]

    UserContext.current_user = teacher
    reviewed = client.post(
        f"/api/v1/teacher/submissions/{second_submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 88,
            "overall_comment": "Much stronger evidence",
            "rubric_scores": {"ideas": 30, "structure": 29, "evidence": 29},
        },
    )
    assert reviewed.status_code == 200, reviewed.text

    classroom_id = client.get("/api/v1/teacher/classrooms").json()[0]["classroom"]["id"]
    profile_res = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile"
    )
    assert profile_res.status_code == 200, profile_res.text
    profile = profile_res.json()

    assert profile["metric_version"] == PROFILE_METRIC_VERSION

    # 两轮都进时间线:成长看的是轮次之间的变化,历史轮不能丢。
    assert [point["round_no"] for point in profile["timeline"]] == [1, 2]
    assert [point["score"] for point in profile["timeline"]] == [70, 88]
    assert profile["timeline"][0]["is_current"] is False
    assert profile["timeline"][1]["is_current"] is True
    assert [point["round_no"] for point in profile["cross_assignment_timeline"]] == [2]
    # 客户端确认编辑事件采集链路已完整落盘时，零条操作是真实的 0，
    # 不能再被误判成采集缺失。
    assert (
        profile["timeline"][0]["data_completeness"]["editor_operations"] == "complete"
    )
    assert profile["timeline"][0]["active_writing_seconds"] == 0
    # 当前轮才计入作业统计与平均分
    assert profile["portfolio_summary"]["submitted_count"] == 1
    assert profile["portfolio_summary"]["average_score_percent"] == 88

    assert len(profile["round_progress"]) == 1
    progress = profile["round_progress"][0]
    assert progress["from_round"] == 1
    assert progress["to_round"] == 2
    assert progress["score_delta"] == 18
    assert progress["char_delta"] > 0
    assert progress["revision_ratio"] > 0
    assert progress["turnaround_seconds"] is not None

    # 两次提交可以展示折线，但不足以生成成长方向；至少需要三个样本。
    assert profile["trends"] == []

    codes = [insight["code"] for insight in profile["insights"]]
    assert "round_improvement" in codes
    assert "not_enough_data" in codes

    # 读取只消费版本一致的画像快照，不再碰历史版本与来源表。
    def fail_live_aggregation(*args, **kwargs):
        raise AssertionError("profile reads must not aggregate writing versions")

    monkeypatch.setattr(Education, "get_versions", fail_live_aggregation)
    monkeypatch.setattr(Education, "get_submissions_by_student", fail_live_aggregation)
    monkeypatch.setattr(
        Education, "get_profile_evidence_snapshots", fail_live_aggregation
    )
    second_round_only = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile",
        params={"assignment_id": assignment["id"], "round_no": 2},
    )
    assert second_round_only.status_code == 200, second_round_only.text
    assert [point["round_no"] for point in second_round_only.json()["timeline"]] == [2]

    invalid_range = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile",
        params={"start_at": 20, "end_at": 10},
    )
    assert invalid_range.status_code == 422

    paged = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile",
        params={"limit": 1},
    )
    assert paged.status_code == 200, paged.text
    assert paged.json()["timeline_pagination"] == {
        "total": 2,
        "limit": 1,
        "offset": 0,
    }
    assert len(paged.json()["timeline"]) == 1
    # 分页只裁剪明细，不能改变完整筛选集合上的汇总与洞察。
    assert paged.json()["filtered_summary"]["point_count"] == 2
    assert paged.json()["filtered_summary"] == profile["filtered_summary"]
    assert paged.json()["insights"] == profile["insights"]

    # 历史轮的分析必须停在自己那一版正文上,不能读到第二轮的字数
    assert profile["timeline"][0]["total_chars"] < profile["timeline"][1]["total_chars"]


def test_student_profile_requires_classroom_membership(education_client):
    client, teacher, _, student, outsider, _ = education_client
    _setup_submitted_assignment(client, teacher, student, "Membership Guard")

    UserContext.current_user = teacher
    classroom_id = client.get("/api/v1/teacher/classrooms").json()[0]["classroom"]["id"]

    missing = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{outsider.id}/profile"
    )
    assert missing.status_code == 404, missing.text

    UserContext.current_user = outsider
    forbidden = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile"
    )
    assert forbidden.status_code == 403, forbidden.text


def test_default_profile_reads_materialized_aggregate(
    education_client, monkeypatch
):
    client, teacher, _, student, _, _ = education_client
    assignment, _, _ = _setup_submitted_assignment(
        client, teacher, student, "Materialized Aggregate"
    )

    def fail_request_time_aggregation(*args, **kwargs):
        raise AssertionError("default profile must use its materialized aggregate")

    monkeypatch.setattr(
        profile_snapshots_module,
        "build_student_profile_aggregate",
        fail_request_time_aggregation,
    )
    UserContext.current_user = teacher
    response = client.get(
        f"/api/v1/teacher/classrooms/{assignment['classroom_id']}/students/{student.id}/profile"
    )
    assert response.status_code == 200, response.text
    assert response.json()["aggregate_materialized"] is True
    assert response.json()["aggregate_revision"] == 1


def test_profile_snapshot_failure_rolls_back_review(education_client, monkeypatch):
    client, teacher, _, student, _, session_local = education_client
    assignment, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Atomic Review"
    )

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(
        education_router_module, "project_profile_evidence", fail_snapshot
    )
    UserContext.current_user = teacher
    with pytest.raises(RuntimeError, match="snapshot failed"):
        client.post(
            f"/api/v1/teacher/submissions/{submission_id}/review",
            json={
                "review_status": "reviewed",
                "score": 80,
                "rubric_scores": {"ideas": 27, "structure": 27, "evidence": 26},
            },
        )

    with session_local() as session:
        assert (
            session.query(SubmissionReview)
            .filter(SubmissionReview.submission_id == submission_id)
            .first()
            is None
        )
        assert (
            session.query(SubmissionReviewEvent)
            .filter(SubmissionReviewEvent.submission_id == submission_id)
            .count()
            == 0
        )
        assert (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .count()
            == 1
        )


def test_profile_snapshot_failure_rolls_back_new_submission_round(
    education_client, monkeypatch
):
    client, teacher, _, student, _, session_local = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "Atomic Submission"
    )
    UserContext.current_user = teacher
    returned = client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "score": 70,
            "rubric_scores": {"ideas": 24, "structure": 23, "evidence": 23},
            "returned_comment": "Revise evidence",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text

    with session_local() as session:
        version_count_before = session.query(WritingVersion).count()
        reflection_count_before = session.query(MicroReflection).count()
        evidence_count_before = session.query(ProfileEvidenceSnapshot).count()
        writing_session = session.get(WritingSession, session_id)
        note_before = dict(session.get(Note, writing_session.note_id).data)

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(
        education_router_module, "project_profile_evidence", fail_snapshot
    )
    UserContext.current_user = student
    with pytest.raises(RuntimeError, match="snapshot failed"):
        client.post(
            f"/api/v1/assignments/{assignment['id']}/submit",
            json=_submit_body(session_id, "A revised draft that should roll back"),
        )

    with session_local() as session:
        rows = (
            session.query(Submission)
            .filter(
                Submission.assignment_id == assignment["id"],
                Submission.student_id == student.id,
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].id == first_submission_id
        assert rows[0].is_current == 1
        assert session.query(WritingVersion).count() == version_count_before
        assert session.query(MicroReflection).count() == reflection_count_before
        assert session.query(ProfileEvidenceSnapshot).count() == evidence_count_before
        writing_session = session.get(WritingSession, session_id)
        assert session.get(Note, writing_session.note_id).data == note_before


def test_submission_transaction_works_with_session_sharing_disabled(
    education_client,
):
    client, teacher, _, student, _, session_local = education_client
    original = internal_db.DATABASE_ENABLE_SESSION_SHARING
    internal_db.DATABASE_ENABLE_SESSION_SHARING = False
    try:
        assignment, _, submission_id = _setup_submitted_assignment(
            client, teacher, student, "Default Session Transaction"
        )
    finally:
        internal_db.DATABASE_ENABLE_SESSION_SHARING = original

    with session_local() as session:
        assert session.get(Submission, submission_id) is not None
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .one()
        )
        assert evidence.assignment_id == assignment["id"]
        assert (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.evidence_snapshot_id == evidence.id)
            .count()
            == 1
        )


def test_profile_snapshots_keep_multiple_metric_versions(education_client):
    client, teacher, _, student, _, session_local = education_client
    assignment, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Versioned Snapshot"
    )
    with session_local() as session:
        original = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .one()
        )
        copied_payload = dict(original.projection_json)
        copied_payload["metric_version"] = "future-metric"
        session.add(
            ProfileAlgorithmRelease(
                id=str(uuid.uuid4()),
                metric_version="future-metric",
                insight_version="future-insight",
                evidence_schema_versions=[PROFILE_EVIDENCE_SCHEMA_VERSION],
                formula_config_json=session.query(ProfileAlgorithmRelease)
                .filter(ProfileAlgorithmRelease.metric_version == PROFILE_METRIC_VERSION)
                .one()
                .formula_config_json,
                code_commit_sha="test",
                code_checksum="future-checksum",
                status="retired",
                created_by="test",
                created_at=original.generated_at,
                activated_at=None,
            )
        )
        session.flush()
        session.add(
            ProfileMetricProjection(
                id=str(uuid.uuid4()),
                evidence_snapshot_id=original.evidence_snapshot_id,
                submission_id=original.submission_id,
                student_id=original.student_id,
                assignment_id=original.assignment_id,
                round_no=original.round_no,
                submitted_at=original.submitted_at,
                review_revision=original.review_revision,
                metric_version="future-metric",
                projection_json=copied_payload,
                input_hash="1" * 64,
                output_hash=canonical_json_hash(copied_payload),
                run_id=None,
                generated_at=original.generated_at,
            )
        )
        session.flush()
        materialize_student_profile_aggregate(
            student_id=student.id,
            assignment_ids=[assignment["id"]],
            scope_kind="classroom",
            scope_id=assignment["classroom_id"],
            metric_version="future-metric",
            db=session,
            commit=False,
        )
        session.commit()
        assert (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .count()
            == 2
        )

    UserContext.current_user = teacher
    classroom_id = assignment["classroom_id"]
    profile = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile",
        params={"metric_version": "future-metric"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["metric_version"] == "future-metric"
    assert profile.json()["excluded_snapshot_count"] == 1
    assert set(profile.json()["available_metric_versions"]) == {
        PROFILE_METRIC_VERSION,
        "future-metric",
    }
    unknown = client.get(
        f"/api/v1/teacher/classrooms/{classroom_id}/students/{student.id}/profile",
        params={"metric_version": "not-registered"},
    )
    assert unknown.status_code == 422


def test_explicit_profile_recompute_is_audited_and_idempotent(education_client):
    client, teacher, _, student, _, session_local = education_client
    _, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Explicit Projection Run"
    )

    with session_local() as session:
        original = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .one()
        )
        original_output_hash = original.output_hash
        run_id = recompute_profile_projections(
            session,
            requested_by=teacher.id,
            activate=True,
            batch_size=10,
        )
        run = session.get(ProfileProjectionRun, run_id)
        assert run.status == "completed"
        assert run.expected_count == 1
        assert run.succeeded_count == 1
        assert run.failed_count == 0
        rows = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].output_hash == original_output_hash


def test_failed_profile_recompute_is_audited_without_activation(
    education_client, monkeypatch
):
    client, teacher, _, student, _, session_local = education_client
    _setup_submitted_assignment(client, teacher, student, "Failed Projection Run")

    def fail_projection(*args, **kwargs):
        raise RuntimeError("deterministic projection failure")

    monkeypatch.setattr(
        profile_recompute_module, "project_profile_evidence", fail_projection
    )
    with session_local() as session:
        active_before = Education.get_active_profile_metric_version(db=session)
        with pytest.raises(RuntimeError, match="coverage is incomplete"):
            recompute_profile_projections(
                session,
                requested_by=teacher.id,
                activate=True,
                batch_size=10,
            )
        run = (
            session.query(ProfileProjectionRun)
            .order_by(ProfileProjectionRun.created_at.desc())
            .first()
        )
        assert run.status == "failed"
        assert run.failed_count == 1
        assert run.error_json[0]["error_type"] == "RuntimeError"
        assert Education.get_active_profile_metric_version(db=session) == active_before


def test_profile_evidence_and_projections_reject_mutation(education_client):
    client, teacher, _, student, _, session_local = education_client
    _, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Immutable Profile Facts"
    )

    with session_local() as session:
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .one()
        )
        assert (
            evidence.evidence_json["evidence_schema_version"]
            == PROFILE_EVIDENCE_SCHEMA_VERSION
        )
        assert (
            evidence.evidence_json["assignment"]["title"] == "Immutable Profile Facts"
        )
        assert (
            evidence.evidence_json["document"]["content_text"]
            == "first draft text for the round essay"
        )
        assert len(evidence.evidence_json["document"]["content_hash"]) == 64
        assert evidence.evidence_json["capture_manifest"]["collector_version"]
        evidence.evidence_hash = "0" * 64
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()

        session.execute(
            ProfileEvidenceSnapshot.__table__.update()
            .where(ProfileEvidenceSnapshot.id == evidence.id)
            .values(evidence_hash="0" * 64)
        )
        session.commit()
        session.expire_all()
        tampered = Education.get_latest_profile_evidence_snapshot(
            submission_id, db=session
        )
        with pytest.raises(ValueError, match="hash verification failed"):
            build_analysis_from_evidence(tampered)

        projection = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.submission_id == submission_id)
            .one()
        )
        projection.output_hash = "0" * 64
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()


def test_profile_read_rejects_tampered_projection(education_client):
    client, teacher, _, student, _, session_local = education_client
    assignment, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Tampered Projection"
    )
    with session_local() as session:
        session.execute(
            ProfileMetricProjection.__table__.update()
            .where(ProfileMetricProjection.submission_id == submission_id)
            .values(output_hash="0" * 64)
        )
        session.commit()

    UserContext.current_user = teacher
    response = client.get(
        f"/api/v1/teacher/classrooms/{assignment['classroom_id']}/students/{student.id}/profile"
    )
    assert response.status_code == 422, response.text
    assert "hash verification failed" in response.json()["detail"]


def test_profile_read_rejects_tampered_aggregate(education_client):
    client, teacher, _, student, _, session_local = education_client
    assignment, _, _ = _setup_submitted_assignment(
        client, teacher, student, "Tampered Aggregate"
    )
    with session_local() as session:
        aggregate = (
            session.query(StudentProfileAggregateProjection)
            .filter(
                StudentProfileAggregateProjection.student_id == student.id,
                StudentProfileAggregateProjection.scope_kind == "classroom",
                StudentProfileAggregateProjection.scope_id
                == assignment["classroom_id"],
            )
            .one()
        )
        session.execute(
            StudentProfileAggregateProjection.__table__.update()
            .where(StudentProfileAggregateProjection.id == aggregate.id)
            .values(output_hash="0" * 64)
        )
        session.commit()

    UserContext.current_user = teacher
    response = client.get(
        f"/api/v1/teacher/classrooms/{assignment['classroom_id']}/students/{student.id}/profile"
    )
    assert response.status_code == 422, response.text
    assert "aggregate hash verification failed" in response.json()["detail"]


def test_submission_review_events_are_append_only(education_client):
    client, teacher, _, student, _, session_local = education_client
    _, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Review Event History"
    )
    UserContext.current_user = teacher
    pending = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "pending"},
    )
    assert pending.status_code == 200, pending.text
    reviewed = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 80,
            "rubric_scores": {"ideas": 27, "structure": 27, "evidence": 26},
        },
    )
    assert reviewed.status_code == 200, reviewed.text

    with session_local() as session:
        events = (
            session.query(SubmissionReviewEvent)
            .filter(SubmissionReviewEvent.submission_id == submission_id)
            .order_by(SubmissionReviewEvent.review_revision.asc())
            .all()
        )
        assert [event.review_revision for event in events] == [1, 2]
        assert [event.review_status for event in events] == ["pending", "reviewed"]
        assert events[0].score is None
        assert events[1].score == 80
        aggregate_revisions = (
            session.query(StudentProfileAggregateProjection)
            .filter(
                StudentProfileAggregateProjection.student_id == student.id,
                StudentProfileAggregateProjection.scope_kind == "classroom",
            )
            .order_by(
                StudentProfileAggregateProjection.aggregate_revision.asc()
            )
            .all()
        )
        assert [item.aggregate_revision for item in aggregate_revisions] == [1, 2, 3]


def test_multi_class_assignments_growth_goals_and_teacher_notes(education_client):
    client, teacher, _, student, _, session_local = education_client
    UserContext.current_user = teacher

    classrooms = []
    assignments = []
    for index in (1, 2):
        classroom_response = client.post(
            "/api/v1/classrooms", json={"name": f"Writing Class {index}"}
        )
        assert classroom_response.status_code == 200, classroom_response.text
        classroom = classroom_response.json()["classroom"]
        classrooms.append(classroom)
        member_response = client.post(
            f"/api/v1/teacher/classrooms/{classroom['id']}/members",
            json={"user_id": student.id, "member_role": "student"},
        )
        assert member_response.status_code == 200, member_response.text
        assignment_response = client.post(
            "/api/v1/assignments",
            json={
                "title": f"Essay {index}",
                "description": "Multi-class assignment",
                "classroom_ids": [classroom["id"]],
                "score_max": 100,
                "rubric_schema": _rubric_schema(),
                "due_at": 2100000000,
            },
        )
        assert assignment_response.status_code == 200, assignment_response.text
        assignments.append(assignment_response.json()[0])

    UserContext.current_user = student
    assignment_list = client.get("/api/v1/me/writing/assignments")
    assert assignment_list.status_code == 200, assignment_list.text
    assignment_memberships = {
        item["assignment"]["id"]: item["membership"]["classroom_id"]
        for item in assignment_list.json()
    }
    assert assignment_memberships == {
        assignments[0]["id"]: classrooms[0]["id"],
        assignments[1]["id"]: classrooms[1]["id"],
    }

    home = client.get("/api/v1/me/writing/home")
    assert home.status_code == 200, home.text
    assert {item["id"] for item in home.json()["classrooms"]} == {
        classrooms[0]["id"],
        classrooms[1]["id"],
    }

    goal_response = client.post(
        "/api/v1/me/writing/goals",
        json={
            "goal_text": "Create the outline two days before the next deadline",
            "classroom_id": classrooms[1]["id"],
            "assignment_id": assignments[1]["id"],
            "target_at": 2000000000,
        },
    )
    assert goal_response.status_code == 200, goal_response.text
    goal = goal_response.json()
    completed_goal = client.patch(
        f"/api/v1/me/writing/goals/{goal['id']}",
        json={"status": "completed"},
    )
    assert completed_goal.status_code == 200, completed_goal.text
    assert completed_goal.json()["status"] == "completed"

    student_profile = client.get("/api/v1/me/writing/profile")
    assert student_profile.status_code == 200, student_profile.text
    assert {item["id"] for item in student_profile.json()["classrooms"]} == {
        classrooms[0]["id"],
        classrooms[1]["id"],
    }
    assert student_profile.json()["growth_goals"][0]["id"] == goal["id"]
    assert "teacher_notes" not in student_profile.json()

    UserContext.current_user = teacher
    note_response = client.post(
        f"/api/v1/teacher/classrooms/{classrooms[0]['id']}/students/{student.id}/profile-notes",
        json={"content": "Follow up on outline planning next week."},
    )
    assert note_response.status_code == 200, note_response.text
    note = note_response.json()

    teacher_profile = client.get(
        f"/api/v1/teacher/classrooms/{classrooms[0]['id']}/students/{student.id}/profile"
    )
    assert teacher_profile.status_code == 200, teacher_profile.text
    assert teacher_profile.json()["teacher_notes"][0]["id"] == note["id"]
    assert teacher_profile.json()["classrooms"][0]["id"] == classrooms[0]["id"]

    updated_note = client.patch(
        f"/api/v1/teacher/profile-notes/{note['id']}",
        json={"content": "Outline planning improved; check evidence selection next."},
    )
    assert updated_note.status_code == 200, updated_note.text
    deleted_note = client.delete(f"/api/v1/teacher/profile-notes/{note['id']}")
    assert deleted_note.status_code == 200, deleted_note.text
    with session_local() as session:
        revisions = (
            session.query(TeacherStudentNoteRevision)
            .filter(TeacherStudentNoteRevision.note_id == note["id"])
            .order_by(TeacherStudentNoteRevision.created_at.asc())
            .all()
        )
        assert [revision.action for revision in revisions] == ["update", "delete"]
        stored_note = session.get(TeacherStudentNote, note["id"])
        assert stored_note.deleted_at is not None


def test_analysis_payload_usability_treats_history_as_immutable():
    stale = {"logic_version": "ancient", "summary": {}}
    current_round = SimpleNamespace(is_current=1)
    historical_round = SimpleNamespace(is_current=0)

    # GET 对当前轮和历史轮都只返回已物化结果；版本升级必须显式 POST/任务重算。
    assert (
        education_analysis_module._is_analysis_payload_usable(current_round, stale)
        is True
    )
    assert (
        education_analysis_module._is_analysis_payload_usable(historical_round, stale)
        is True
    )
    # 缺少物化结果不会触发 GET 自动补建。
    assert (
        education_analysis_module._is_analysis_payload_usable(historical_round, None)
        is False
    )


def test_analysis_get_does_not_repair_missing_materialization(education_client):
    client, teacher, _, student, _, session_local = education_client
    _, _, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Missing Materialized Analysis"
    )
    with session_local() as session:
        session.query(AnalysisResult).filter(
            AnalysisResult.submission_id == submission_id
        ).delete()
        session.commit()

    UserContext.current_user = teacher
    response = client.get(
        f"/api/v1/teacher/submissions/{submission_id}/analysis/summary"
    )
    assert response.status_code == 409, response.text
    with session_local() as session:
        assert (
            session.query(AnalysisResult)
            .filter(AnalysisResult.submission_id == submission_id)
            .count()
            == 0
        )


def test_historical_round_analysis_survives_logic_version_bump(
    education_client, monkeypatch
):
    client, teacher, _, student, _, session_local = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "Immutable History"
    )

    UserContext.current_user = teacher
    returned = client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Revise",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text

    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(
            session_id, "a much longer second round draft with new evidence"
        ),
    )
    assert resubmit.status_code == 200, resubmit.text

    UserContext.current_user = teacher

    def fail_live_rebuild(*args, **kwargs):
        raise AssertionError("analysis GET must not rebuild from live writing data")

    monkeypatch.setattr(Education, "get_versions", fail_live_rebuild)
    monkeypatch.setattr(Education, "get_provenance_segments", fail_live_rebuild)
    monkeypatch.setattr(Education, "get_editor_operations", fail_live_rebuild)
    stored_first = client.get(
        f"/api/v1/teacher/submissions/{first_submission_id}/analysis/summary"
    ).json()

    # 模拟逻辑版本升级:当前轮该重算,历史轮必须原样返回存档。
    original_version = education_analysis_module._ANALYSIS_LOGIC_VERSION
    education_analysis_module._ANALYSIS_LOGIC_VERSION = f"{original_version}-next"
    try:
        after_bump = client.get(
            f"/api/v1/teacher/submissions/{first_submission_id}/analysis/summary"
        ).json()
    finally:
        education_analysis_module._ANALYSIS_LOGIC_VERSION = original_version

    assert after_bump["total_chars"] == stored_first["total_chars"]

    with session_local() as session:
        rows = (
            session.query(AnalysisResult)
            .filter(AnalysisResult.submission_id == first_submission_id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload_json["logic_version"] == original_version


def test_revision_depth_measures_rework_not_autosave_count():
    # 一路往下写:写了 1000 字,没回头删过 → 修订深度 0
    assert education_profile_module._compute_revision_depth(0, 1000) == 0
    # 删改量达到写入量的三成即记满分(目标比例)
    assert education_profile_module._compute_revision_depth(300, 1000) == 100
    assert education_profile_module._compute_revision_depth(150, 1000) == 50
    # 删改比写入还多也不会超过 100
    assert education_profile_module._compute_revision_depth(2000, 1000) == 100
    # 没写过东西不该除以零
    assert education_profile_module._compute_revision_depth(0, 0) is None


def test_process_index_ignores_version_count():
    # 自动保存次数再多,只要没回头改过,过程投入就不该被抬高。
    steady_typing = education_profile_module._compute_process_index(
        revision_depth=0, writing_span_seconds=0, end_loaded_ratio=1.0
    )
    reworked = education_profile_module._compute_process_index(
        revision_depth=100, writing_span_seconds=0, end_loaded_ratio=1.0
    )

    assert steady_typing == 0
    assert reworked == 33
    assert education_profile_module._compute_process_index(None, 0, None) is None


def test_profile_trend_compares_early_and_recent_windows():
    trend = education_profile_module._build_trend(
        "normalized_score", [60, 62, 64, 82, 84, 86]
    )

    assert trend is not None
    assert trend.first == 62
    assert trend.last == 84
    assert trend.delta == 22
    assert trend.direction == "up"
    assert education_profile_module._build_trend("score", [60, 80]) is None


def test_profile_insights_rank_confidence_and_combine_ai_evidence():
    completeness = SimpleNamespace(
        version_data="complete",
        editor_operations="complete",
        source_tracking="complete",
        scoring="complete",
    )
    timeline = [
        SimpleNamespace(
            assignment_id=f"assignment-{index}",
            is_current=True,
            submission_id=f"submission-{index}",
            ai_ratio=0.4,
            digestion_ratio=20,
            reflection_quality=30,
            revision_depth=10,
            normalized_score=70,
            deadline_window_ratio=0.2,
            data_completeness=completeness,
        )
        for index in range(3)
    ]
    round_progress = [
        SimpleNamespace(score_delta=0, revision_ratio=5),
    ]
    trends = {
        "normalized_score": StudentProfileMetricTrend(
            key="normalized_score",
            first=70,
            last=70,
            delta=0,
            direction="flat",
            sample_count=3,
        )
    }
    help_shift = StudentProfileHelpTypeShift(
        early=StudentProfileHelpTypeSummary(),
        recent=StudentProfileHelpTypeSummary(),
    )
    reflection_quality = StudentProfileReflectionQuality(
        count=3, average_score=30, average_chars=20
    )

    insights = education_profile_module._build_profile_insights(
        timeline, round_progress, trends, help_shift, reflection_quality
    )

    assert insights[0].severity == "high"
    assert insights[0].teaching_value == 5
    assert all(0 <= insight.confidence <= 1 for insight in insights)
    assert all(insight.sample_count >= 0 for insight in insights)
    assert "ai_use_needs_review" in {insight.code for insight in insights}


def _create_coaching_assignment(client, teacher, student, coaching_style=None):
    """建班 + 发作业 + 学生入班，返回 (assignment, 打开写作区的函数)。"""
    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Coaching"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    payload = {
        "title": "Argument Essay 1",
        "description": "Write a short argument essay.",
        "classroom_ids": [classroom["id"]],
        "score_max": 100,
        "rubric_schema": _rubric_schema(),
        "due_at": 2000000000,
    }
    if coaching_style is not None:
        payload["coaching_style"] = coaching_style

    create_assignment_res = client.post("/api/v1/assignments", json=payload)
    assert create_assignment_res.status_code == 200, create_assignment_res.text
    assignment = create_assignment_res.json()[0]

    UserContext.current_user = student
    join_res = client.post(
        "/api/v1/classrooms/join",
        json={"invite_code": classroom["invite_code"]},
    )
    assert join_res.status_code == 200, join_res.text

    def open_workspace():
        UserContext.current_user = student
        workspace_res = client.get(f"/api/v1/assignments/{assignment['id']}/workspace")
        assert workspace_res.status_code == 200, workspace_res.text
        return workspace_res.json()

    return assignment, open_workspace


def test_assignment_defaults_to_balanced_coaching_style(education_client):
    client, teacher, _, student, _, _ = education_client

    assignment, open_workspace = _create_coaching_assignment(client, teacher, student)

    assert assignment["coaching_style"] == "balanced"

    system_prompt = open_workspace()["project"]["data"]["system_prompt"]
    assert "【作业】Argument Essay 1" in system_prompt
    assert "【辅导方式】平衡" in system_prompt


def test_assignment_coaching_style_changes_system_prompt(education_client):
    client, teacher, _, student, _, _ = education_client

    assignment, open_workspace = _create_coaching_assignment(
        client, teacher, student, coaching_style="socratic"
    )

    assert assignment["coaching_style"] == "socratic"
    assert "【辅导方式】严格提问式" in open_workspace()["project"]["data"]["system_prompt"]

    UserContext.current_user = teacher
    update_res = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"coaching_style": "hands_off"},
    )
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["coaching_style"] == "hands_off"

    # 写作区每次打开都按最新作业重建系统提示，档位改动要能跟过来。
    refreshed = open_workspace()["project"]["data"]["system_prompt"]
    assert "【辅导方式】放手" in refreshed
    assert "严格提问式" not in refreshed


def test_blank_coaching_prompt_leaves_assignment_context_only(education_client):
    client, teacher, _, student, _, _ = education_client

    asyncio.run(
        Config.upsert(
            {
                "education.coaching_prompts": {
                    "socratic": "",
                    "balanced": "",
                    "hands_off": "",
                }
            }
        )
    )

    _, open_workspace = _create_coaching_assignment(client, teacher, student)

    system_prompt = open_workspace()["project"]["data"]["system_prompt"]
    assert "【作业】Argument Essay 1" in system_prompt
    assert "【辅导方式】" not in system_prompt


def test_unknown_coaching_style_is_rejected(education_client):
    client, teacher, _, _, _, _ = education_client

    UserContext.current_user = teacher
    create_classroom_res = client.post(
        "/api/v1/classrooms", json={"name": "Grade 8 Coaching Reject"}
    )
    assert create_classroom_res.status_code == 200, create_classroom_res.text
    classroom = create_classroom_res.json()["classroom"]

    create_assignment_res = client.post(
        "/api/v1/assignments",
        json={
            "title": "Argument Essay 1",
            "classroom_ids": [classroom["id"]],
            "score_max": 100,
            "rubric_schema": _rubric_schema(),
            "due_at": 2000000000,
            "coaching_style": "strict",
        },
    )
    assert create_assignment_res.status_code == 422, create_assignment_res.text



_ASK_USER_TIMELINE = [{'id': 'm1', 'role': 'user', 'content': '帮我写作文', 'created_at': 100, 'output': None},
 {'id': 'm2',
  'role': 'assistant',
  'content': '',
  'created_at': 200,
  'output': [{'type': 'function_call',
              'id': 'fc_c1',
              'call_id': 'c1',
              'name': 'ask_user',
              'arguments': '{"questions": [{"id": "topic", "header": "Topic", '
                           '"question": "这篇文章你想写什么主题？", "options": [{"label": "校园现象", '
                           '"description": "身边看到的事"}, {"label": "思辨议题", "description": '
                           '"有正反两面的问题"}], "allow_other": true}, {"id": "reader", '
                           '"header": "Reader", "question": "你写给谁看？", "options": '
                           '[{"label": "同学", "description": "同龄人"}, {"label": "老师", '
                           '"description": "评卷人"}], "allow_other": true}]}',
              'status': 'completed'},
             {'type': 'function_call_output',
              'id': 'fco_c1',
              'call_id': 'c1',
              'output': [{'type': 'input_text',
                          'text': '{"status": "answered", "answers": {"topic": '
                                  '{"type": "other", "text": "我想写食堂排队这件事背后的公共秩序"}, '
                                  '"reader": {"type": "option", "option_index": 0, '
                                  '"label": "同学", "description": "同龄人"}}}'}],
              'status': 'completed'}]},
 {'id': 'm3',
  'role': 'assistant',
  'content': '',
  'created_at': 300,
  'output': [{'type': 'function_call',
              'id': 'fc_c2',
              'call_id': 'c2',
              'name': 'ask_user',
              'arguments': '{"questions": [{"id": "topic", "header": "Topic", '
                           '"question": "这篇文章你想写什么主题？", "options": [], "allow_other": '
                           'true}]}',
              'status': 'completed'},
             {'type': 'function_call_output',
              'id': 'fco_c2',
              'call_id': 'c2',
              'output': [{'type': 'input_text',
                          'text': 'Error: Each question requires 2-3 options.'}],
              'status': 'completed'}]},
 {'id': 'm4',
  'role': 'assistant',
  'content': '',
  'created_at': 400,
  'output': [{'type': 'function_call',
              'id': 'fc_c3',
              'call_id': 'c3',
              'name': 'ask_user',
              'arguments': '{"questions": [{"id": "reader", "header": "Reader", '
                           '"question": "你写给谁看？", "options": [{"label": "同学", '
                           '"description": "同龄人"}, {"label": "老师", "description": '
                           '"评卷人"}], "allow_other": true}]}',
              'status': 'rejected'},
             {'type': 'function_call_output',
              'id': 'fco_c3',
              'call_id': 'c3',
              'output': [{'type': 'input_text',
                          'text': 'Error: tool call rejected by user.'}],
              'status': 'completed'}]}]


def test_collect_clarification_exchanges_reads_chat_output():
    exchanges = collect_clarification_exchanges(_ASK_USER_TIMELINE)

    assert [item["status"] for item in exchanges] == ["answered", "invalid", "invalid"]

    answered = exchanges[0]
    assert [question["question"] for question in answered["questions"]] == [
        "这篇文章你想写什么主题？",
        "你写给谁看？",
    ]
    # 选项回答带得回标签文字，不只是 option_index。
    assert answered["questions"][1]["answer"] == {
        "type": "option",
        "option_index": 0,
        "label": "同学",
    }
    # 自由输入才是真正看得出学生在想什么的那部分。
    assert answered["questions"][0]["answer"]["type"] == "other"
    assert "食堂排队" in answered["questions"][0]["answer"]["text"]


def test_clarification_counters_ignore_rejected_tool_calls():
    summary = education_analysis_module._build_process_summary(
        [], _ASK_USER_TIMELINE, [], [], collect_clarification_exchanges(_ASK_USER_TIMELINE)
    )

    assert summary["clarification_question_count"] == 2
    assert summary["clarification_answered_count"] == 2
    assert summary["clarification_free_text_count"] == 1
    # 参数拼错被后端拒掉的调用是模型噪声，不能算成问过学生。
    assert summary["clarification_declined_count"] == 0


def test_student_and_teacher_read_the_same_answered_count():
    # 学生写作区和教师端过程摘要展示的是同一个数字，必须出自同一处实现。
    exchanges = collect_clarification_exchanges(_ASK_USER_TIMELINE)
    summary = education_analysis_module._build_process_summary(
        [], _ASK_USER_TIMELINE, [], [], exchanges
    )

    assert count_clarifications(exchanges) == {
        "clarification_question_count": summary["clarification_question_count"],
        "clarification_answered_count": summary["clarification_answered_count"],
        "clarification_free_text_count": summary["clarification_free_text_count"],
        "clarification_declined_count": summary["clarification_declined_count"],
    }
    assert count_clarifications(exchanges)["clarification_answered_count"] == 2


def test_writing_process_summary_is_owner_only(education_client):
    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    created = client.post("/api/v1/me/writing/personal", json={"title": "Draft"})
    assert created.status_code == 200, created.text
    session_id = created.json()["writing_session"]["id"]

    owner_res = client.get(f"/api/v1/writing/{session_id}/process-summary")
    assert owner_res.status_code == 200, owner_res.text
    # 工具没跑过时结果是空列表，计数自然是 0，不需要任何分支判断。
    assert owner_res.json() == {"clarification_answered_count": 0}

    UserContext.current_user = student
    foreign_res = client.get(f"/api/v1/writing/{session_id}/process-summary")
    assert foreign_res.status_code == 403, foreign_res.text


def test_clarification_collection_is_empty_when_tool_never_ran():
    timeline = [
        {"id": "m1", "role": "user", "content": "hi", "created_at": 1, "output": None},
        {"id": "m2", "role": "assistant", "content": "hello", "created_at": 2, "output": None},
    ]

    assert collect_clarification_exchanges(timeline) == []

    summary = education_analysis_module._build_process_summary([], timeline, [], [], [])
    assert summary["clarification_question_count"] == 0
    assert summary["clarification_answered_count"] == 0
    assert summary["clarification_free_text_count"] == 0
    assert summary["clarification_declined_count"] == 0



def test_submission_freezes_the_coaching_wording_in_force(education_client):
    client, teacher, _, student, _, _ = education_client

    assignment, _ = _create_coaching_assignment(
        client, teacher, student, coaching_style="socratic"
    )

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(workspace["writing_session"]["id"], "draft text for coaching"),
    )
    assert submit_res.status_code == 200, submit_res.text
    submission_id = submit_res.json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    coaching = detail["submission"]["stats_json"]["coaching"]
    assert coaching["style"] == "socratic"
    assert "严格提问式" in coaching["prompt"]

    # 管理员改了档位措辞，已交那一轮的记录不能跟着变。
    asyncio.run(
        Config.upsert(
            {
                "education.coaching_prompts": {
                    "socratic": "【辅导方式】改过的新说法。",
                    "balanced": "",
                    "hands_off": "",
                }
            }
        )
    )

    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    frozen = detail["submission"]["stats_json"]["coaching"]
    assert frozen["prompt"] == coaching["prompt"]
    assert "改过的新说法" not in frozen["prompt"]


# ---------------------------------------------------------------------------
# 提交前质疑环节
# ---------------------------------------------------------------------------


# 每一句都不一样。质疑要从中引用一句作为修订判定的锚点，同一句重复六遍的话，
# 学生改掉其中一处、剩下五处还在，就永远判不出「那一句变了」。
_DRAFT_SENTENCES = (
    "短视频降低了年轻人的注意力，因为它把时间切成了碎片。",
    "所有人都认为长视频已经没人看了，这是显而易见的事实。",
    "我身边的同学几乎都在刷短视频，可见这已经是普遍现象。",
    "平台的推荐算法让人停不下来，因此它必须为此负责。",
    "阅读能力的下降和短视频的普及是同时发生的，两者显然互为因果。",
    "综上所述，短视频对年轻人的影响是全面而深远的。",
)


def _long_draft():
    """越过最短正文门槛的草稿。正文太短时质疑没有可打的东西，服务端会拒绝。"""

    return "".join(_DRAFT_SENTENCES)


@contextmanager
def _fake_challenge_model(turn_text="你这一点说服不了我", closing=None, raw_turns=None):
    """替换质疑环节唯一的模型调用出口，测试不碰真实模型。

    收尾调用靠 system 提示词里的 JSON 约定识别（closing 那段带 "stood" 字样）。
    质疑轮按真实契约输出 JSON，quote 从正文里原样摘一句——摘不回原文的引用会被
    服务端判为生成失败，测试里也不该绕过这条。

    raw_turns 用来喂坏输出（不是 JSON、引用不在正文里），验证解析失败与重试。
    """

    calls = []

    def _draft_from(messages):
        body = messages[1]["content"].split("【作者的文章】\n", 1)[1]
        return body.split("\n\n", 1)[0]

    async def fake_generate(request, user, model_id, messages):
        calls.append({"model": model_id, "messages": messages})
        if '"stood"' in messages[0]["content"]:
            return json.dumps(
                closing or {"stood": [], "unresolved": []}, ensure_ascii=False
            )

        turn_calls = [
            call for call in calls if '"stood"' not in call["messages"][0]["content"]
        ]
        index = len(turn_calls) - 1
        if raw_turns is not None:
            return raw_turns[min(index, len(raw_turns) - 1)]

        draft = _draft_from(messages)
        sentences = [part + "。" for part in draft.split("。") if part.strip()]
        return json.dumps(
            {
                "quote": sentences[index % len(sentences)],
                "challenge": f"{turn_text} #{len(calls)}",
            },
            ensure_ascii=False,
        )

    original = education_challenge_module.generate_completion
    education_challenge_module.generate_completion = fake_generate
    try:
        yield calls
    finally:
        education_challenge_module.generate_completion = original


def _setup_challenge_assignment(
    client,
    teacher,
    student,
    rounds=3,
    focus_keys=("ideas",),
    title="Challenge Essay",
):
    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": f"CR {title}"}).json()[
        "classroom"
    ]

    UserContext.current_user = student
    client.post(
        "/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]}
    )

    UserContext.current_user = teacher
    create_res = client.post(
        "/api/v1/assignments",
        json={
            "title": title,
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": 100,
            "rubric_schema": _rubric_schema(100),
            "challenge_enabled": True,
            "challenge_rounds": rounds,
            "challenge_focus_keys": list(focus_keys),
        },
    )
    assert create_res.status_code == 200, create_res.text
    assignment = create_res.json()[0]

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    session_id = workspace["writing_session"]["id"]
    version_res = client.post(
        f"/api/v1/writing-sessions/{session_id}/versions",
        json={"trigger_type": "autosave", "content_text": _long_draft()},
    )
    assert version_res.status_code == 200, version_res.text
    return assignment, session_id


def _start_challenge(client, assignment_id, session_id):
    return client.post(
        f"/api/v1/assignments/{assignment_id}/challenge/start",
        json={"writing_session_id": session_id, "model": "test-model"},
    )


def _respond(client, challenge_id, turn_no, text="我补充一条调查数据来支撑这个判断。"):
    return client.post(
        f"/api/v1/challenge/{challenge_id}/respond",
        json={"turn_no": turn_no, "response_text": text, "model": "test-model"},
    )


def test_challenge_stops_at_planned_rounds_and_closes(education_client):
    """回合上限由服务端兜死，不靠提示词。答满就收尾，再答一轮直接拒。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=3
    )

    UserContext.current_user = student
    # 这里刻意用裸字符串：模型不按格式输出时，条目照样要能给学生看到，
    # 只是没有维度归属，不进班级那张统计表。
    with _fake_challenge_model(
        closing={"stood": ["立意站住了"], "unresolved": ["证据仍然不足"]}
    ) as calls:
        start_res = _start_challenge(client, assignment["id"], session_id)
        assert start_res.status_code == 200, start_res.text
        detail = start_res.json()
        assert detail["session"]["status"] == "in_progress"
        assert detail["session"]["planned_rounds"] == 3
        assert len(detail["turns"]) == 1
        challenge_id = detail["session"]["id"]

        for turn_no in (1, 2, 3):
            res = _respond(client, challenge_id, turn_no)
            assert res.status_code == 200, res.text
            detail = res.json()

        assert detail["session"]["status"] == "completed"
        assert len(detail["turns"]) == 3
        assert all(turn["response_text"] for turn in detail["turns"])
        # 这条是裸字符串喂进去的，文本照样留住，只是没有维度归属。
        unresolved = detail["session"]["closing_summary_json"]["unresolved"]
        assert [item["text"] for item in unresolved] == ["证据仍然不足"]
        assert unresolved[0]["focus_key"] is None
        assert detail["session"]["ended_at"] is not None

        # 三轮质疑 + 一次收尾 = 四次模型调用，不多不少。
        assert len(calls) == 4

        extra = _respond(client, challenge_id, 4)
        assert extra.status_code == 400, extra.text


def test_challenge_rejects_out_of_order_and_repeat_answers(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Order Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]

        # 第 1 轮还没答就想答第 2 轮
        assert _respond(client, challenge_id, 2).status_code == 400

        assert _respond(client, challenge_id, 1).status_code == 200
        # 同一轮答两次
        assert _respond(client, challenge_id, 1).status_code == 400


def test_challenge_single_focus_repeats_across_rounds(education_client):
    """教师只勾一个维度就三轮都打这一个，这是教师的选择，引擎不做纠正。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=3, focus_keys=("evidence",), title="Focus One"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        for turn_no in (1, 2, 3):
            detail = _respond(client, challenge_id, turn_no).json()

    assert [turn["focus_key"] for turn in detail["turns"]] == [
        "evidence",
        "evidence",
        "evidence",
    ]


def test_challenge_two_focus_keys_alternate(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=3,
        focus_keys=("ideas", "evidence"),
        title="Focus Two",
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        for turn_no in (1, 2, 3):
            detail = _respond(client, challenge_id, turn_no).json()

    assert [turn["focus_key"] for turn in detail["turns"]] == [
        "ideas",
        "evidence",
        "ideas",
    ]


def test_challenge_requires_a_long_enough_draft(education_client):
    """空白页上来就被问三个问题只会让学生关掉页面，正文太短直接拒。"""

    client, teacher, _, student, _, _ = education_client

    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": "CR Short"}).json()[
        "classroom"
    ]
    UserContext.current_user = student
    client.post(
        "/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]}
    )

    UserContext.current_user = teacher
    assignment = client.post(
        "/api/v1/assignments",
        json={
            "title": "Short Draft",
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": 100,
            "rubric_schema": _rubric_schema(100),
            "challenge_enabled": True,
            "challenge_rounds": 2,
            "challenge_focus_keys": ["ideas"],
        },
    ).json()[0]

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    session_id = workspace["writing_session"]["id"]
    client.post(
        f"/api/v1/writing-sessions/{session_id}/versions",
        json={"trigger_type": "autosave", "content_text": "太短了"},
    )

    with _fake_challenge_model():
        res = _start_challenge(client, assignment["id"], session_id)
    assert res.status_code == 400, res.text


def test_challenge_start_rejected_when_assignment_has_it_off(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, _ = _setup_submitted_assignment(
        client, teacher, student, "No Challenge"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        res = _start_challenge(client, assignment["id"], session_id)
    assert res.status_code == 400, res.text


def test_challenge_can_be_skipped_and_teacher_sees_it(education_client):
    """允许跳过，但跳过留痕。强制不可跳过只会逼出敷衍答案。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Skip Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]

    skip_res = client.post(f"/api/v1/challenge/{challenge_id}/skip")
    assert skip_res.status_code == 200, skip_res.text
    assert skip_res.json()["session"]["status"] == "skipped"
    # 已结束的质疑不能再跳一次
    assert client.post(f"/api/v1/challenge/{challenge_id}/skip").status_code == 400

    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    )
    assert submit_res.status_code == 200, submit_res.text
    submission_id = submit_res.json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    frozen = detail["submission"]["stats_json"]["challenge"]
    assert frozen["status"] == "skipped"
    assert frozen["answered_rounds"] == 0

    rounds_res = client.get(f"/api/v1/submissions/{submission_id}/challenge")
    assert rounds_res.status_code == 200, rounds_res.text
    assert rounds_res.json()["session"]["status"] == "skipped"


def test_challenge_rounds_are_visible_to_the_teacher_after_submit(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Teacher View"
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={
            "stood": ["你说清了论点"],
            "unresolved": [{"text": "还缺一个反例", "turn_no": 2}],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1, "我补了一份调查数据。")
        _respond(client, challenge_id, 2, "我承认这里还缺一个反例。")

    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    )
    assert submit_res.status_code == 200, submit_res.text
    submission_id = submit_res.json()["submission_id"]

    UserContext.current_user = teacher
    rounds = client.get(f"/api/v1/submissions/{submission_id}/challenge").json()
    assert rounds["session"]["status"] == "completed"
    assert len(rounds["turns"]) == 2
    assert rounds["turns"][0]["response_text"] == "我补了一份调查数据。"
    assert [
        item["text"] for item in rounds["session"]["closing_summary_json"]["unresolved"]
    ] == ["还缺一个反例"]


def test_submission_without_challenge_records_absence(education_client):
    """没开质疑的作业，提交流程一切照旧。"""

    client, teacher, _, student, _, _ = education_client
    _assignment, _session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Plain Essay"
    )

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    challenge = detail["submission"]["stats_json"]["challenge"]
    assert challenge["enabled"] is False
    assert challenge["status"] is None
    assert client.get(f"/api/v1/submissions/{submission_id}/challenge").json() is None


def test_submission_freezes_the_challenge_wording_in_force(education_client):
    """管理员随时可改质疑措辞，已交那一轮的记录不能跟着变。"""

    client, teacher, _, student, _, _ = education_client
    asyncio.run(
        Config.upsert(
            {
                "education.challenge_prompts": {
                    "turn": "你是一个不同意作者观点的读者。原始措辞。",
                    "closing": '收尾，输出 {"stood": [], "unresolved": []}。',
                }
            }
        )
    )
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Frozen Wording"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    frozen = detail["submission"]["stats_json"]["challenge"]
    assert "原始措辞" in frozen["turn_prompt"]
    assert frozen["answered_rounds"] == 2

    asyncio.run(
        Config.upsert(
            {
                "education.challenge_prompts": {
                    "turn": "改过的新说法。",
                    "closing": "改过的收尾说法。",
                }
            }
        )
    )

    detail = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    assert (
        detail["submission"]["stats_json"]["challenge"]["turn_prompt"]
        == frozen["turn_prompt"]
    )


def test_challenge_config_must_reference_rubric_criteria(education_client):
    """未配置评分维度的作业不允许启用质疑，焦点必须是本作业已有的维度。"""

    client, teacher, _, _student, _, _ = education_client

    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": "CR Config"}).json()[
        "classroom"
    ]

    unknown_focus = client.post(
        "/api/v1/assignments",
        json={
            "title": "Bad Focus",
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": 100,
            "rubric_schema": _rubric_schema(100),
            "challenge_enabled": True,
            "challenge_rounds": 3,
            "challenge_focus_keys": ["not_a_criterion"],
        },
    )
    assert unknown_focus.status_code == 422, unknown_focus.text

    empty_focus = client.post(
        "/api/v1/assignments",
        json={
            "title": "No Focus",
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": 100,
            "rubric_schema": _rubric_schema(100),
            "challenge_enabled": True,
            "challenge_rounds": 3,
            "challenge_focus_keys": [],
        },
    )
    assert empty_focus.status_code == 422, empty_focus.text

    bad_rounds = client.post(
        "/api/v1/assignments",
        json={
            "title": "Bad Rounds",
            "classroom_ids": [classroom["id"]],
            "due_at": 2000000000,
            "score_max": 100,
            "rubric_schema": _rubric_schema(100),
            "challenge_enabled": True,
            "challenge_rounds": 5,
            "challenge_focus_keys": ["ideas"],
        },
    )
    assert bad_rounds.status_code == 422, bad_rounds.text


def test_challenge_current_restores_unfinished_session(education_client):
    """刷新页面不该把已经答过的回合弄丢。"""

    client, teacher, _, student, outsider, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=3, title="Resume Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)

    current = client.get(
        f"/api/v1/assignments/{assignment['id']}/challenge/current",
        params={"writing_session_id": session_id},
    )
    assert current.status_code == 200, current.text
    payload = current.json()
    assert payload["session"]["id"] == challenge_id
    assert len(payload["turns"]) == 2
    assert payload["turns"][0]["response_text"] is not None
    assert payload["turns"][1]["response_text"] is None

    # 一轮只质疑一次，重复 start 要被拒
    with _fake_challenge_model():
        assert _start_challenge(client, assignment["id"], session_id).status_code == 400

    # 别人的质疑读不到也答不了
    UserContext.current_user = outsider
    assert client.post(f"/api/v1/challenge/{challenge_id}/skip").status_code == 403
    with _fake_challenge_model():
        assert _respond(client, challenge_id, 2).status_code == 403


def test_challenge_checklist_state_persists(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Checklist Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={
            "stood": [],
            "unresolved": [
                {"text": "补一个反例", "turn_no": 1},
                {"text": "说明数据来源", "turn_no": 2},
            ],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    res = client.patch(
        f"/api/v1/challenge/{challenge_id}/checklist",
        json={"checked_indexes": [1, 1, 0]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["session"]["checklist_state_json"] == {"checked_indexes": [0, 1]}

    current = client.get(
        f"/api/v1/assignments/{assignment['id']}/challenge/current",
        params={"writing_session_id": session_id},
    ).json()
    assert current["session"]["checklist_state_json"]["checked_indexes"] == [0, 1]


def test_teacher_sees_whether_the_student_revised_after_the_read_through(education_client):
    """被问住之后到底改没改。判的是被质疑的那一句，不是全文改了多少字。

    这里只把第一句里的两个词换掉——字数上微不足道，却正是被质疑之后最理想的修改。
    老口径（全文改动量过 20 字）会把它判成没改。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Revised Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={"stood": [], "unresolved": [{"text": "还缺一个反例", "turn_no": 1}]}
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    # 第一轮质疑引用的就是第一句。只改这句里的两个词。
    revised_text = _long_draft().replace(
        "短视频降低了年轻人的注意力", "短视频可能削弱了部分人的注意力"
    )
    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, revised_text),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    rounds = client.get(f"/api/v1/submissions/{submission_id}/challenge").json()
    revision = rounds["revision"]
    assert revision["revised"] is True
    assert revision["changed_spans"] == 1
    assert revision["total_spans"] == 2

    first, second = revision["turns"]
    assert first["changed"] is True
    # 三栏里的第三栏：这句在最终稿里成了什么样。
    assert "短视频可能削弱了部分人的注意力" in first["final_span"]
    assert second["changed"] is False

    frozen = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    assert frozen["submission"]["stats_json"]["challenge"]["revision"]["revised"] is True


def test_teacher_sees_when_the_student_changed_nothing(education_client):
    """在结尾堆一段与质疑无关的话，被质疑的那几句一字未动 —— 判定必须是「未修改」。

    这是老口径最容易被糊弄的地方：全文改动量轻松过 20 字，于是判成「改了」。
    新口径只看被质疑的那几句在不在。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Untouched Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    padding = (
        "总而言之，这个话题值得我们每一个人认真地思考和反复地体会，"
        "并且在今后的日常生活当中持续地加以关注，不能掉以轻心。"
    )
    assert len(padding) >= 50
    padded = _long_draft() + padding

    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, padded),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    rounds = client.get(f"/api/v1/submissions/{submission_id}/challenge").json()
    revision = rounds["revision"]
    assert revision["revised"] is False
    assert revision["changed_spans"] == 0
    assert revision["total_spans"] == 2
    assert all(turn["changed"] is False for turn in revision["turns"])


def test_challenge_skipped_on_the_contract_page_is_recorded(education_client):
    """连「开始」都没点就跳过，同样要留痕。

    这是这个环节最有教学意义的信号之一——系统性回避质疑的学生正是最该被教师看到的
    那批。不落库的话，他们反而是唯一在质疑维度上完全空白的。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Never Started Essay"
    )

    UserContext.current_user = student
    # 没有 _start_challenge：模拟学生在契约页直接点跳过。
    skip_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/challenge/skip",
        json={"writing_session_id": session_id},
    )
    assert skip_res.status_code == 200, skip_res.text
    assert skip_res.json()["session"]["status"] == "skipped"
    assert skip_res.json()["turns"] == []

    # 已经落过一条就不许再落，避免重复点击写出两条。
    assert (
        client.post(
            f"/api/v1/assignments/{assignment['id']}/challenge/skip",
            json={"writing_session_id": session_id},
        ).status_code
        == 400
    )

    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    frozen = client.get(f"/api/v1/teacher/submissions/{submission_id}").json()
    assert frozen["submission"]["stats_json"]["challenge"]["status"] == "skipped"
    rounds = client.get(f"/api/v1/submissions/{submission_id}/challenge").json()
    assert rounds["session"]["status"] == "skipped"


def test_challenge_turn_records_the_quoted_sentence(education_client):
    """每一轮都要引用原文里的一句，并且存下来的是原文那一版。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Quoted Essay"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        detail = _start_challenge(client, assignment["id"], session_id).json()
        challenge_id = detail["session"]["id"]
        detail = _respond(client, challenge_id, 1).json()

    draft = _long_draft()
    for turn in detail["turns"]:
        assert turn["quoted_span"]
        assert turn["quoted_span"] in draft


def test_challenge_retries_once_when_the_quote_cannot_be_located(education_client):
    """引用锚不回原文就是生成失败，重试一次，再失败直接拒。

    刻意不做「拿整段输出当质疑、片段留空」的降级：留空的片段会让这一轮永远判不出
    改没改，等于把坏数据写进证据链。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Bad Quote Essay"
    )

    UserContext.current_user = student

    # 第一次不是 JSON，第二次引用的是正文里没有的句子 —— 两次都失败。
    bad = ['我觉得你这里说不通。', '{"quote": "这句话原文里根本没有出现过", "challenge": "说不通"}']
    with _fake_challenge_model(raw_turns=bad) as calls:
        res = _start_challenge(client, assignment["id"], session_id)
    assert res.status_code == 400, res.text
    assert len(calls) == 2

    # 第一次坏、第二次好 —— 重试救回来。
    good = ['不是 JSON', json.dumps(
        {"quote": _DRAFT_SENTENCES[0], "challenge": "这一句说服不了我"},
        ensure_ascii=False,
    )]
    with _fake_challenge_model(raw_turns=good) as calls:
        res = _start_challenge(client, assignment["id"], session_id)
    assert res.status_code == 200, res.text
    assert len(calls) == 2
    assert res.json()["turns"][0]["quoted_span"] == _DRAFT_SENTENCES[0]


def test_closing_items_carry_their_focus_dimension(education_client):
    """收尾条目按轮次映射到维度。轮次报错或不报就留空，不硬塞给某个维度。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=2,
        focus_keys=("ideas", "evidence"),
        title="Focus Attribution",
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={
            "stood": [],
            "unresolved": [
                {"text": "第一轮那条还不成立", "turn_no": 1},
                {"text": "第二轮那条也不成立", "turn_no": 2},
                # 轮次超出范围：模型瞎报，服务端不接受。
                {"text": "来路不明的一条", "turn_no": 9},
                # 干脆不是对象：模型没按格式输出。
                "连格式都没按",
            ],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        detail = _respond(client, challenge_id, 2).json()

    unresolved = detail["session"]["closing_summary_json"]["unresolved"]
    # 四条都要留给学生看，一条都不能因为归属不上就被丢掉。
    assert [item["text"] for item in unresolved] == [
        "第一轮那条还不成立",
        "第二轮那条也不成立",
        "来路不明的一条",
        "连格式都没按",
    ]
    assert unresolved[0]["focus_key"] == "ideas"
    assert unresolved[1]["focus_key"] == "evidence"
    assert unresolved[2]["focus_key"] is None
    assert unresolved[3]["focus_key"] is None


def test_dashboard_reports_challenge_hit_rate_per_criterion(education_client):
    """看板按维度给出命中率：被质疑几人、几人没答住、其中几人一字未动。

    来源占比回答「他用了多少 AI」，这一项回答「这个班普遍在哪个维度上站不住」，
    是第一个班级层面的学习指标而不是监控指标。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=2,
        focus_keys=("ideas", "evidence"),
        title="Distribution Essay",
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={
            "stood": [],
            "unresolved": [
                {"text": "立意这条还不成立", "turn_no": 1},
                {"text": "证据这条也不成立", "turn_no": 2},
            ],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    # 只改第一轮质疑的那一句（第一句），第二轮那句原样不动。
    revised = _long_draft().replace(
        "短视频降低了年轻人的注意力", "短视频可能削弱了部分人的注意力"
    )
    client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, revised),
    )

    UserContext.current_user = teacher
    dashboard = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    ).json()
    distribution = dashboard["distributions"]["challenge"]

    assert distribution["completed_students"] == 1
    assert distribution["skipped_students"] == 0
    # 一个人的样本不该被当成班级结论。
    assert distribution["below_sample_threshold"] is True

    by_key = {row["focus_key"]: row for row in distribution["criteria"]}
    assert by_key["ideas"]["challenged"] == 1
    assert by_key["ideas"]["unresolved"] == 1
    # 立意这句改了 —— 没答住但动了笔。
    assert by_key["ideas"]["unresolved_unchanged"] == 0
    assert by_key["evidence"]["challenged"] == 1
    assert by_key["evidence"]["unresolved"] == 1
    # 证据这句一字未动 —— 这才是教师最该讲的那种。
    assert by_key["evidence"]["unresolved_unchanged"] == 1


def test_dashboard_omits_challenge_block_when_nobody_was_challenged(education_client):
    """没人做过质疑就不出这一块，不摆空状态占位。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Nobody Challenged"
    )

    # 既没发起也没跳过就直接交。
    UserContext.current_user = student
    client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    )

    UserContext.current_user = teacher
    dashboard = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    ).json()
    assert "challenge" not in dashboard["distributions"]


def test_return_comment_drives_the_next_challenge(education_client):
    """教师退回时勾了追问，下一轮质疑就围绕那条意见展开。

    这是产品里第一处 AI 直接执行教师教学意图、而不是执行配置预设的交互。此前退回
    意见写完就没下文：学生看不看、改不改全凭自觉，教师没有任何抓手。
    """

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Followup Essay"
    )

    # 第一轮：学生跳过质疑直接交。
    UserContext.current_user = student
    client.post(
        f"/api/v1/assignments/{assignment['id']}/challenge/skip",
        json={"writing_session_id": session_id},
    )
    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    # 教师退回，并要求就这条意见追问。
    UserContext.current_user = teacher
    comment = "你说所有人都认为长视频没人看了，凭什么这么说？"
    review_res = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": comment,
            "resubmit_due_at": 2000000000,
            "challenge_followup": True,
        },
    )
    assert review_res.status_code == 200, review_res.text
    assert review_res.json()["challenge_followup"] is True

    # 学生重交前发起质疑：教师那句话要进模型的输入，并冻进本轮记录。
    UserContext.current_user = student
    with _fake_challenge_model() as calls:
        detail = _start_challenge(client, assignment["id"], session_id).json()

    assert detail["session"]["followup_comment"] == comment
    assert comment in calls[0]["messages"][1]["content"]


def test_challenge_followup_needs_a_returned_comment(education_client):
    """勾了追问但没退回、或没写意见，直接拒——没有内容可追问时不该硬造一轮。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Followup Guard"
    )

    UserContext.current_user = student
    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    # 退回了但没写意见。
    assert (
        client.post(
            f"/api/v1/teacher/submissions/{submission_id}/review",
            json={
                "review_status": "returned",
                "returned_comment": "   ",
                "resubmit_due_at": 2000000000,
                "challenge_followup": True,
            },
        ).status_code
        == 400
    )
    # 根本不是退回。
    assert (
        client.post(
            f"/api/v1/teacher/submissions/{submission_id}/review",
            json={
                "review_status": "pending",
                "returned_comment": "改一下这里",
                "challenge_followup": True,
            },
        ).status_code
        == 400
    )


def test_challenge_followup_rejected_when_assignment_has_challenge_off(education_client):
    """未启用质疑的作业不接受这个勾选——不在这里替教师悄悄打开那个环节。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Followup Off"
    )

    UserContext.current_user = teacher
    disabled = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"challenge_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text

    UserContext.current_user = student
    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    UserContext.current_user = teacher
    res = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "再补一个反例",
            "resubmit_due_at": 2000000000,
            "challenge_followup": True,
        },
    )
    assert res.status_code == 400, res.text


def _complete_challenge_and_submit(client, assignment, session_id, unresolved_text):
    """跑完一轮质疑并提交，留下一条指定文本的未解决点。"""

    with _fake_challenge_model(
        closing={
            "stood": [],
            "unresolved": [{"text": unresolved_text, "turn_no": 1}],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    return client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    )


def test_challenge_insight_refuses_below_the_sample_threshold(education_client):
    """样本不足时明说还差几人，不勉强归纳 —— 少数几条文本归纳出的类型是噪声。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Thin Sample"
    )

    UserContext.current_user = student
    _complete_challenge_and_submit(client, assignment, session_id, "论据还不够")

    UserContext.current_user = teacher
    with _fake_challenge_model() as calls:
        res = client.post(
            f"/api/v1/teacher/assignments/{assignment['id']}/challenge-insight",
            json={"model": "test-model"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["below_threshold"] is True
    assert body["sample_size"] == 1
    assert body["categories"] == []
    # 样本不足时一次模型都不能调。
    assert calls == []


def test_challenge_insight_payload_carries_no_student_identity(education_client):
    """送进模型的载荷里不能有姓名、学号、提交 id —— 这份东西要摆到课堂上讲。"""

    client, teacher, _, students, _, _ = education_client
    assignment, first_session = _setup_challenge_assignment(
        client, teacher, students, rounds=2, title="Redaction Check"
    )

    UserContext.current_user = students
    submit_res = _complete_challenge_and_submit(
        client, assignment, first_session, "以个例代替普遍规律"
    )
    submission_id = submit_res.json()["submission_id"]

    UserContext.current_user = teacher
    insight_payload = {
        "categories": [
            {
                "name": "以个例代替普遍规律",
                "hits": 1,
                "samples": ["以个例代替普遍规律"],
                "advice": "讲清样本量和结论强度的关系。",
            }
        ]
    }
    with _fake_challenge_model(
        raw_turns=[json.dumps(insight_payload, ensure_ascii=False)]
    ) as calls:
        # 门槛在服务层，这里直接调服务把它绕开，专测脱敏。
        from open_webui.services.education import challenge_insight as insight_module

        original = insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS
        insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS = 1
        try:
            res = client.post(
                f"/api/v1/teacher/assignments/{assignment['id']}/challenge-insight",
                json={"model": "test-model"},
            )
        finally:
            insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS = original

    assert res.status_code == 200, res.text
    assert len(calls) == 1
    sent = calls[0]["messages"][1]["content"]
    assert "以个例代替普遍规律" in sent
    # 载荷里只有维度名和条目文本。
    assert students.name not in sent
    assert students.id not in sent
    assert students.email not in sent
    assert submission_id not in sent
    assert first_session not in sent

    body = res.json()
    assert body["categories"][0]["name"] == "以个例代替普遍规律"
    assert body["categories"][0]["hits"] == 1


def test_challenge_insight_is_cached_until_the_input_changes(education_client):
    """输入哈希不变就不重算 —— 不缓存的话教师每刷一次看板烧一次调用。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Cached Insight"
    )

    UserContext.current_user = student
    _complete_challenge_and_submit(client, assignment, session_id, "论据还不够")

    UserContext.current_user = teacher
    from open_webui.services.education import challenge_insight as insight_module

    original = insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS
    insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS = 1
    payload = json.dumps(
        {"categories": [{"name": "论据不足", "hits": 1, "samples": [], "advice": "讲证据。"}]},
        ensure_ascii=False,
    )
    try:
        with _fake_challenge_model(raw_turns=[payload]) as first_calls:
            first = client.post(
                f"/api/v1/teacher/assignments/{assignment['id']}/challenge-insight",
                json={"model": "test-model"},
            ).json()
        with _fake_challenge_model(raw_turns=[payload]) as second_calls:
            second = client.post(
                f"/api/v1/teacher/assignments/{assignment['id']}/challenge-insight",
                json={"model": "test-model"},
            ).json()
    finally:
        insight_module.CHALLENGE_INSIGHT_MIN_STUDENTS = original

    assert len(first_calls) == 1
    # 第二次全靠缓存，一次模型都不调。
    assert second_calls == []
    assert second["categories"] == first["categories"]
    assert second["generated_at"] == first["generated_at"]


_CRITIQUE_TEXT = (
    "所有人都认为短视频毁掉了这一代人的专注力。"
    "我表弟每天刷五个小时，成绩一落千丈，可见这个结论是成立的。"
)
_CRITIQUE_FLAWS = [
    {
        "key": "overgeneralized",
        "description": "用「所有人都认为」代替论证，没有给出依据。",
        "focus_key": "ideas",
    },
    {
        "key": "single-case",
        "description": "只用表弟一个例子就推出普遍结论。",
        "focus_key": "evidence",
    },
]


def _enable_critique(client, assignment_id):
    return client.patch(
        f"/api/v1/assignments/{assignment_id}",
        json={
            "critique_enabled": True,
            "critique_text": _CRITIQUE_TEXT,
            "critique_flaws": _CRITIQUE_FLAWS,
        },
    )


def test_critique_gate_records_hits_without_scoring(education_client):
    """写作前评析：只报命中，不给分、不给等级，找出一条也放行。"""

    client, teacher, _, student, _, _ = education_client
    assignment, _ = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=2,
        focus_keys=("ideas", "evidence"),
        title="Critique Essay",
    )

    UserContext.current_user = teacher
    enabled = _enable_critique(client, assignment["id"])
    assert enabled.status_code == 200, enabled.text

    UserContext.current_user = student
    state = client.get(f"/api/v1/assignments/{assignment['id']}/critique").json()
    assert state["enabled"] is True
    assert state["completed"] is False
    assert _CRITIQUE_TEXT in state["text"]

    with _fake_challenge_model(
        raw_turns=[json.dumps({"hits": ["single-case"]}, ensure_ascii=False)]
    ):
        # 只写一条也放行 —— 不设及格线。
        res = client.post(
            f"/api/v1/assignments/{assignment['id']}/critique",
            json={"items": ["只举了表弟一个例子"], "model": "test-model"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["completed"] is True

    matches = {match["key"]: match for match in body["attempt"]["matches_json"]}
    assert matches["single-case"]["hit"] is True
    assert matches["overgeneralized"]["hit"] is False
    # 不给分、不给等级：载荷里不该出现任何分数字段。
    assert "score" not in body["attempt"]
    assert "grade" not in body["attempt"]

    # 一次作业至多一条，重复提交直接拒。
    assert (
        client.post(
            f"/api/v1/assignments/{assignment['id']}/critique",
            json={"items": ["再来一次"], "model": "test-model"},
        ).status_code
        == 400
    )


def test_critique_needs_rubric_criteria_and_a_target_text(education_client):
    """未配评分维度、没有靶文、或一条漏洞都没预设，都不允许启用。"""

    client, teacher, _, student, _, _ = education_client
    assignment, _ = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Critique Guard"
    )

    UserContext.current_user = teacher
    # 开了但没靶文。
    assert (
        client.patch(
            f"/api/v1/assignments/{assignment['id']}",
            json={"critique_enabled": True, "critique_text": "  ", "critique_flaws": []},
        ).status_code
        in (400, 422)
    )
    # 有靶文但一条漏洞都没预设 —— 没有标准答案就无从判定。
    assert (
        client.patch(
            f"/api/v1/assignments/{assignment['id']}",
            json={
                "critique_enabled": True,
                "critique_text": _CRITIQUE_TEXT,
                "critique_flaws": [],
            },
        ).status_code
        in (400, 422)
    )
    # 漏洞绑到了不存在的维度。
    assert (
        client.patch(
            f"/api/v1/assignments/{assignment['id']}",
            json={
                "critique_enabled": True,
                "critique_text": _CRITIQUE_TEXT,
                "critique_flaws": [
                    {"key": "x", "description": "问题", "focus_key": "no-such-key"}
                ],
            },
        ).status_code
        in (400, 422)
    )


def test_critique_judgement_failure_does_not_block_writing(education_client):
    """模型抽风判不出来，也不能把学生挡在写作区外面 —— 这道门拦在写作之前。"""

    client, teacher, _, student, _, _ = education_client
    assignment, _ = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=2,
        focus_keys=("ideas", "evidence"),
        title="Critique Resilient",
    )

    UserContext.current_user = teacher
    _enable_critique(client, assignment["id"])

    UserContext.current_user = student
    with _fake_challenge_model(raw_turns=["这根本不是 JSON"]):
        res = client.post(
            f"/api/v1/assignments/{assignment['id']}/critique",
            json={"items": ["只举了一个例子"], "model": "test-model"},
        )
    assert res.status_code == 200, res.text
    # 判不出来记为待判定（空命中表），不等同于「一条都没找到」。
    assert res.json()["completed"] is True
    assert res.json()["attempt"]["matches_json"] == []


def test_dashboard_shows_critique_hits_per_criterion(education_client):
    """写前认得出这个毛病的人次，和质疑命中率并进同一张按维度的表。"""

    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=2,
        focus_keys=("ideas", "evidence"),
        title="Critique Dashboard",
    )

    UserContext.current_user = teacher
    _enable_critique(client, assignment["id"])

    UserContext.current_user = student
    with _fake_challenge_model(
        raw_turns=[json.dumps({"hits": ["single-case"]}, ensure_ascii=False)]
    ):
        client.post(
            f"/api/v1/assignments/{assignment['id']}/critique",
            json={"items": ["只举了表弟一个例子"], "model": "test-model"},
        )

    with _fake_challenge_model(
        closing={"stood": [], "unresolved": [{"text": "证据不足", "turn_no": 2}]}
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    )

    UserContext.current_user = teacher
    dashboard = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/dashboard"
    ).json()
    by_key = {
        row["focus_key"]: row
        for row in dashboard["distributions"]["challenge"]["criteria"]
    }
    # 证据这一维：写前看出来了，写自己的时候仍然被问住 —— 正是这两个环节的对照。
    assert by_key["evidence"]["critique_hits"] == 1
    assert by_key["evidence"]["critique_total"] == 1
    assert by_key["evidence"]["unresolved"] == 1
    # 立意这一维：写前没看出来。
    assert by_key["ideas"]["critique_hits"] == 0
    assert by_key["ideas"]["critique_total"] == 1


def test_challenge_config_survives_assignment_update(education_client):
    """教师改作业时三个字段要跟着走，关掉质疑要把焦点一并清空。"""

    client, teacher, _, student, _, _ = education_client
    assignment, _ = _setup_challenge_assignment(
        client,
        teacher,
        student,
        rounds=3,
        focus_keys=("ideas", "evidence"),
        title="Config Update",
    )

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/assignments/{assignment['id']}").json()
    assert detail["assignment"]["challenge_enabled"] is True
    assert detail["assignment"]["challenge_rounds"] == 3
    assert detail["assignment"]["challenge_focus_keys"] == ["ideas", "evidence"]

    updated = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"challenge_rounds": 2, "challenge_focus_keys": ["structure"]},
    )
    assert updated.status_code == 200, updated.text
    detail = client.get(f"/api/v1/teacher/assignments/{assignment['id']}").json()
    assert detail["assignment"]["challenge_rounds"] == 2
    assert detail["assignment"]["challenge_focus_keys"] == ["structure"]

    # 关掉质疑，焦点必须一起清掉，免得下次开启时带着过期的维度
    disabled = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"challenge_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    detail = client.get(f"/api/v1/teacher/assignments/{assignment['id']}").json()
    assert detail["assignment"]["challenge_enabled"] is False
    assert detail["assignment"]["challenge_focus_keys"] == []

    # 评分维度里没有的 key 一律拒绝
    rejected = client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"challenge_enabled": True, "challenge_focus_keys": ["not_a_criterion"]},
    )
    assert rejected.status_code in (400, 422), rejected.text


def test_challenge_facts_reach_the_growth_profile(education_client):
    """质疑事实进画像，且只走 stats_json（画像不回读 challenge 原表）。"""

    client, teacher, _, student, _, SessionLocal = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Profile Challenge"
    )

    UserContext.current_user = student
    with _fake_challenge_model(
        closing={
            "stood": ["论点清楚"],
            "unresolved": [
                {"text": "还缺一个反例", "turn_no": 1},
                {"text": "数据来源没说", "turn_no": 2},
            ],
        }
    ):
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
        _respond(client, challenge_id, 1)
        _respond(client, challenge_id, 2)

    # 第二轮质疑引用的是第二句，把那句里的绝对化表述限缩掉。
    revised_text = _long_draft().replace(
        "所有人都认为长视频已经没人看了", "我采访的 12 个同学里有 9 个说很少看长视频"
    )
    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, revised_text),
    ).json()["submission_id"]

    with SessionLocal() as session:
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .one()
        )
        challenge = evidence.evidence_json["challenge"]
        assert challenge["enabled"] is True
        assert challenge["status"] == "completed"
        assert challenge["planned_rounds"] == 2
        assert challenge["answered_rounds"] == 2
        assert challenge["unresolved_count"] == 2
        assert challenge["revised_after"] is True
        assert challenge["changed_spans"] >= 1
        assert challenge["total_spans"] == 2

        projection = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.evidence_snapshot_id == evidence.id)
            .one()
        )
        point = projection.projection_json["point"]
        assert point["challenge_status"] == "completed"
        assert point["challenge_answer_ratio"] == 100
        assert point["challenge_unresolved_count"] == 2
        assert point["challenge_revised"] is True


def test_profile_marks_challenge_as_not_applicable_when_disabled(education_client):
    """没开试读的作业，画像里这几项是 None——「不适用」不能被读成「表现差」。"""

    client, teacher, _, student, _, SessionLocal = education_client
    _assignment, _session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "No Challenge Profile"
    )

    with SessionLocal() as session:
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .one()
        )
        assert evidence.evidence_json["challenge"]["enabled"] is False

        projection = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.evidence_snapshot_id == evidence.id)
            .one()
        )
        point = projection.projection_json["point"]
        assert point["challenge_status"] is None
        assert point["challenge_answer_ratio"] is None
        assert point["challenge_unresolved_count"] is None
        assert point["challenge_revised"] is None


def test_skipped_challenge_reaches_profile_without_answer_ratio(education_client):
    """跳过要如实进画像，但不给回应率——没答过就没有这个数，不是 0%。"""

    client, teacher, _, student, _, SessionLocal = education_client
    assignment, session_id = _setup_challenge_assignment(
        client, teacher, student, rounds=2, title="Skipped Profile"
    )

    UserContext.current_user = student
    with _fake_challenge_model():
        challenge_id = _start_challenge(client, assignment["id"], session_id).json()[
            "session"
        ]["id"]
    client.post(f"/api/v1/challenge/{challenge_id}/skip")

    submission_id = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, _long_draft()),
    ).json()["submission_id"]

    with SessionLocal() as session:
        evidence = (
            session.query(ProfileEvidenceSnapshot)
            .filter(ProfileEvidenceSnapshot.submission_id == submission_id)
            .one()
        )
        assert evidence.evidence_json["challenge"]["status"] == "skipped"

        projection = (
            session.query(ProfileMetricProjection)
            .filter(ProfileMetricProjection.evidence_snapshot_id == evidence.id)
            .one()
        )
        point = projection.projection_json["point"]
        assert point["challenge_status"] == "skipped"
        assert point["challenge_answer_ratio"] is None
        assert point["challenge_revised"] is None
