"""Workspace aggregation uses real migration-built isolated databases, never a model."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.models.education import Assignment
from open_webui.models.education_types import RevisionReading
from open_webui.services.education.writing_document import text_document
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client as base_education_client,
    UserContext,
)
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, DRAFT, model_stub

education_client = base_education_client


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
def test_workspace_state_matches_independent_reads_and_session_route(education_client, mode):
    client, teacher, _, student, _, sessions = education_client
    assignment, sid, _ = setup(client, teacher, student, mode=mode)
    url = f'/api/v1/assignments/{assignment["id"]}/workspace'
    response = client.get(url)
    assert response.status_code == 200, response.text
    workspace = response.json()
    state = workspace['initial_state']
    assert state['teaching_summary'] == client.get(f'/api/v1/writing-sessions/{sid}/teaching-summary').json()
    assert state['pending_draft'] is None
    assert state['challenge'] is None
    assert state['readings'] == []
    if mode != 'from_scratch':
        assert state['readings'] == client.get(f'/api/v1/writing-sessions/{sid}/readings').json()
    session_response = client.get(f'/api/v1/writing/{sid}/workspace')
    assert session_response.status_code == 200, session_response.text
    other = session_response.json()
    for field in ('initial_state', 'review', 'effective_due_at', 'can_switch_thinking', 'source_map'):
        assert other[field] == workspace[field]
    with sessions() as db:
        assert db.query(RevisionReading).count() == 0  # GET never starts first reading.
    if mode == 'revise_argument':
        assert set(state['teaching_summary']) == {
            'id',
            'name',
            'owned_by',
            'revision',
            'change_summary',
            'thinking',
            'info',
        }


def test_pending_structure_revision_and_permission_boundaries(education_client):
    client, teacher, _, student, outsider, sessions = education_client
    assignment, sid, _ = setup(client, teacher, student)
    reset = client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline')
    assert reset.status_code == 200, reset.text
    document = text_document(DRAFT)
    response = client.put(
        f'/api/v1/writing-sessions/{sid}/pending-draft',
        json={
            'content_json': document,
            'materials': [],
            'expected_revision': 0,
        },
    )
    assert response.status_code == 200, response.text
    url = f'/api/v1/assignments/{assignment["id"]}/workspace'
    state = client.get(url).json()['initial_state']
    assert state['pending_draft'] == client.get(f'/api/v1/writing-sessions/{sid}/pending-draft').json()
    assert state['pending_draft']['revision'] == 1
    assert state['pending_draft']['content_json'] == document
    assert state['readings'] == []
    UserContext.current_user = outsider
    assert client.get(url).status_code == 403
    assert client.get(f'/api/v1/writing/{sid}/workspace').status_code == 403
    UserContext.current_user = student
    with sessions() as db:
        db.get(Assignment, assignment['id']).hidden = True
        db.commit()
    assert client.get(url).status_code == 403
    assert client.get(f'/api/v1/writing/{sid}/workspace').status_code == 403


def test_aggregation_failure_is_not_an_empty_reading_history(education_client, monkeypatch):
    client, teacher, _, student, _, _ = education_client
    assignment, _, _ = setup(client, teacher, student)
    from open_webui.services.education import revision_reading

    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic read failure')

    monkeypatch.setattr(revision_reading, 'reading_records', fail)
    with pytest.raises(RuntimeError, match='Synthetic read failure'):
        client.get(f'/api/v1/assignments/{assignment["id"]}/workspace')


@pytest.mark.parametrize('status', ['ready', 'running', 'failed'])
def test_existing_reading_and_original_chat_are_restored_without_model_calls(education_client, monkeypatch, status):
    client, teacher, _, student, _, sessions = education_client
    assignment, sid, _ = setup(client, teacher, student)
    calls = model_stub(monkeypatch, text='合成初读反馈，保留真实来源。')
    result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    with sessions() as db:
        reading = db.query(RevisionReading).filter_by(writing_session_id=sid).one()
        reading.status = status
        db.commit()
    expected = client.get(f'/api/v1/writing-sessions/{sid}/readings').json()
    first = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
    assert first['initial_state']['readings'] == expected
    assert first['initial_state']['readings'][0]['status'] == status
    chat_id = first['active_chat_id']
    assert chat_id
    original_chat = client.get(f'/api/v1/chats/{chat_id}').json()
    for _ in range(3):
        restored = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
        assert restored['active_chat_id'] == chat_id
        assert restored['initial_state'] == first['initial_state']
        assert restored['note'] == first['note']
    assert client.get(f'/api/v1/chats/{chat_id}').json() == original_chat
    assert len(calls) == 1
