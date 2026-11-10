import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi import HTTPException
from open_webui.models.config import Config
from open_webui.models.education import WritingSession
from open_webui.routers.configs import router as configs_router
from open_webui.services.education.writing_access import ensure_writing_session_access
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client,
    UserContext,
    _prepare_assignment_flow,
    _WRITING_WRITE_REQUESTS,
)


@pytest.mark.parametrize('role', ['student', 'teacher'])
def test_admin_switches_personal_writing_without_restart(education_client, role):
    client, teacher, _, student, _, SessionLocal = education_client
    _prepare_assignment_flow(client, teacher, student)
    client.app.include_router(configs_router, prefix='/api/v1/configs')
    client.app.state.MODELS = {'test-model': {'id': 'test-model', 'name': 'Test'}}
    admin = teacher.model_copy(update={'role': 'admin'})
    UserContext.current_user = admin
    response = client.get('/api/v1/configs/education')
    assert response.status_code == 200, response.text
    form = response.json()
    assert form['EDUCATION_PERSONAL_WRITING_STUDENT'] is False
    assert form['EDUCATION_PERSONAL_WRITING_TEACHER'] is False
    key = f'EDUCATION_PERSONAL_WRITING_{role.upper()}'
    subject = student if role == 'student' else teacher
    UserContext.current_user = subject
    assert client.post('/api/v1/me/writing/personal', json={'title': 'Default denied'}).status_code == 403
    assert client.get('/api/v1/me/writing/home').json()['personal_writing_enabled'] is False

    def save(enabled):
        UserContext.current_user = admin
        form[key] = enabled
        result = client.post('/api/v1/configs/education', json=form)
        assert result.status_code == 200, result.text
        assert result.json()[key] is enabled
        assert asyncio.run(Config.get(f'education.personal_writing.{role}')) is enabled
        UserContext.current_user = subject

    save(True)
    created = client.post('/api/v1/me/writing/personal', json={'title': 'Retained draft'})
    assert created.status_code == 200, created.text
    session_id = created.json()['writing_session']['id']
    home = client.get('/api/v1/me/writing/home').json()
    assert home['personal_writing_enabled'] is True
    assert len(home['personal_items']) == 1
    save(False)
    assert client.post('/api/v1/me/writing/personal', json={'title': 'Denied'}).status_code == 403
    assert client.get(f'/api/v1/writing/{session_id}/workspace').status_code == 403
    for endpoint, payload in _WRITING_WRITE_REQUESTS:
        result = client.post(f'/api/v1/writing-sessions/{session_id}/{endpoint}', json=payload)
        assert result.status_code == 403, result.text
    home = client.get('/api/v1/me/writing/home').json()
    assert home['personal_writing_enabled'] is False
    assert home['personal_items'] == []
    assert all(item['project_mode'] != 'personal_writing' for item in home['recent_items'])
    if role == 'student':
        assert len(home['assignment_items']) == 1
    with SessionLocal() as db:
        session = db.get(WritingSession, session_id)
        assert session is not None
        with pytest.raises(HTTPException) as error:
            asyncio.run(ensure_writing_session_access(subject, session))
        assert error.value.status_code == 403
    save(True)
    assert client.get(f'/api/v1/writing/{session_id}/workspace').status_code == 200
    assert (
        client.post(f'/api/v1/writing-sessions/{session_id}/autosave', json={'content_text': 'Resumed'}).status_code
        == 200
    )
    # Disabling either role never disables the administrator's own writing.
    save(False)
    UserContext.current_user = admin
    assert client.post('/api/v1/me/writing/personal', json={'title': 'Admin draft'}).status_code == 200
    UserContext.current_user = subject
    assert client.post('/api/v1/configs/education', json=form).status_code == 401
