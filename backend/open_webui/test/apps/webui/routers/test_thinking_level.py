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
    fixed_sampling_params,
    ThinkingSupport,
    effective_thinking_level,
    strip_fixed_sampling_params,
    thinking_support,
)


@pytest.mark.parametrize(
    ('url', 'api_config', 'expected'),
    [
        ('https://api.anthropic.com/v1', {}, 'anthropic'),
        ('https://openrouter.ai/api/v1', {}, 'openrouter'),
        ('https://dashscope.aliyuncs.com/compatible-mode/v1', {}, 'qwen'),
        ('https://ws-1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1', {}, 'qwen'),
        ('https://api.deepseek.com', {}, 'deepseek'),
        ('https://api.moonshot.cn/v1', {}, 'kimi'),
        ('https://api.moonshot.ai/v1', {}, 'kimi'),
        ('https://ark.cn-beijing.volces.com/api/v3', {}, 'doubao'),
        ('https://open.bigmodel.cn/api/paas/v4', {}, 'zhipu'),
        ('https://api.z.ai/api/paas/v4', {}, 'zhipu'),
        # 按主机名后缀认,不靠子串:这些都不是对应服务商
        ('https://notdeepseek.com.example.org/v1', {}, 'openai'),
        ('https://openai.azure.com/openai/v1', {}, 'openai'),
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


def _levels(thinking_format, model=''):
    return {
        level: apply_thinking_level({'model': model} if model else {}, level, thinking_format)
        for level in ('off', 'low', 'medium', 'high')
    }


def test_deepseek_turns_thinking_off_and_maps_three_efforts():
    """实测:disabled 真的关掉;effort 只有 low / high / max,medium 落到 high。"""
    assert _levels('deepseek') == {
        'off': {'thinking': {'type': 'disabled'}},
        'low': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'low'},
        'medium': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
        'high': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'max'},
    }


def test_kimi_disables_with_thinking_type_and_levels_with_effort():
    """实测:K3 认 thinking.type=disabled,按 reasoning_effort 分档;不发 enabled。"""
    assert _levels('kimi', 'kimi-k3') == {
        'off': {'model': 'kimi-k3', 'thinking': {'type': 'disabled'}},
        'low': {'model': 'kimi-k3', 'reasoning_effort': 'low'},
        'medium': {'model': 'kimi-k3', 'reasoning_effort': 'high'},
        'high': {'model': 'kimi-k3', 'reasoning_effort': 'max'},
    }


def test_kimi_k26_only_turns_thinking_on_or_off():
    """实测:K2.6 收 reasoning_effort 不报错但看不出效果;各档都发 thinking.type=enabled(实测 200)。"""
    assert thinking_support('kimi', 'kimi-k2.6').graded is False
    assert _levels('kimi', 'kimi-k2.6') == {
        'off': {'model': 'kimi-k2.6', 'thinking': {'type': 'disabled'}},
        'low': {'model': 'kimi-k2.6', 'thinking': {'type': 'enabled'}},
        'medium': {'model': 'kimi-k2.6', 'thinking': {'type': 'enabled'}},
        'high': {'model': 'kimi-k2.6', 'thinking': {'type': 'enabled'}},
    }


def test_thinking_support_table():
    assert thinking_support('kimi', 'kimi-k3').graded is True
    assert thinking_support('zhipu', 'glm-5.3-flash') == ThinkingSupport(can_turn_off=False, graded=True)
    assert thinking_support('zhipu', 'glm-4.6').graded is False
    assert thinking_support('chat_template', 'qwen3-8b').graded is False
    assert thinking_support('deepseek', 'deepseek-flash').graded is True
    assert thinking_support('openai', None).graded is True


def test_model_list_carries_thinking_support(monkeypatch):
    """模型列表里每个模型带着同一张表算出的 thinking_support,界面据此提示;前缀 id 按去掉前缀后的判断。"""

    async def runtime_config():
        return (
            True,
            ['https://api.moonshot.cn/v1', 'https://api.deepseek.com'],
            ['k1', 'k2'],
            {'0': {'prefix_id': 'moon'}},
        )

    async def responses(request, user=None):
        return [
            {'data': [{'id': 'moon.kimi-k2.6'}, {'id': 'moon.kimi-k3'}]},
            {'data': [{'id': 'deepseek-flash'}]},
        ]

    monkeypatch.setattr(openai_router, 'get_openai_runtime_config', runtime_config)
    monkeypatch.setattr(openai_router, 'get_all_models_responses', responses)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    models = asyncio.run(openai_router.get_all_models.__wrapped__(request, None))['data']

    assert {model['id']: model['thinking_support'] for model in models} == {
        'moon.kimi-k2.6': {'can_turn_off': True, 'graded': False},
        'moon.kimi-k3': {'can_turn_off': True, 'graded': True},
        'deepseek-flash': {'can_turn_off': True, 'graded': True},
    }


def test_zhipu_never_disables_always_thinking_models():
    """实测:GLM-5.3 系列传 disabled 返回 400(code 1210),medium 也报错;关不掉时退到 low。"""
    for model in ('glm-5.3', 'glm-5.3-flash', 'GLM-5.3-FlashX'):
        assert _levels('zhipu', model) == {
            'off': {'model': model, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'low'},
            'low': {'model': model, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'low'},
            'medium': {'model': model, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
            'high': {'model': model, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'max'},
        }
    # GLM-5.2 可以关,也接受 effort
    assert apply_thinking_level({'model': 'glm-5.2'}, 'off', 'zhipu') == {
        'model': 'glm-5.2',
        'thinking': {'type': 'disabled'},
    }
    assert apply_thinking_level({'model': 'glm-5.2'}, 'low', 'zhipu')['reasoning_effort'] == 'low'
    # 更早的型号只有开 / 关,不发 effort
    assert apply_thinking_level({'model': 'glm-4.6'}, 'high', 'zhipu') == {
        'model': 'glm-4.6',
        'thinking': {'type': 'enabled'},
    }


@pytest.mark.parametrize(
    ('thinking_format', 'model'),
    [('zhipu', 'glm-4.7'), ('zhipu', 'glm-4.5v'), ('kimi', 'kimi-k2.7-code'), ('kimi', 'kimi-k2.7-code-highspeed')],
)
def test_always_thinking_models_without_levels_get_nothing(thinking_format, model):
    """始终思考又没有档位:没什么可调,各档都按模型默认、什么也不发,从不发会 400 的 disabled。"""
    support = thinking_support(thinking_format, model)
    assert (support.can_turn_off, support.graded) == (False, False)
    assert set(map(str, _levels(thinking_format, model).values())) == {str({'model': model})}


def test_effective_level():
    always_graded = ThinkingSupport(can_turn_off=False)
    always_flat = ThinkingSupport(can_turn_off=False, graded=False)
    assert [effective_thinking_level(level, always_graded) for level in ('off', 'low', 'high', 'model_default')] == [
        'low',
        'low',
        'high',
        'model_default',
    ]
    assert {effective_thinking_level(level, always_flat) for level in ('off', 'low', 'high')} == {'model_default'}
    assert effective_thinking_level('off', ThinkingSupport()) == 'off'


def test_doubao_and_qwen_follow_their_docs():
    assert _levels('doubao') == {
        'off': {'thinking': {'type': 'disabled'}},
        'low': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'low'},
        'medium': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'medium'},
        'high': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }
    assert _levels('qwen') == {
        'off': {'enable_thinking': False},
        'low': {'enable_thinking': True, 'thinking_budget': THINKING_BUDGET_TOKENS['low']},
        'medium': {'enable_thinking': True, 'thinking_budget': THINKING_BUDGET_TOKENS['medium']},
        # 高档不设预算,用模型上限
        'high': {'enable_thinking': True},
    }


def test_other_formats():
    assert apply_thinking_level({'chat_template_kwargs': {'x': 1}}, 'off', 'chat_template') == {
        'chat_template_kwargs': {'x': 1, 'enable_thinking': False}
    }
    assert apply_thinking_level({}, 'medium', 'openrouter') == {'reasoning': {'effort': 'medium'}}
    assert apply_thinking_level({}, 'off', 'openrouter') == {'reasoning': {'enabled': False}}


class _Sent(Exception):
    pass


def _send_through_router(
    monkeypatch, *, saved_params, capabilities, url, api_config=None, body_extra=None, model='qwen-plus'
):
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
        app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={model: {'urlIdx': 0}})),
        state=SimpleNamespace(),
    )
    body = {'model': model, 'messages': [{'role': 'user', 'content': 'hi'}], **(body_extra or {})}
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


KIMI_RULES = [
    {'param': 'temperature', 'allowed': 1.0, 'allowed_without_thinking': 0.6},
    {'param': 'top_p', 'allowed': 0.95, 'allowed_without_thinking': None},
    {'param': 'n', 'allowed': 1, 'allowed_without_thinking': None},
    {'param': 'presence_penalty', 'allowed': 0, 'allowed_without_thinking': None},
    {'param': 'frequency_penalty', 'allowed': 0, 'allowed_without_thinking': None},
]


def test_kimi_fixed_sampling_params_follow_the_tests():
    """实测(K2.6、K3 一样):temperature 开思考只能 1、关思考只能 0.6;top_p 只能 0.95;n 只能 1;两个 penalty 只能 0。"""
    assert [rule._asdict() for rule in fixed_sampling_params('kimi')] == KIMI_RULES
    assert fixed_sampling_params('deepseek') == []


def test_strip_drops_every_fixed_param_on_kimi():
    payload = {
        'model': 'kimi-k2.6',
        'temperature': 0.3,
        'top_p': 0.9,
        'n': 2,
        'presence_penalty': 0.5,
        'frequency_penalty': 0.5,
        'max_tokens': 100,
    }
    assert strip_fixed_sampling_params(payload, 'kimi') == (
        {'model': 'kimi-k2.6', 'max_tokens': 100},
        ['temperature', 'top_p', 'n', 'presence_penalty', 'frequency_penalty'],
    )
    # 恰好等于开思考时的值也不发:关掉思考时 temperature=1 同样 400(只能 0.6)
    off = {'model': 'kimi-k3', 'thinking': {'type': 'disabled'}, 'temperature': 1, 'top_p': 0.95}
    assert strip_fixed_sampling_params(off, 'kimi') == (
        {'model': 'kimi-k3', 'thinking': {'type': 'disabled'}},
        ['temperature', 'top_p'],
    )
    other = {'model': 'deepseek-flash', 'temperature': 0.3, 'n': 2}
    assert strip_fixed_sampling_params(other, 'deepseek') == (other, [])


def test_router_drops_kimi_sampling_params_before_sending(monkeypatch):
    _, body = _send_through_router(
        monkeypatch,
        saved_params={'temperature': 0.3, 'top_p': 0.9, 'frequency_penalty': 0.5},
        capabilities={},
        url='https://api.moonshot.cn/v1',
        model='kimi-k2.6',
    )
    assert not {'temperature', 'top_p', 'frequency_penalty'} & set(body)


def test_sampling_rules_endpoint_reads_the_same_table(monkeypatch):
    async def model_by_id(model_id):
        return SimpleNamespace(base_model_id='kimi-k2.6') if model_id == 'tutor' else None

    async def connection(idx):
        return 'https://api.moonshot.cn/v1', 'key', {}

    monkeypatch.setattr(openai_router.Models, 'get_model_by_id', model_by_id)
    monkeypatch.setattr(openai_router, 'get_openai_connection', connection)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={'kimi-k2.6': {'urlIdx': 3}, 'kimi-k3': {'urlIdx': 3}}))
    )
    rules = lambda **form: asyncio.run(  # noqa: E731
        openai_router.get_sampling_rules(request, openai_router.SamplingRulesForm(**form), None)
    )

    # 自建模型按底模判断
    assert rules(model_id='tutor') == {'thinking_format': 'kimi', 'rules': KIMI_RULES}
    assert rules(model_id='kimi-k3')['rules'] == KIMI_RULES
    # 新建连接时按地址 / 手选的格式
    assert rules(url='https://api.moonshot.ai/v1')['thinking_format'] == 'kimi'
    assert rules(url='https://api.deepseek.com')['rules'] == []
    assert rules(url='https://example.com/v1', thinking_format='kimi')['thinking_format'] == 'kimi'
