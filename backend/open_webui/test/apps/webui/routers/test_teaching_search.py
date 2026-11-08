"""Search is opt-in; source text, failures and limits remain auditable."""

import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import httpx
import pytest
from open_webui.models.teaching_trials import AiCandidate
from open_webui.services.education import teaching_search as search
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    DRAFT,
    UserContext,
    action,
    payload,
    prepare,
    publish,
    student_session,
    trial,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import education_client as base_education_client
from open_webui.test.apps.webui.routers.test_teaching_trials import env as base_env

education_client = base_education_client
env = base_env


def reply(content='保留原文，出处仍需核对。', calls=None):
    return {
        'id': 'reply',
        'model': 'model-A',
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content, **({'tool_calls': calls} if calls else {})},
                'finish_reason': 'tool_calls' if calls else 'stop',
            }
        ],
    }


def tool(name, args, id='call-1'):
    return {'id': id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


def request():
    return SimpleNamespace(state=SimpleNamespace(teaching_evidence={}))


def body(stream=False):
    return {
        'model': 'model-A',
        'stream': stream,
        'messages': [{'role': 'system', 'content': '教师提示词原文'}, {'role': 'user', 'content': '请核对出处'}],
    }


async def key(*args):
    return 'private-test-key'


def test_search_and_fetch_keep_evidence_and_reject_false_quote(monkeypatch):
    monkeypatch.setattr(search, 'api_key', key)
    original = body()
    sent = []
    requests = []
    responses = [
        reply('', [tool('search_sources', {'query': '原文'})]),
        reply('', [tool('read_source', {'url': 'https://example.org/book', 'quote': '并不存在的引文'})]),
        reply(),
    ]

    async def model(**kwargs):
        sent.append(copy.deepcopy(kwargs['form_data']))
        return responses.pop(0)

    async def post(client, credential, operation, data):
        requests.append((operation, data))
        if operation == 'search':
            return {
                'results': [{'url': 'https://example.org/book', 'title': '原书', 'summary': '相关线索', 'content': ''}]
            }
        return {'title': '原书', 'content': '实际取得的原文'}

    monkeypatch.setattr(search, 'post_tool', post)
    req = request()
    result = asyncio.run(search.execute(req, None, original, model))
    assert result['choices'][0]['message']['content']
    assert original == body()
    assert sent[0]['messages'][0]['content'].startswith('教师提示词原文')
    record = req.state.teaching_evidence['source_search']
    assert record['calls'][0]['result']['sources'][0]['status'] == 'search_summary'
    assert record['calls'][1]['result']['quote_found_in_returned_text'] is False
    assert record['calls'][1]['result']['content'] == '实际取得的原文'
    assert [r[0] for r in requests] == ['search', 'fetch']
    assert 'private-test-key' not in json.dumps(record)


def test_auto_no_lookup_uses_no_search_service_and_preserves_stream_contract(monkeypatch):
    monkeypatch.setattr(search, 'api_key', key)

    async def post(*args):
        pytest.fail('No source request expected')

    async def model(**kwargs):
        return reply('这次无需查资料。')

    monkeypatch.setattr(search, 'post_tool', post)
    req = request()

    async def run():
        response = await search.execute(req, None, body(True), model)
        return ''.join([chunk async for chunk in response.body_iterator])

    text = asyncio.run(run())
    assert '这次无需查资料' in text and '[DONE]' in text
    assert req.state.teaching_evidence['source_search']['status'] == 'not_needed'


def test_budget_unknown_tools_and_unseen_urls_are_enforced(monkeypatch):
    monkeypatch.setattr(search, 'api_key', key)
    sent = []
    operations = []

    async def post(client, credential, operation, data):
        operations.append(operation)
        return {'results': [{'url': 'https://example.org/book', 'title': '书', 'content': '正文'}]}

    async def model(**kwargs):
        sent.append(copy.deepcopy(kwargs['form_data']))
        if 'tools' not in kwargs['form_data']:
            return reply()
        return reply(
            '',
            [
                tool('search_sources', {'query': '书'}, 's'),
                tool('read_source', {'url': 'http://127.0.0.1/secret'}, 'f'),
                tool('delete_file', {}, 'x'),
            ],
        )

    monkeypatch.setattr(search, 'post_tool', post)
    req = request()
    asyncio.run(search.execute(req, None, body(), model))
    assert operations == ['search', 'search']
    assert len(sent) == search.MAX_ROUNDS + 1 and 'tools' not in sent[-1]
    errors = [c['result'].get('error') for c in req.state.teaching_evidence['source_search']['calls']]
    assert 'url_not_in_search_results' in errors and 'unknown_tool' in errors and 'search_budget_exhausted' in errors


def test_service_error_is_sanitized_and_not_reported_as_verified(monkeypatch):
    async def run():
        def transport(req):
            return httpx.Response(401, json={'secret': 'do-not-log'})

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            return await search.post_tool(client, 'private-test-key', 'search', {'query': '原文'})

    assert asyncio.run(run()) == {'error': 'source_service_unavailable', 'http_status': 401}


def test_disabled_and_enabled_trial_use_same_teacher_prompt_without_mutation(env, monkeypatch):
    from open_webui.services.education import ai_steps

    monkeypatch.setattr(ai_steps, 'generate_chat_completion', env.real_generate)
    sent = []

    async def model(**kwargs):
        sent.append(copy.deepcopy(kwargs['form_data']))
        return reply()

    monkeypatch.setattr('open_webui.utils.chat.generate_openai_chat_completion', model)
    off = trial(env, prepare(env))
    disabled = action(env, off, 'confirm', DRAFT)
    assert disabled.status_code == 200, disabled.text
    assert len(sent) == 1 and 'tools' not in sent[0]
    assert search.RULES not in sent[0]['messages'][0]['content']
    assert 'source_search' not in disabled.json()['events'][-1]['call']
    monkeypatch.setattr(search, 'api_key', key)
    data = payload(env)
    data['ai']['web_search'] = True
    on = trial(env, prepare(env, data))
    enabled = action(env, on, 'confirm', DRAFT)
    assert enabled.status_code == 200, enabled.text
    assert sent[1]['messages'][0]['content'] == sent[0]['messages'][0]['content'] + '\n\n' + search.RULES
    assert enabled.json()['config']['ai']['prompt'] == disabled.json()['config']['ai']['prompt']
    assert enabled.json()['events'][-1]['call']['source_search']['status'] == 'not_needed'


def test_admin_policy_is_private_and_teacher_cannot_bypass_availability(env, monkeypatch):
    async def connections():
        return True, ['https://api.deepseek.com/v1'], ['private-test-key'], {}

    monkeypatch.setattr('open_webui.routers.openai.get_openai_runtime_config', connections)
    UserContext.current_user = env.teacher
    assert (
        env.client.put('/api/v1/admin/teaching-search', json={'enabled': True, 'connection_index': 0}).status_code
        == 401
    )
    data = payload(env)
    data['ai']['web_search'] = True
    prep = prepare(env, data)
    assert publish(env, prep).status_code == 409
    UserContext.current_user = env.teacher.model_copy(update={'role': 'admin'})
    response = env.client.put('/api/v1/admin/teaching-search', json={'enabled': True, 'connection_index': 0})
    assert response.status_code == 200
    assert 'private-test-key' not in env.client.get('/api/v1/admin/teaching-search').text
    assert (
        env.client.put('/api/v1/admin/teaching-search', json={'enabled': True, 'connection_index': 99}).status_code
        == 400
    )
    UserContext.current_user = env.teacher
    assert publish(env, prep).status_code == 200
    UserContext.current_user = env.student
    assert env.client.get('/api/v1/teacher/teaching-models').status_code == 403


def test_boolean_is_strict_and_responses_tool_calls_survive_roundtrip():
    from open_webui.routers.openai import convert_responses_result, convert_to_responses_payload
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AiCandidate(prompt='教师提示', model_id='A', template_version=1, web_search='false')
    output = [{'type': 'function_call', 'call_id': 'c', 'name': 'search_sources', 'arguments': '{"query":"text"}'}]
    result = convert_responses_result({'output': output})
    message = result['choices'][0]['message']
    assert result['choices'][0]['finish_reason'] == 'tool_calls'
    converted = convert_to_responses_payload(
        {'messages': [message, {'role': 'tool', 'tool_call_id': 'c', 'content': '{}'}]}
    )
    assert converted['input'][0]['call_id'] == 'c'
    assert converted['input'][1]['type'] == 'function_call_output'


def test_admin_disabling_service_continues_teaching_without_lookup(monkeypatch):
    async def unavailable():
        return None

    sent = []

    async def model(**kwargs):
        sent.append(kwargs['form_data'])
        return reply()

    monkeypatch.setattr(search, 'api_key', unavailable)
    req = request()
    asyncio.run(search.execute(req, None, body(), model))
    assert len(sent) == 1 and 'tools' not in sent[0]
    assert '不得声称已联网核验' in sent[0]['messages'][0]['content']
    assert req.state.teaching_evidence['source_search']['status'] == 'unavailable'


def test_page_budget_and_truncation_are_explicit(monkeypatch):
    operations = []

    async def post(client, credential, operation, data):
        operations.append(operation)
        return {'content': 'a' * (search.MAX_CONTENT + 10)}

    monkeypatch.setattr(search, 'post_tool', post)
    tools = search.SourceTools(None, 'not-stored', {'calls': []})
    tools.urls.add('https://example.org/book')

    async def run():
        return [
            await tools.fetch(search.FetchArguments(url='https://example.org/book', quote='missing')) for _ in range(4)
        ]

    results = asyncio.run(run())
    assert operations == ['fetch'] * 3
    assert results[0]['content_truncated'] is True
    assert len(results[0]['content']) == search.MAX_CONTENT
    assert results[0]['quote_found_in_returned_text'] is False
    assert results[3]['error'] == 'fetch_budget_exhausted'


def test_cancellation_keeps_search_evidence(monkeypatch):
    monkeypatch.setattr(search, 'api_key', key)

    async def model(**kwargs):
        raise asyncio.CancelledError()

    req = request()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(search.execute(req, None, body(), model))
    assert req.state.teaching_evidence['source_search']['status'] == 'interrupted'


def test_formal_version_can_disable_search_without_rewriting_prior_evidence(env, monkeypatch):
    from open_webui.models.teaching_trials import TeachingCall
    from open_webui.services.education import ai_steps

    monkeypatch.setattr(search, 'api_key', key)
    monkeypatch.setattr(ai_steps, 'generate_chat_completion', env.real_generate)
    sent = []

    async def model(**kwargs):
        data = kwargs['form_data']
        sent.append(copy.deepcopy(data))
        if data.get('tools') and not any(m['role'] == 'tool' for m in data['messages']):
            return reply('', [tool('search_sources', {'query': '出处'})])
        return reply()

    async def post(*args):
        return {'results': [{'url': 'https://example.org/source', 'title': '来源', 'content': '原文'}]}

    monkeypatch.setattr('open_webui.utils.chat.generate_openai_chat_completion', model)
    monkeypatch.setattr(search, 'post_tool', post)
    data = payload(env)
    data['ai']['web_search'] = True
    assignment = publish(env, prepare(env, data)).json()[0]
    sid = student_session(env, assignment)
    first = env.client.post(
        f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read', 'model_id': 'model-A'}
    )
    assert first.status_code == 200, first.text
    context = first.json()['context']
    assert context['source_search']['calls'][0]['result']['sources'][0]['content'] == '原文'
    original_context = copy.deepcopy(context)
    data['ai']['web_search'] = False
    prep = prepare(env, data, assignment['id'])
    assert publish(env, prep, assignment['config_revision']).status_code == 200
    UserContext.current_user = env.student
    last = env.client.post(
        f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'whole_review', 'model_id': 'model-A'}
    )
    assert last.status_code == 200, last.text
    assert 'source_search' not in last.json()['context']
    assert not sent[-1].get('tools') and search.RULES not in sent[-1]['messages'][0]['content']
    with env.factory() as db:
        assert db.get(TeachingCall, context['call_id']).context['source_search'] == original_context['source_search']
