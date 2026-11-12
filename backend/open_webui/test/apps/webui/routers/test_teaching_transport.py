"""Published teaching survives administrator transport changes without rewriting evidence."""

import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.models.education import Assignment
from open_webui.models.teaching_trials import AssignmentAiRevision, TeachingCall
from open_webui.services.education import teaching_runtime as runtime
from open_webui.test.apps.webui.routers.test_model_fallback import OK
from open_webui.test.apps.webui.routers.test_model_fallback import routing as base_routing
from open_webui.test.apps.webui.routers.test_teaching_trials import education_client as base_education_client
from open_webui.test.apps.webui.routers.test_teaching_trials import env as base_env
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    prepare,
    publish,
    student_session,
)
from open_webui.test.apps.webui.routers.test_transient_retry import FakeResponse

education_client = base_education_client
env = base_env
routing = base_routing


def backup(model):
    return {'model_id': model, 'capabilities': {'vision': True}, 'connection_hash': f'route-{model}'}


@pytest.mark.parametrize('before,after', [(None, 'backup-A'), ('backup-A', 'backup-B'), ('backup-A', None)])
def test_existing_assignment_reads_with_live_transport_and_preserves_published_config(env, monkeypatch, before, after):
    original_resolve = runtime.resolve_binding
    state = {'changed': False}

    async def resolve(*args):
        binding = await original_resolve(*args)
        binding['params'] = {'temperature': 0.9 if state['changed'] else 0.2}
        target = after if state['changed'] else before
        if target:
            binding['fallback'] = backup(target)
        if state['changed']:
            binding.update(
                route={'base_model_id': 'model-A', 'url_index': 5, 'connection_hash': 'current-primary'},
                workspace_model=True,
                capabilities={'reasoning': False, 'vision': True},
                thinking_format='openai',
            )
        return binding

    monkeypatch.setattr(runtime, 'resolve_binding', resolve)
    monkeypatch.setattr('open_webui.services.education.teaching_preparations.resolve_binding', resolve)
    assignment = publish(env, prepare(env)).json()[0]
    sid = student_session(env, assignment)
    with env.factory() as db:
        published = copy.deepcopy(db.get(AssignmentAiRevision, assignment['current_ai_revision_id']).config)
    state['changed'] = True
    response = env.client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'ready'
    assert result['thinking'] == 'model_default'
    assert result['context']['config']['binding'].get('fallback') == (backup(after) if after else None)
    assert result['context']['config']['binding']['route']['connection_hash'] == 'current-primary'
    assert result['context']['config']['binding']['params'] == {'temperature': 0.2}
    assert env.calls[-1]['temperature'] == 0.2
    assert result['context']['config']['ai'] == published['ai']
    with env.factory() as db:
        revision = db.get(AssignmentAiRevision, assignment['current_ai_revision_id'])
        assert revision.config == published
        assert db.get(Assignment, assignment['id']).current_ai_revision_id == revision.id
        assert db.query(AssignmentAiRevision).filter_by(assignment_id=assignment['id']).count() == 1
        call = db.query(TeachingCall).filter_by(session_id=sid).one()
        assert call.context['config'] == result['context']['config']
        frozen = runtime.frozen_evidence(sid, db)
        assert frozen['calls'][0]['context']['config']['binding'].get('fallback') == (backup(after) if after else None)
    # A route update does not request another reading of an already-read draft.
    state['changed'] = False
    repeated = env.client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert repeated.json()['id'] == result['id']
    assert len(env.calls) == 1


@pytest.mark.parametrize('field,value', [('base_model_id', 'another-model'), ('filter_fingerprint', 'new-filter')])
def test_transport_refresh_still_rejects_a_different_model_or_teaching_filter(env, monkeypatch, field, value):
    assignment = publish(env, prepare(env)).json()[0]
    sid = student_session(env, assignment)
    original_resolve = runtime.resolve_binding

    async def changed(*args):
        result = await original_resolve(*args)
        result[field] = value
        return result

    monkeypatch.setattr(runtime, 'resolve_binding', changed)
    response = env.client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert response.status_code == 409
    assert not env.calls


def test_current_fallback_is_captured_once_and_real_adapter_switches_after_timeout(routing, monkeypatch):
    from open_webui.routers import openai
    from open_webui.utils.model_fallback import provider_route

    r = routing
    route = asyncio.run(provider_route(r.request, r.user, 'google/backup'))[0]
    binding = {
        'model_id': 'primary',
        'base_model_id': 'primary',
        'workspace_model': True,
        'route': {'base_model_id': 'primary', 'url_index': 0, 'connection_hash': 'primary-route'},
        'params': {'temperature': 0.2},
        'filter_fingerprint': 'same-filter',
        'thinking_support': {},
        'thinking_format': None,
        'capabilities': {},
    }
    config = {
        'ai': {
            'model_id': 'primary',
            'prompt': 'Published teaching prompt',
            'thinking': 'model_default',
            'template_version': 1,
        },
        'binding': binding,
        'title': 'Assignment',
        'description': '',
        'description_version': 1,
        'execution_version': runtime.execution_version(),
        'validation_environment': 'published',
    }
    original = copy.deepcopy(config)
    current = {**binding, 'fallback': route, 'capabilities': {'vision': True}, 'params': {'temperature': 0.9}}

    async def resolve(*args):
        return copy.deepcopy(current)

    monkeypatch.setattr(runtime, 'resolve_binding', resolve)
    context = {'purpose': 'coaching_chat', 'attempts': []}
    resolved = asyncio.run(runtime.validate_binding(r.request, r.user, config))
    installed = runtime.install_binding(r.request, config, context, resolved)
    assert installed['binding']['fallback'] == route
    assert installed['binding']['params'] == {'temperature': 0.2}
    # Changes after capture must not replace this call's route plan.
    current['fallback'] = backup('later-backup')
    assert runtime.install_binding(r.request, config, context, current) is installed
    r.body['messages'].insert(0, {'role': 'system', 'content': config['ai']['prompt']})
    r.body.update(installed['binding']['params'])
    r.outcomes[:] = [TimeoutError(), FakeResponse(200, OK)]
    assert asyncio.run(openai.generate_chat_completion(r.request, r.body, r.user)) == OK
    assert len(r.sent) == 2
    sent = [json.loads(item['data']) for item in r.sent]
    assert sent[0]['messages'] == sent[1]['messages']
    assert sent[1]['model'] == 'google/backup'
    assert sent[1]['temperature'] == 0.2
    assert [a['fallback'] for a in context['attempts']] == [False, True]
    assert context['config']['binding']['fallback'] == route
    assert config == original


def test_formal_chat_installs_live_transport_without_new_revision(env, monkeypatch):
    import uuid

    import open_webui.internal.db as internal_db
    import open_webui.main as main
    from open_webui.models.education import Education
    from starlette.requests import Request

    assignment = publish(env, prepare(env)).json()[0]
    sid = student_session(env, assignment)
    monkeypatch.setattr(internal_db, 'SessionLocal', env.factory)
    original_resolve = runtime.resolve_binding

    async def changed(*args):
        binding = await original_resolve(*args)
        binding.update(fallback=backup('new-backup'), capabilities={'vision': True, 'reasoning': False})
        return binding

    async def provider(request, form_data, user):
        assert request.state.teaching_binding['binding']['fallback'] == backup('new-backup')
        runtime.record_provider_request(request, form_data)
        return {'choices': [{'message': {'content': 'Synthetic test feedback'}, 'finish_reason': 'stop'}]}

    monkeypatch.setattr(runtime, 'resolve_binding', changed)
    monkeypatch.setattr(main, 'chat_completion_handler', provider)
    with env.factory() as db:
        folder_id = Education.get_writing_session_by_id(sid, db=db).folder_id
    request = Request(
        {'type': 'http', 'method': 'POST', 'path': '/api/chat/completions', 'headers': [], 'app': env.client.app}
    )
    body = {
        'model': 'model-A',
        'parent_id': None,
        'stream': False,
        'folder_id': folder_id,
        'id': str(uuid.uuid4()),
        'messages': [{'role': 'user', 'content': 'Please read this paragraph.'}],
        'user_message': {
            'id': str(uuid.uuid4()),
            'role': 'user',
            'content': 'Please read this paragraph.',
            'parentId': None,
        },
    }
    assert asyncio.run(main.chat_completion(request, body, env.student, client_request=True))
    with env.factory() as db:
        call = db.query(TeachingCall).filter_by(session_id=sid).one()
        assert call.status == 'ready'
        assert call.context['config']['binding']['fallback'] == backup('new-backup')
        assert not db.get(AssignmentAiRevision, assignment['current_ai_revision_id']).config['binding'].get('fallback')
