"""Visibility preserves evidence while closing student entry points."""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.models.education import Education
from open_webui.models.chats import Chats, ChatForm
from open_webui.models.config import Config
from open_webui.routers.folders import router as folders_router
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    education_client,
    _setup_submitted_assignment,
    _rubric_schema,
)


def test_hide_and_restore_submitted_assignment(education_client):
    client, teacher, other_teacher, student, _, SessionLocal = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(client, teacher, student)
    assignment_id = assignment['id']
    visibility_url = f'/api/v1/assignments/{assignment_id}/visibility'

    # Students and unrelated teachers cannot change visibility.
    for actor in (student, other_teacher):
        UserContext.current_user = actor
        assert client.patch(visibility_url, json={'hidden': True}).status_code == 403

    UserContext.current_user = teacher
    assert client.delete(f'/api/v1/assignments/{assignment_id}').status_code == 400
    hidden = client.patch(visibility_url, json={'hidden': True})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()['hidden'] is True
    assert hidden.json()['config_revision'] == assignment['config_revision']
    assert hidden.json()['change_summary'] == assignment['change_summary']
    listed = client.get('/api/v1/teacher/assignments').json()
    assert next(item for item in listed if item['assignment']['id'] == assignment_id)['assignment']['hidden']
    assert client.get(f'/api/v1/teacher/assignments/{assignment_id}').status_code == 200
    assert client.get(f'/api/v1/teacher/submissions/{submission_id}').status_code == 200

    UserContext.current_user = student
    home = client.get('/api/v1/me/writing/home').json()
    assert home['assignment_items'] == []
    assert home['recent_items'] == []
    assert client.get('/api/v1/me/writing/workspaces').json() == []
    assert client.get('/api/v1/me/writing/assignments').json() == []
    assert assignment_id not in client.get('/api/v1/me/notifications/summary').json()['by_assignment']
    profile = client.get('/api/v1/me/writing/profile')
    assert profile.status_code == 200, profile.text
    assert assignment_id not in profile.text
    for url in (
        f'/api/v1/assignments/{assignment_id}/workspace',
        f'/api/v1/assignments/{assignment_id}/me/submissions',
        f'/api/v1/writing/{session_id}/workspace',
        f'/api/v1/writing/{session_id}/process-summary',
    ):
        assert client.get(url).status_code == 403, url
    assert client.post(f'/api/v1/writing-sessions/{session_id}/versions', json={
        'trigger_type': 'autosave', 'content_text': 'blocked edit', 'content_json': None,
    }).status_code == 403

    with SessionLocal() as db:
        session = Education.get_writing_session_by_id(session_id, db=db)
        submission = Education.get_submission_by_id(submission_id, db=db)
        assert session.submitted_submission_id == submission.id
        final_version_id = submission.final_version_id

    UserContext.current_user = teacher
    assert client.patch(visibility_url, json={'hidden': False}).status_code == 200
    UserContext.current_user = student
    workspace = client.get(f'/api/v1/assignments/{assignment_id}/workspace')
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()['writing_session']['id'] == session_id
    assert len(client.get('/api/v1/me/writing/home').json()['assignment_items']) == 1
    assert client.get('/api/v1/me/writing/profile').status_code == 200
    with SessionLocal() as db:
        assert Education.get_submission_by_id(submission_id, db=db).final_version_id == final_version_id


@pytest.mark.parametrize('payload', [{'hidden': 'true'}, {'hidden': 1}, {}, {'hidden': True, 'status': 'archived'}])
def test_visibility_requires_strict_boolean(education_client, payload):
    client, teacher, _, student, _, _ = education_client
    assignment, _, _ = _setup_submitted_assignment(client, teacher, student)
    UserContext.current_user = teacher
    assert client.patch(f'/api/v1/assignments/{assignment["id"]}/visibility', json=payload).status_code == 422


def test_hidden_assignment_cannot_be_started(education_client):
    client, teacher, _, student, _, _ = education_client
    UserContext.current_user = teacher
    classroom = client.post('/api/v1/classrooms', json={'name': '大学写作课程'}).json()['classroom']
    assignment = client.post('/api/v1/assignments', json={
        'title': '课程论证', 'classroom_ids': [classroom['id']], 'score_max': 100,
        'rubric_schema': _rubric_schema(), 'due_at': 2000000000,
    }).json()[0]
    assert assignment['hidden'] is False
    assert client.patch(f'/api/v1/assignments/{assignment["id"]}/visibility', json={'hidden': True}).status_code == 200
    UserContext.current_user = student
    assert client.post('/api/v1/classrooms/join', json={'invite_code': classroom['invite_code']}).status_code == 200
    assert client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').status_code == 403


def test_hidden_assignment_project_and_chat_are_unavailable(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    client.app.include_router(folders_router, prefix='/api/v1/folders')
    assignment, session_id, _ = _setup_submitted_assignment(client, teacher, student)
    with SessionLocal() as db:
        session = Education.get_writing_session_by_id(session_id, db=db)
    asyncio.run(Config.upsert({'folders.enable': True, 'user.permissions': {'features': {'folders': True}}}))
    asyncio.run(Chats.insert_new_chat('visibility-chat', student.id, ChatForm(
        chat={'title': 'Assignment conversation'}, folder_id=session.folder_id,
    )))
    UserContext.current_user = teacher
    assert client.patch(f'/api/v1/assignments/{assignment["id"]}/visibility', json={'hidden': True}).status_code == 200
    UserContext.current_user = student
    folders = client.get('/api/v1/folders/')
    assert folders.status_code == 200, folders.text
    assert session.folder_id not in folders.text
    assert client.get(f'/api/v1/folders/{session.folder_id}').status_code == 403
    assert client.get('/api/v1/chats/visibility-chat').status_code == 403
    assert client.post('/api/v1/chats/visibility-chat', json={'chat': {'title': 'Changed'}}).status_code == 403
