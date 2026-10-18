"""辅导对话的思考档位：管理员决定交给谁，教师按作业设，学生只在允许时关掉；平台步骤不受影响。"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.config import DEFAULT_EDUCATION_AI_STEPS
from open_webui.models.chats import Chat
from open_webui.models.config import Config
from open_webui.models.education import AssignmentModelParams, Submission
from open_webui.services.education.ai_steps import (
    EducationAiStepPolicy,
    ModelParamsNotAllowed,
    ensure_model_params_allowed,
    resolve_coaching_thinking,
)
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    _rubric_schema,
    _submit_body,
    education_client,  # noqa: F401  pytest fixture
)


def _policy(control='admin', default='model_default', **steps):
    return {**DEFAULT_EDUCATION_AI_STEPS, **steps, 'coaching_chat': {'control': control, 'default': default}}


def _set_policy(**kwargs):
    asyncio.run(Config.upsert({'education.ai_steps': _policy(**kwargs)}))


def _params(**kwargs):
    return AssignmentModelParams(**kwargs)


@pytest.mark.parametrize(
    ('control', 'params', 'student_choice', 'expected'),
    [
        ('admin', {'thinking': 'off'}, None, ('high', 'admin', False)),
        ('teacher', {}, None, ('high', 'admin', False)),
        ('teacher', {'thinking': 'off'}, None, ('off', 'teacher', False)),
        # 管理员没允许学生开关：作业里存的开关不生效，学生请求关掉也不理
        ('teacher', {'thinking': 'low', 'students_choose_thinking': True}, 'off', ('low', 'teacher', False)),
        ('student', {'thinking': 'low', 'students_choose_thinking': True}, None, ('low', 'teacher', True)),
        ('student', {'thinking': 'low', 'students_choose_thinking': True}, 'off', ('off', 'student', True)),
        # 学生只能关，不能自己挑档位
        ('student', {'thinking': 'low', 'students_choose_thinking': True}, 'high', ('low', 'teacher', True)),
        ('student', {'thinking': 'low'}, 'off', ('low', 'teacher', False)),
    ],
)
def test_resolve_coaching_thinking(control, params, student_choice, expected):
    policy = EducationAiStepPolicy.model_validate(_policy(control=control, default='high'))
    # 构造时绕过「学生开关须写明开的档位」的校验，单测解读规则
    resolved = resolve_coaching_thinking(policy, AssignmentModelParams.model_construct(**params), student_choice)

    assert (resolved.level, resolved.source, resolved.students_choose) == expected


def test_students_switch_needs_an_on_level():
    with pytest.raises(ValidationError):
        _params(students_choose_thinking=True)
    with pytest.raises(ValidationError):
        _params(thinking='off', students_choose_thinking=True)
    with pytest.raises(ValidationError):
        AssignmentModelParams.model_validate({'thinking': 'max'})


def test_teachers_set_only_what_was_delegated():
    def check(control, **params):
        ensure_model_params_allowed(_params(**params), EducationAiStepPolicy.model_validate(_policy(control=control)))

    check('admin')
    with pytest.raises(ModelParamsNotAllowed):
        check('admin', thinking='off')
    check('teacher', thinking='off')
    with pytest.raises(ModelParamsNotAllowed):
        check('teacher', thinking='low', students_choose_thinking=True)
    check('student', thinking='low', students_choose_thinking=True)


def _create_assignment(client, teacher, model_params=None, title='Thinking Essay'):
    UserContext.current_user = teacher
    classroom = client.post('/api/v1/classrooms', json={'name': f'CR {title}'}).json()['classroom']
    body = {
        'title': title,
        'classroom_ids': [classroom['id']],
        'due_at': 2000000000,
        'score_max': 100,
        'rubric_schema': _rubric_schema(100),
        **({'model_params': model_params} if model_params is not None else {}),
    }
    return classroom, client.post('/api/v1/assignments', json=body)


def _open_workspace(client, student, classroom, assignment_id):
    UserContext.current_user = student
    client.post('/api/v1/classrooms/join', json={'invite_code': classroom['invite_code']})
    res = client.get(f'/api/v1/assignments/{assignment_id}/workspace')
    assert res.status_code == 200, res.text
    return res.json()


def test_assignment_api_follows_the_delegation(education_client):
    client, teacher, _, _, _, _ = education_client

    UserContext.current_user = teacher
    assert client.get('/api/v1/teacher/assignment-defaults').json()['thinking'] == {
        'control': 'admin',
        'default': 'model_default',
    }
    _, res = _create_assignment(client, teacher, {'thinking': 'off'}, title='Locked')
    assert res.status_code == 400, res.text
    _, res = _create_assignment(client, teacher, title='Default')
    assert res.status_code == 200, res.text
    assert res.json()[0]['model_params'] == {'thinking': None, 'students_choose_thinking': False}

    _set_policy(control='teacher')
    _, res = _create_assignment(client, teacher, {'thinking': 'off'}, title='Teacher')
    assert res.status_code == 200, res.text
    assignment_id = res.json()[0]['id']
    _, res = _create_assignment(client, teacher, {'thinking': 'low', 'students_choose_thinking': True}, title='Not yet')
    assert res.status_code == 400, res.text

    patch = client.patch(
        f'/api/v1/assignments/{assignment_id}',
        json={'model_params': {'thinking': 'high', 'students_choose_thinking': True}},
    )
    assert patch.status_code == 400, patch.text
    patch = client.patch(f'/api/v1/assignments/{assignment_id}', json={'model_params': {'thinking': 'high'}})
    assert patch.status_code == 200, patch.text
    assert patch.json()['model_params']['thinking'] == 'high'


def test_ai_settings_card_shows_what_applies_now(education_client):
    client, teacher, _, _, _, _ = education_client
    _set_policy(control='teacher', default='medium', first_read={'model': None, 'thinking': 'high'})
    _, res = _create_assignment(client, teacher, {'thinking': 'off'})
    assignment_id = res.json()[0]['id']

    client.app.state.MODELS = {'insight-model': {'id': 'insight-model', 'name': 'Insight'}}
    asyncio.run(
        Config.upsert(
            {
                'education.ai_steps': _policy(
                    control='teacher',
                    default='medium',
                    first_read={'model': None, 'thinking': 'high'},
                    class_insight={'model': 'insight-model', 'thinking': 'low'},
                    reader_check={'model': 'gone-model', 'thinking': 'model_default'},
                )
            }
        )
    )
    card = client.get(f'/api/v1/teacher/assignments/{assignment_id}/ai-settings').json()
    rows = {row['key']: row for row in card['steps']}
    assert rows['coaching_chat'] == {
        'key': 'coaching_chat',
        'model_source': 'student_chat_model',
        'model_id': None,
        'model_name': None,
        'model_available': True,
        'control': 'teacher',
        'thinking': 'off',
    }
    # 管理员指定的模型连同名称显示;指定的已被删掉时标出,这一步回落到学生选的模型
    assert (rows['class_insight']['model_name'], rows['class_insight']['model_available']) == ('Insight', True)
    assert (rows['reader_check']['model_id'], rows['reader_check']['model_available']) == ('gone-model', False)
    assert (rows['first_read']['control'], rows['first_read']['thinking']) == ('admin', 'high')
    assert rows['image_parsing']['thinking'] == 'off'

    # 管理员收回下放：作业里存的不再生效，立即回到管理员默认
    _set_policy(control='admin', default='medium')
    card = client.get(f'/api/v1/teacher/assignments/{assignment_id}/ai-settings').json()
    assert card['coaching_thinking'] == {
        'control': 'admin',
        'level': 'medium',
        'source': 'admin',
        'students_choose': False,
    }


def test_workspace_and_submission_record_the_thinking_setting(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    _set_policy(control='student')
    classroom, res = _create_assignment(client, teacher, {'thinking': 'low', 'students_choose_thinking': True})
    assignment_id = res.json()[0]['id']

    workspace = _open_workspace(client, student, classroom, assignment_id)
    assert workspace['can_switch_thinking'] is True

    submit = client.post(
        f'/api/v1/assignments/{assignment_id}/submit',
        json=_submit_body(workspace['writing_session']['id'], 'essay text for the thinking round'),
    )
    assert submit.status_code == 200, submit.text
    with SessionLocal() as db:
        stats = db.get(Submission, submit.json()['submission_id']).stats_json
    assert stats['coaching']['thinking'] == {
        'control': 'student',
        'level': 'low',
        'source': 'teacher',
        'students_choose': True,
    }

    _set_policy(control='teacher')
    UserContext.current_user = student
    workspace = client.get(f'/api/v1/assignments/{assignment_id}/workspace').json()
    assert workspace['can_switch_thinking'] is False


class _Stop(Exception):
    pass


def _chat_request(model_capabilities):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                MODELS={
                    'coach-model': {
                        'id': 'coach-model',
                        'info': {'meta': {'capabilities': model_capabilities}},
                    }
                }
            )
        ),
        headers={},
        state=SimpleNamespace(),
    )


def _chat_body(folder_id, thinking_level=None):
    return {
        'model': 'coach-model',
        'stream': True,
        'messages': [{'role': 'user', 'content': '帮我看看论点'}],
        'params': {**({'thinking_level': thinking_level} if thinking_level else {}), 'temperature': 1.5},
        'id': 'assistant-1',
        'user_message': {'id': 'user-1', 'role': 'user', 'content': '帮我看看论点'},
        'parent_id': None,
        'folder_id': folder_id,
    }


def _assignment_chat(education_client, monkeypatch, model_params, control):
    import open_webui.main as webui_main

    client, teacher, _, student, _, SessionLocal = education_client
    monkeypatch.setattr(internal_db, 'SessionLocal', SessionLocal)
    monkeypatch.setattr(webui_main, 'BYPASS_MODEL_ACCESS_CONTROL', True)
    _set_policy(control=control)
    classroom, res = _create_assignment(client, teacher, model_params)
    workspace = _open_workspace(client, student, classroom, res.json()[0]['id'])
    return webui_main, student, workspace['project']['id'], SessionLocal


def _sent_params(webui_main, monkeypatch, student, body, capabilities):
    """跑到参数合并为止，返回进入合并的请求参数。"""
    captured = {}
    real_merge = webui_main.merge_model_params

    def spy_merge(base, override):
        captured.setdefault('calls', []).append(override)
        if len(captured['calls']) == 2:
            raise _Stop
        return real_merge(base, override)

    monkeypatch.setattr(webui_main, 'merge_model_params', spy_merge)
    with pytest.raises(HTTPException):
        asyncio.run(webui_main.chat_completion(_chat_request(capabilities), body, student, client_request=True))
    return captured['calls'][1]


def test_assignment_chat_sends_the_assignment_level(education_client, monkeypatch):
    webui_main, student, folder_id, _ = _assignment_chat(
        education_client, monkeypatch, {'thinking': 'low', 'students_choose_thinking': True}, 'student'
    )
    capable = {'reasoning': True}

    # 其余参数照样去掉；档位按作业来
    assert _sent_params(webui_main, monkeypatch, student, _chat_body(folder_id), capable) == {'thinking_level': 'low'}
    # 学生关掉这一轮
    assert _sent_params(webui_main, monkeypatch, student, _chat_body(folder_id, 'off'), capable) == {
        'thinking_level': 'off'
    }
    # 学生不能自己调高
    assert _sent_params(webui_main, monkeypatch, student, _chat_body(folder_id, 'high'), capable) == {
        'thinking_level': 'low'
    }


def test_assignment_chat_ignores_student_switch_when_not_allowed(education_client, monkeypatch):
    webui_main, student, folder_id, _ = _assignment_chat(education_client, monkeypatch, {'thinking': 'high'}, 'teacher')

    params = _sent_params(webui_main, monkeypatch, student, _chat_body(folder_id, 'off'), {'reasoning': True})
    assert params == {'thinking_level': 'high'}


def test_reply_records_the_level_it_was_sent_with(education_client, monkeypatch):
    webui_main, student, folder_id, SessionLocal = _assignment_chat(
        education_client, monkeypatch, {'thinking': 'low', 'students_choose_thinking': True}, 'student'
    )

    async def no_event(*args, **kwargs):
        return None

    async def stop(*args, **kwargs):
        raise HTTPException(status_code=418, detail='stop after the chat is saved')

    monkeypatch.setattr(webui_main, 'publish_event', no_event)
    monkeypatch.setattr(webui_main, 'emit_chat_list_event', stop)

    def reply_meta(capabilities, thinking_level=None):
        body = _chat_body(folder_id, thinking_level)
        body['id'] = f'assistant-{uuid.uuid4()}'
        with pytest.raises(HTTPException) as error:
            asyncio.run(webui_main.chat_completion(_chat_request(capabilities), body, student, client_request=True))
        assert error.value.status_code == 418
        with SessionLocal() as db:
            chats = [chat for chat in db.query(Chat).all() if body['id'] in chat.chat['history']['messages']]
        return chats[0].chat['history']['messages'][body['id']].get('meta')

    assert reply_meta({'reasoning': True}) == {'thinking_level': 'low'}
    assert reply_meta({'reasoning': True}, 'off') == {'thinking_level': 'off'}
    # 模型没有思考控制时档位发不出去，如实记成模型默认
    assert reply_meta({}) == {'thinking_level': 'model_default'}


def test_only_assignment_coaching_chats_ask_for_automatic_retries(education_client, monkeypatch):
    """作业辅导对话带上重发标记,服务商一时出错由 OpenAI 兼容路由自动重发;普通对话不变。"""
    webui_main, student, folder_id, _ = _assignment_chat(
        education_client, monkeypatch, {'thinking': 'low', 'students_choose_thinking': True}, 'student'
    )
    flags = []

    async def no_event(*args, **kwargs):
        return None

    async def capture(metadata, chat_id):
        flags.append(metadata['retry_transient'])
        raise HTTPException(status_code=418, detail='stop after the chat is saved')

    monkeypatch.setattr(webui_main, 'publish_event', no_event)
    monkeypatch.setattr(webui_main, 'emit_chat_list_event', capture)
    for folder in (folder_id, None):
        body = _chat_body(folder)
        body['id'] = f'assistant-{uuid.uuid4()}'
        if folder is None:
            body.pop('folder_id')
        with pytest.raises(HTTPException):
            asyncio.run(webui_main.chat_completion(_chat_request({}), body, student, client_request=True))

    assert flags == [True, False]
