"""统一思考档位：按连接翻译成服务商字段，没勾「思考控制」的模型不发出去。"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.routers.openai as openai_router
from open_webui.utils.thinking import (
    ANTHROPIC_ANSWER_TOKENS,
    THINKING_BUDGET_TOKENS,
    apply_thinking_level,
    detect_thinking_format,
)


@pytest.mark.parametrize(
    ('url', 'api_config', 'expected'),
    [
        ('https://api.anthropic.com/v1', {}, 'anthropic'),
        ('https://openrouter.ai/api/v1', {}, 'openrouter'),
        ('https://dashscope.aliyuncs.com/compatible-mode/v1', {}, 'qwen'),
        ('https://api.deepseek.com/v1', {}, 'thinking_type'),
        ('https://ark.cn-beijing.volces.com/api/v3', {}, 'thinking_type'),
        ('https://open.bigmodel.cn/api/paas/v4', {}, 'thinking_type'),
        ('https://api.openai.com/v1', {}, 'openai'),
        ('http://localhost:8000/v1', {}, 'openai'),
        ('http://localhost:8000/v1', {'thinking_format': 'chat_template'}, 'chat_template'),
        ('https://api.anthropic.com/v1', {'thinking_format': 'openai'}, 'openai'),
    ],
)
def test_thinking_format_comes_from_connection_or_url(url, api_config, expected):
    assert detect_thinking_format(url, api_config) == expected


def test_openai_format_uses_reasoning_effort_and_minimal_for_off():
    assert apply_thinking_level({}, 'high', 'openai') == {'reasoning_effort': 'high'}
    assert apply_thinking_level({}, 'off', 'openai') == {'reasoning_effort': 'minimal'}
    assert apply_thinking_level({}, 'low', 'openai', responses_api=True) == {'reasoning': {'effort': 'low'}}


def test_anthropic_format_sets_budget_and_room_for_the_answer():
    payload = apply_thinking_level({'max_tokens': 2000, 'temperature': 0.3, 'top_p': 0.9}, 'medium', 'anthropic')

    budget = THINKING_BUDGET_TOKENS['medium']
    assert payload == {
        'thinking': {'type': 'enabled', 'budget_tokens': budget},
        'max_tokens': budget + ANTHROPIC_ANSWER_TOKENS,
    }
    assert apply_thinking_level({'max_tokens': 64000}, 'low', 'anthropic')['max_tokens'] == 64000
    assert apply_thinking_level({'temperature': 0.3}, 'off', 'anthropic') == {
        'temperature': 0.3,
        'thinking': {'type': 'disabled'},
    }


def test_other_formats():
    assert apply_thinking_level({}, 'off', 'qwen') == {'enable_thinking': False}
    assert apply_thinking_level({}, 'high', 'qwen') == {
        'enable_thinking': True,
        'thinking_budget': THINKING_BUDGET_TOKENS['high'],
    }
    assert apply_thinking_level({'chat_template_kwargs': {'x': 1}}, 'off', 'chat_template') == {
        'chat_template_kwargs': {'x': 1, 'enable_thinking': False}
    }
    assert apply_thinking_level({}, 'low', 'thinking_type') == {'thinking': {'type': 'enabled'}}
    assert apply_thinking_level({}, 'off', 'thinking_type') == {'thinking': {'type': 'disabled'}}
    assert apply_thinking_level({}, 'medium', 'openrouter') == {'reasoning': {'effort': 'medium'}}
    assert apply_thinking_level({}, 'off', 'openrouter') == {'reasoning': {'enabled': False}}


class _Sent(Exception):
    pass


def _send_through_router(monkeypatch, *, saved_params, capabilities, url, api_config=None, body_extra=None):
    """跑一遍 OpenAI 兼容路由，返回路由抛出的错误和截下的服务商请求体（没发出去时为 None）。"""
    sent = {}

    class FakeSession:
        async def request(self, **kwargs):
            sent['body'] = json.loads(kwargs['data'])
            raise _Sent

    async def fake_session():
        return FakeSession()

    async def config_get(key, default=None):
        return True

    async def model_by_id(model_id):
        return SimpleNamespace(
            base_model_id=None,
            params=SimpleNamespace(model_dump=lambda: dict(saved_params)),
            meta=SimpleNamespace(capabilities=capabilities),
        )

    async def no_check(*args, **kwargs):
        return None

    async def connection(idx):
        return url, 'key', dict(api_config or {})

    async def headers_and_cookies(*args, **kwargs):
        return {}, {}

    monkeypatch.setattr(openai_router, 'Config', SimpleNamespace(get=config_get))
    monkeypatch.setattr(openai_router.Models, 'get_model_by_id', model_by_id)
    monkeypatch.setattr(openai_router, 'check_model_access', no_check)
    monkeypatch.setattr(openai_router, 'get_openai_connection', connection)
    monkeypatch.setattr(openai_router, 'get_headers_and_cookies', headers_and_cookies)
    monkeypatch.setattr(openai_router, 'get_session', fake_session)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={'qwen-plus': {'urlIdx': 0}})),
        state=SimpleNamespace(),
    )
    body = {'model': 'qwen-plus', 'messages': [{'role': 'user', 'content': 'hi'}], **(body_extra or {})}
    user = SimpleNamespace(id='u-1', name='U', email='u@example.com', role='user')
    with pytest.raises(HTTPException) as error:
        asyncio.run(openai_router.generate_chat_completion(request, body, user))
    return error.value, sent.get('body')


def test_router_translates_saved_level_for_capable_models(monkeypatch):
    _, body = _send_through_router(
        monkeypatch,
        saved_params={'thinking_level': 'off'},
        capabilities={'reasoning': True},
        url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

    assert body['enable_thinking'] is False
    assert 'thinking_level' not in body


def test_request_level_wins_over_saved_level(monkeypatch):
    _, body = _send_through_router(
        monkeypatch,
        saved_params={'thinking_level': 'off'},
        capabilities={'reasoning': True},
        url='http://localhost:8000/v1',
        body_extra={'thinking_level': 'high'},
    )

    assert body['reasoning_effort'] == 'high'


def test_router_drops_level_for_models_without_the_capability(monkeypatch):
    _, body = _send_through_router(
        monkeypatch,
        saved_params={'thinking_level': 'off'},
        capabilities={},
        url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

    assert 'thinking_level' not in body and 'enable_thinking' not in body


def test_router_rejects_unknown_levels(monkeypatch):
    error, body = _send_through_router(
        monkeypatch,
        saved_params={},
        capabilities={'reasoning': True},
        url='http://localhost:8000/v1',
        body_extra={'thinking_level': 'max'},
    )
    assert error.status_code == 400 and body is None
