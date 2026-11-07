"""Single revision conversation and explicit consolidation, on real migrated test databases."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
import copy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from open_webui.models.chats import Chat, Chats, ChatForm
from open_webui.models.education import Education, Submission, WritingSession
from open_webui.services.education.single_conversation import (
    choose_conversation,
    consolidation_plan,
    apply_consolidation,
)
from open_webui.test.apps.webui.routers.test_education_smoke import education_client, UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, submit


def folder_for(SessionLocal, sid):
    with SessionLocal() as db:
        return db.get(WritingSession, sid).folder_id


def chat_body(title='Conversation'):
    return {
        'title': title,
        'history': {
            'messages': {'u': {'id': 'u', 'role': 'user', 'content': title, 'parentId': None, 'childrenIds': []}},
            'currentId': 'u',
        },
    }


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
def test_create_copy_import_move_archive_delete_are_guarded(education_client, monkeypatch, mode):
    from open_webui.routers import chats as router

    async def allow_import(*args, **kwargs):
        return None

    monkeypatch.setattr(router, 'require_chat_import_permission', allow_import)
    client, teacher, _, student, _, SessionLocal = education_client
    _, sid, _ = setup(client, teacher, student, mode=mode)
    folder = folder_for(SessionLocal, sid)
    first = client.post('/api/v1/chats/new', json={'chat': chat_body(), 'folder_id': folder})
    assert first.status_code == 200, first.text
    cid = first.json()['id']
    with SessionLocal() as db:
        ws = db.get(WritingSession, sid)
        assert ws.chat_id == ws.active_chat_id == cid
    assert client.post('/api/v1/chats/new', json={'chat': chat_body('second'), 'folder_id': folder}).status_code == 409
    assert client.post(f'/api/v1/chats/{cid}/fork', json={}).status_code == 409
    assert client.post(f'/api/v1/chats/{cid}/clone', json={'title': 'copy'}).status_code == 409
    assert (
        client.post(
            '/api/v1/chats/import', json={'chats': [{'chat': chat_body('import'), 'folder_id': folder}]}
        ).status_code
        == 409
    )
    assert client.post(f'/api/v1/chats/{cid}/folder', json={'folder_id': None}).status_code == 409
    assert client.post(f'/api/v1/chats/{cid}/archive').status_code == 409
    assert client.delete(f'/api/v1/chats/{cid}').status_code == 409
    assert client.post('/api/v1/chats/archive/all').status_code == 409
    assert client.delete('/api/v1/chats/').status_code == 409
    unrelated = client.post('/api/v1/chats/new', json={'chat': chat_body('ordinary')}).json()['id']
    assert client.post(f'/api/v1/chats/{unrelated}/folder', json={'folder_id': folder}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Chat).filter_by(folder_id=folder).count() == 1


def test_from_scratch_keeps_multiple_conversations(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    assignment, sid, _ = setup(client, teacher, student, mode='from_scratch')
    folder = folder_for(SessionLocal, sid)
    for title in ['one', 'two']:
        assert client.post('/api/v1/chats/new', json={'chat': chat_body(title), 'folder_id': folder}).status_code == 200
    with SessionLocal() as db:
        assert db.query(Chat).filter_by(folder_id=folder).count() == 2
    UserContext.current_user = teacher
    assert (
        client.patch(f'/api/v1/assignments/{assignment["id"]}', json={'task_mode': 'revise_argument'}).status_code
        == 409
    )


def test_concurrent_first_requests_create_only_one_conversation(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    _, sid, _ = setup(client, teacher, student)
    folder = folder_for(SessionLocal, sid)

    async def create():
        return await Chats.insert_new_chat(str(uuid4()), student.id, ChatForm(chat=chat_body(), folder_id=folder))

    async def race():
        return await asyncio.gather(create(), create(), return_exceptions=True)

    results = asyncio.run(race())
    assert sum(not isinstance(result, Exception) for result in results) == 1, results
    errors = [result for result in results if isinstance(result, Exception)]
    assert isinstance(errors[0], HTTPException) and errors[0].status_code == 409
    with SessionLocal() as db:
        assert db.query(Chat).filter_by(folder_id=folder).count() == 1


def test_consolidation_preserves_selected_chat_draft_and_submission(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    assignment, sid, _ = setup(client, teacher, student)
    folder = folder_for(SessionLocal, sid)
    cid = client.post('/api/v1/chats/new', json={'chat': chat_body('keep'), 'folder_id': folder}).json()['id']
    result = submit(client, assignment, sid)
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        submission = db.query(Submission).filter_by(assignment_id=assignment['id']).one()
        frozen = copy.deepcopy(submission.stats_json)
        ws = db.get(WritingSession, sid)
        baseline = ws.draft_baseline_text
        # Simulate already-existing duplicate chats; normal creation must reject these.
        for cid2 in ['old-extra', 'new-extra']:
            db.add(
                Chat(
                    id=cid2,
                    user_id=student.id,
                    title=cid2,
                    chat=chat_body(cid2),
                    folder_id=folder,
                    meta={},
                    created_at=10,
                    updated_at=2000000000,
                    archived=False,
                )
            )
        db.commit()
        plan = consolidation_plan(db)
        assert plan[0]['keep'] == cid
        assert plan[0]['delete'] == ['new-extra', 'old-extra']
        db.query(Chat).filter_by(id='new-extra').update({'updated_at': 2000000001})
        db.commit()
        with pytest.raises(ValueError, match='changed'):
            apply_consolidation(db, plan)
        db.rollback()
        assert db.query(Chat).filter_by(folder_id=folder).count() == 3
        assert apply_consolidation(db, consolidation_plan(db)) == 2
        db.commit()
        assert db.query(Chat).filter_by(folder_id=folder).one().id == cid
        db.expire_all()
        assert db.get(WritingSession, sid).draft_baseline_text == baseline
        assert db.get(Submission, submission.id).stats_json == frozen
        assert consolidation_plan(db) == []


def test_keep_rule_prefers_active_content_then_latest_content():
    rows = [
        dict(id='empty', has_content=False, updated_at=30, created_at=1),
        dict(id='old', has_content=True, updated_at=10, created_at=1),
        dict(id='new', has_content=True, updated_at=20, created_at=1),
    ]
    assert choose_conversation(rows, 'old')['id'] == 'old'
    assert choose_conversation(rows, 'empty')['id'] == 'new'
    assert choose_conversation(rows, None)['id'] == 'new'
    assert choose_conversation([], None) is None
