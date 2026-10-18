"""教学模块的模型调用都登记为 AI 步骤：静态核对每处调用写明了登记过的步骤，档位按步骤发出。"""

import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.services.education.ai_steps as ai_steps
from open_webui.config import DEFAULT_EDUCATION_AI_STEPS
from open_webui.services.education.ai_steps import (
    AI_STEPS,
    EducationAiStepPolicy,
    StepModel,
    call_step_model,
    describe_steps,
    resolve_step_model,
)

OPEN_WEBUI = BACKEND_ROOT / 'open_webui'
EDUCATION_SOURCES = sorted((OPEN_WEBUI / 'services' / 'education').glob('*.py')) + [
    OPEN_WEBUI / 'routers' / 'education.py'
]
# 接受步骤参数的模型调用出口，以及步骤参数的位置（从 0 数）。
STEP_CALLS = {'call_step_model': 2, 'generate_completion': 4, 'resolve_step_model': 2}
PLATFORM_STEPS = {step.key for step in AI_STEPS} - {'coaching_chat'}


def _called_name(call: ast.Call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _step_argument(call: ast.Call, position: int):
    for keyword in call.keywords:
        if keyword.arg == 'step':
            return keyword.value
    return call.args[position] if len(call.args) > position else None


def _trees():
    for path in EDUCATION_SOURCES:
        yield path, ast.parse(path.read_text(encoding='utf-8'))


def test_only_ai_steps_calls_the_chat_completion_directly():
    for path, tree in _trees():
        if path.name == 'ai_steps.py':
            continue
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        assert 'generate_chat_completion' not in names, f'{path.name} calls the model without an AI step'


def test_every_model_call_names_a_registered_step():
    used_steps = set()
    for path, tree in _trees():
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            name = _called_name(call)
            if name not in STEP_CALLS:
                continue
            step = _step_argument(call, STEP_CALLS[name])
            location = f'{path.name}:{call.lineno}'
            if isinstance(step, ast.Name) and step.id == 'step':
                continue  # 出口把调用方写明的步骤往下传
            assert isinstance(step, ast.Constant), f'{location} must name its AI step literally'
            assert step.value in PLATFORM_STEPS, f'{location} uses unregistered step {step.value!r}'
            used_steps.add(step.value)

    assert used_steps == PLATFORM_STEPS, 'every registered platform step needs a call site'


def _policy(**steps):
    return EducationAiStepPolicy.model_validate({**DEFAULT_EDUCATION_AI_STEPS, **steps})


def test_default_policy_is_valid_and_matches_the_registry():
    policy = _policy()

    assert policy.image_parsing.model is None and policy.image_parsing.thinking == 'off'
    assert policy.coaching_chat.control == 'admin'
    rows = describe_steps(policy, {})
    assert [row.key for row in rows] == [step.key for step in AI_STEPS]
    assert all(row.control == 'admin' and row.model_id is None and row.model_available for row in rows)
    assert {row.key: row.model_source for row in rows}['class_insight'] == 'teacher_chat_model'


@pytest.mark.parametrize(
    'change',
    [
        {'first_read': {'model': None, 'thinking': 'max'}},
        {'first_read': {'model': '', 'thinking': 'off'}},
        {'coaching_chat': {'control': 'everyone', 'default': 'off'}},
        {'coaching_chat': {'control': 'admin', 'default': 'off', 'model': 'm'}},
        {'unknown_step': {'model': None, 'thinking': 'off'}},
    ],
)
def test_policy_rejects_unknown_values(change):
    with pytest.raises(ValidationError):
        _policy(**change)


def _request(models):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS=models)))


def test_resolve_step_model_prefers_the_admin_model_and_falls_back(monkeypatch):
    request = _request({'reader-model': {'id': 'reader-model'}, 'vision-model': {'id': 'vision-model'}})
    resolve = lambda step, requested=None, **steps: asyncio.run(  # noqa: E731
        resolve_step_model(request, None, step, requested, policy=_policy(**steps))
    )

    # 管理员没指定:通读、试读跟学生选的,班级归纳跟老师选的;没选就没有
    assert resolve('first_read', 'student-model') == StepModel(model_id='student-model', fixed=False)
    assert resolve('class_insight', 'teacher-model') == StepModel(model_id='teacher-model', fixed=False)
    assert resolve('reader_check') is None
    # 指定了就用指定的,标为 fixed(跳过学生的模型访问控制)
    assert resolve(
        'reader_check', 'student-model', reader_check={'model': 'reader-model', 'thinking': 'low'}
    ) == StepModel(model_id='reader-model', fixed=True)
    # 指定的已被删掉:回落到学生选的
    assert resolve(
        'reader_check', 'student-model', reader_check={'model': 'gone', 'thinking': 'low'}
    ) == StepModel(model_id='student-model', fixed=False)
    # 图片识别没有回落
    assert resolve('image_parsing', 'student-model') is None
    assert resolve('image_parsing', image_parsing={'model': 'gone', 'thinking': 'off'}) is None
    assert resolve('image_parsing', image_parsing={'model': 'vision-model', 'thinking': 'off'}) == StepModel(
        model_id='vision-model', fixed=True
    )


def test_describe_steps_flags_missing_models():
    rows = {
        row.key: row
        for row in describe_steps(
            _policy(
                reader_check={'model': 'gone', 'thinking': 'low'},
                image_parsing={'model': 'vision-model', 'thinking': 'off'},
            ),
            {'vision-model': {'id': 'vision-model', 'name': 'Vision'}},
        )
    }

    assert (rows['reader_check'].model_id, rows['reader_check'].model_available) == ('gone', False)
    assert (rows['image_parsing'].model_name, rows['image_parsing'].model_available) == ('Vision', True)


def test_call_step_model_sends_the_step_setting(monkeypatch):
    sent = []
    policy = _policy(
        first_read={'model': None, 'thinking': 'high'}, reader_check={'model': None, 'thinking': 'model_default'}
    )

    async def fake_policy():
        return policy

    async def fake_generate(request, form_data, user, bypass_filter=False):
        sent.append((form_data, bypass_filter))
        return {'ok': True}

    monkeypatch.setattr(ai_steps, 'get_ai_step_policy', fake_policy)
    monkeypatch.setattr(ai_steps, 'generate_chat_completion', fake_generate)
    messages = [{'role': 'user', 'content': 'hi'}]

    asyncio.run(call_step_model(None, None, 'first_read', StepModel(model_id='m', fixed=False), messages))
    asyncio.run(call_step_model(None, None, 'reader_check', StepModel(model_id='m', fixed=False), messages))
    asyncio.run(call_step_model(None, None, 'image_parsing', StepModel(model_id='vision', fixed=True), messages))

    assert sent[0] == ({'model': 'm', 'messages': messages, 'stream': False, 'thinking_level': 'high'}, False)
    assert 'thinking_level' not in sent[1][0]
    # 管理员指定的模型跳过模型访问控制
    assert sent[2][0]['thinking_level'] == 'off' and sent[2][1] is True


def test_student_status_follows_default_and_student_group(monkeypatch):
    """组权限只能往上加：默认开着时，在学生组里关掉也不算收回。"""
    from types import SimpleNamespace

    import open_webui.utils.access_control.chat as chat_access

    state = {'defaults': {}, 'group': {}}

    async def config_get(key, default=None):
        return state['defaults']

    async def group_by_id(group_id, db=None):
        return SimpleNamespace(permissions=state['group'])

    monkeypatch.setattr(chat_access.Config, 'get', config_get)
    monkeypatch.setattr(chat_access.Groups, 'get_group_by_id', group_by_id)
    status = lambda: asyncio.run(chat_access.get_group_chat_overrides('education-student'))  # noqa: E731

    assert status() == chat_access.ALL_CHAT_OVERRIDES
    state['group'] = {'chat': {'params': False, 'system_prompt': False}}
    assert status() == chat_access.ALL_CHAT_OVERRIDES
    state['defaults'] = {'chat': {'params': False, 'system_prompt': False}}
    assert status() == chat_access.NO_CHAT_OVERRIDES
    state['group'] = {'chat': {'params': True}}
    assert status() == chat_access.ChatOverrides(params=True, system_prompt=False)
