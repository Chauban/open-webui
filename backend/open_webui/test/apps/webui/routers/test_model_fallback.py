"""Exercise real provider routing with fake HTTP only; never call a vendor."""

import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.models.models import ModelMeta, ModelParams
from open_webui.routers import openai
from open_webui.test.apps.webui.routers.test_education_smoke import education_client as base_education_client
from open_webui.test.apps.webui.routers.test_transient_retry import FakeResponse
from open_webui.utils import model_fallback

education_client = base_education_client


@pytest.fixture
def routing(monkeypatch):
    sources = {
        'primary': SimpleNamespace(
            id='primary',
            base_model_id=None,
            is_active=True,
            meta=ModelMeta(fallback_model_id='google/backup', capabilities={'vision': True}),
            params=ModelParams(system='Keep the same instruction.'),
        ),
        'google/backup': SimpleNamespace(
            id='google/backup',
            base_model_id=None,
            is_active=True,
            meta=ModelMeta(),
            params=ModelParams(system='DO NOT INJECT THIS'),
        ),
    }
    sent, statuses, outcomes = [], [], []
    request = SimpleNamespace(
        state=SimpleNamespace(reading_context={}),
        app=SimpleNamespace(
            state=SimpleNamespace(
                OPENAI_MODELS={
                    'primary': {'id': 'primary', 'urlIdx': 0},
                    'google/backup': {'id': 'google/backup', 'urlIdx': 1},
                }
            )
        ),
    )

    async def lookup(model_id, **kwargs):
        return sources.get(model_id)

    async def connection(index):
        return f'https://provider-{index}.example/v1', f'key-{index}', {}

    async def headers(request, url, key, *args, **kwargs):
        return {'Authorization': f'Bearer {key}'}, {}

    async def enabled(*args, **kwargs):
        return True

    async def permitted(*args, **kwargs):
        return None

    async def notify(request, metadata, *, done=False):
        statuses.append(done)

    class Session:
        async def request(self, **kwargs):
            sent.append(kwargs)
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    async def session():
        return Session()

    monkeypatch.setattr(openai.Models, 'get_model_by_id', lookup)
    monkeypatch.setattr(openai.Config, 'get', enabled)
    monkeypatch.setattr(openai, 'check_model_access', permitted)
    monkeypatch.setattr(openai, 'get_openai_connection', connection)
    monkeypatch.setattr(openai, 'get_headers_and_cookies', headers)
    monkeypatch.setattr(openai, 'get_session', session)
    monkeypatch.setattr(openai, 'publish_model_provider_request_failed', permitted)
    monkeypatch.setattr(model_fallback, 'notify_retry', notify)
    body = {
        'model': 'primary',
        'stream': False,
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Read my draft.'},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,TEST'}},
                ],
            }
        ],
    }
    user = SimpleNamespace(id='student', role='user')
    return SimpleNamespace(
        request=request, user=user, body=body, sent=sent, statuses=statuses, outcomes=outcomes, sources=sources
    )


def run(r):
    return asyncio.run(openai.generate_chat_completion(r.request, r.body, r.user))


OK = {'choices': [{'message': {'content': 'Result'}}]}


def test_timeout_switches_address_key_model_without_changing_input(routing):
    r = routing
    r.outcomes[:] = [FakeResponse(200, read_error=TimeoutError()), FakeResponse(200, OK)]
    original = copy.deepcopy(r.body)
    assert run(r) == OK
    assert len(r.sent) == 2 and r.body == original
    first, second = [json.loads(call['data']) for call in r.sent]
    assert first['model'] == 'primary' and second['model'] == 'google/backup'
    assert first['messages'] == second['messages']
    assert 'DO NOT INJECT THIS' not in json.dumps(second)
    assert r.sent[0]['url'] == 'https://provider-0.example/v1/chat/completions'
    assert r.sent[1]['url'] == 'https://provider-1.example/v1/chat/completions'
    assert r.sent[1]['headers']['Authorization'] == 'Bearer key-1'
    assert r.statuses == [False, True]
    attempts = r.request.state.reading_context['provider_attempts']
    assert [attempt['fallback'] for attempt in attempts] == [False, True]
    assert attempts[0]['error_type'] == 'TimeoutError'
    assert 'key-1' not in json.dumps(attempts)


def test_success_never_calls_backup(routing):
    routing.outcomes[:] = [FakeResponse(200, OK)]
    assert run(routing) == OK
    assert len(routing.sent) == 1 and not routing.statuses


def test_both_timeout_stop_after_two_calls(routing):
    routing.outcomes[:] = [TimeoutError(), TimeoutError()]
    with pytest.raises(HTTPException) as error:
        run(routing)
    assert error.value.status_code == 504
    assert len(routing.sent) == 2


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
def test_non_timeout_http_errors_do_not_switch(routing, status):
    routing.outcomes[:] = [FakeResponse(status)]
    assert run(routing).status_code == status
    assert len(routing.sent) == 1 and not routing.statuses


def test_gateway_timeout_switches(routing):
    routing.outcomes[:] = [FakeResponse(504), FakeResponse(200, OK)]
    assert run(routing) == OK
    assert len(routing.sent) == 2


def test_cancellation_does_not_start_backup(routing):
    routing.outcomes[:] = [asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        run(routing)
    assert len(routing.sent) == 1 and not routing.statuses


def test_disconnect_after_timeout_does_not_start_backup(routing):
    async def disconnected():
        return True

    routing.request.is_disconnected = disconnected
    routing.outcomes[:] = [TimeoutError()]
    with pytest.raises(asyncio.CancelledError):
        run(routing)
    assert len(routing.sent) == 1


def test_stream_switches_before_first_chunk_only(routing, monkeypatch):
    async def stream(response, head=b''):
        yield head
        async for chunk, _ in response.content.iter_chunks():
            yield chunk

    monkeypatch.setattr(openai, 'stream_wrapper', stream)
    routing.body['stream'] = True
    routing.outcomes[:] = [
        FakeResponse(200, sse=True, chunks=[TimeoutError()]),
        FakeResponse(200, sse=True, chunks=[b'data: hello\n\n', TimeoutError()]),
    ]

    async def consume():
        response = await openai.generate_chat_completion(routing.request, routing.body, routing.user)
        assert await anext(response.body_iterator) == b'data: hello\n\n'
        with pytest.raises(asyncio.TimeoutError):
            await anext(response.body_iterator)

    asyncio.run(consume())
    assert len(routing.sent) == 2


def test_only_admin_can_change_fallback(routing):
    form = SimpleNamespace(id='primary', base_model_id=None, meta=ModelMeta(fallback_model_id='google/backup'))
    with pytest.raises(HTTPException) as error:
        asyncio.run(model_fallback.validate_model_fallback(routing.request, routing.user, form))
    assert error.value.status_code == 403


def test_self_and_cycles_rejected(routing):
    admin = SimpleNamespace(role='admin')
    form = SimpleNamespace(id='primary', base_model_id=None, meta=ModelMeta(fallback_model_id='primary'))
    with pytest.raises(HTTPException):
        asyncio.run(model_fallback.validate_model_fallback(routing.request, admin, form))
    form.meta.fallback_model_id = 'google/backup'
    routing.sources['google/backup'].meta.fallback_model_id = 'primary'
    with pytest.raises(HTTPException):
        asyncio.run(model_fallback.validate_model_fallback(routing.request, admin, form))


def test_disabled_backup_rejected(routing):
    routing.sources['google/backup'].is_active = False
    with pytest.raises(HTTPException):
        run(routing)
    assert not routing.sent


def test_options_keep_provider_identity_without_credentials(routing, monkeypatch):
    calls = []
    routing.request.app.state.OPENAI_MODELS['another-primary'] = {'id': 'another-primary', 'urlIdx': 0}
    for item in routing.sources.values():
        item.name = 'Gemini'

    async def catalog(*args, **kwargs):
        return None

    async def saved():
        return list(routing.sources.values())

    async def connection(index):
        calls.append(index)
        return f'https://provider-{index}.example/v1', 'SECRET-MUST-NOT-LEAK', {}

    monkeypatch.setattr(openai, 'get_all_models', catalog)
    monkeypatch.setattr(openai, 'get_openai_connection', connection)
    monkeypatch.setattr(openai.Models, 'get_base_models', saved)
    options = asyncio.run(model_fallback.fallback_options(routing.request))
    assert calls == [0, 1]
    assert options[0]['provider'] != options[1]['provider']
    assert options[0]['id'] != options[1]['id']
    assert 'SECRET-MUST-NOT-LEAK' not in json.dumps(options)


@pytest.mark.parametrize('mode', ['revise_argument', 'revise_draft'])
def test_reading_retry_progress_persists_without_duplicate_reading(education_client, monkeypatch, mode):
    from open_webui.models.education_types import RevisionReading
    from open_webui.services.education import revision_reading as readings
    from open_webui.test.apps.webui.routers.test_revision_coaching import model_stub, setup

    client, teacher, _, student, _, factory = education_client
    _, sid, _ = setup(client, teacher, student, mode=mode)
    model_stub(monkeypatch)
    original_call = readings.call_step_model
    monkeypatch.setattr(readings, 'get_db_context', factory)
    observed = []

    async def retry_then_reply(request, *args, **kwargs):
        await request.state.reading_retry_callback()
        with factory() as db:
            rows = db.query(RevisionReading).filter_by(writing_session_id=sid).all()
            assert len(rows) == 1
            observed.append((rows[0].status, rows[0].context['retrying']))
        return await original_call(request, *args, **kwargs)

    monkeypatch.setattr(readings, 'call_step_model', retry_then_reply)
    result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'ready'
    assert observed == [('running', True)]
    records = client.get(f'/api/v1/writing-sessions/{sid}/readings').json()
    assert len(records) == 1


def test_captured_teaching_binding_rejects_changed_fallback(monkeypatch):
    from open_webui.services.education import teaching_runtime as runtime

    async def changed(*args):
        return {'fallback': {'model_id': 'different-backup'}}

    monkeypatch.setattr(runtime, 'resolve_binding', changed)
    config = {
        'binding': {'fallback': {'model_id': 'original-backup'}},
        'ai': {'model_id': 'primary', 'prompt': 'Prompt', 'thinking': 'model_default', 'template_version': 1},
    }
    with pytest.raises(HTTPException) as error:
        asyncio.run(runtime.validate_binding(None, None, config, check_execution=False))
    assert error.value.status_code == 409


def test_admin_can_save_reload_and_clear_fallback(education_client, monkeypatch):
    from open_webui.routers import models as models_router
    from open_webui.test.apps.webui.routers.test_education_smoke import UserContext

    client, teacher, _, _, _, _ = education_client
    client.app.include_router(models_router.router, prefix='/api/v1/models')
    UserContext.current_user = teacher.model_copy(update={'role': 'admin'})
    client.app.state.OPENAI_MODELS = {
        'primary': {'id': 'primary', 'urlIdx': 0},
        'google/backup': {'id': 'google/backup', 'urlIdx': 1},
    }

    async def connection(index):
        return f'https://provider-{index}.example/v1', f'fake-key-{index}', {}

    monkeypatch.setattr(openai, 'get_openai_connection', connection)
    form = {
        'id': 'primary',
        'name': 'Primary',
        'base_model_id': None,
        'meta': {'fallback_model_id': 'google/backup'},
        'params': {},
        'access_grants': [],
    }
    created = client.post('/api/v1/models/create', json=form)
    assert created.status_code == 200, created.text
    assert created.json()['meta']['fallback_model_id'] == 'google/backup'
    loaded = client.get('/api/v1/models/model', params={'id': 'primary'})
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()['meta']['fallback_model_id'] == 'google/backup'
    form['meta']['fallback_model_id'] = None
    cleared = client.post('/api/v1/models/model/update', json=form)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()['meta']['fallback_model_id'] is None
