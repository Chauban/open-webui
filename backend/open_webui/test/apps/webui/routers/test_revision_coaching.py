"""Confirmed autonomous revision contract; all data and switches are isolated."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from open_webui.models.config import Config
from open_webui.models.education import Assignment, Education, Submission, SubmissionReviewEvent
from open_webui.models.education_types import (
    TeacherTaskAccess,
    TeacherTaskAccessForm,
    TeachingConfigUpdate,
    RevisionReading,
)
from open_webui.services.education.teaching_config import (
    teacher_access,
    set_teacher_access,
    latest_teaching_config,
    publish_teaching_config,
    revision_system_context,
)
from open_webui.services.education.ai_steps import StepModel
import open_webui.services.education.revision_reading as readings
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client,
    UserContext,
    _rubric_schema,
    _submit_body,
    _reflection_questions,
)

DRAFT = '本段提出一个需要证明的判断，理由和证据之间仍有需要解释的联系。' * 12


@pytest.mark.parametrize('stage', ['first_read', 'coaching_chat', 'revision_review', 'whole_review'])
def test_formal_and_trial_builder_only_attach_current_draft(stage):
    from open_webui.services.education.teaching_runtime import build_messages

    config = {'ai': {'prompt': '老师的提示词'}, 'title': '题目', 'description': '最新要求'}
    dialogue = [{'role': 'assistant', 'content': '前面的真实反馈'},
                {'role': 'user', 'content': '看看这次修改，整体复看一下'}]
    messages = build_messages(config, stage, '唯一的当前稿件', dialogue)
    raw = json.dumps(messages, ensure_ascii=False)
    assert raw.count('唯一的当前稿件') == 1
    assert raw.count('前面的真实反馈') == 1
    assert '上次阅读稿' not in raw
    assert '旧稿，仅作比较' not in raw
    assert '本轮稿件核对' not in raw
    assert dialogue[-1]['content'] == '看看这次修改，整体复看一下'


def test_current_requirements_replace_prior_requirements_without_change_instructions():
    from types import SimpleNamespace
    from open_webui.services.education.teaching_runtime import system_context

    assignment = SimpleNamespace(task_mode='revise_argument', title='当前题目', description='当前要求',
                                 description_version=2, change_summary='旧要求改为新要求',
                                 teaching_config={'version': 1, 'prompt': '教学提示'})
    config = {'ai': {'prompt': '教学提示'}, 'title': assignment.title, 'description': assignment.description,
              'description_version': 2, 'change_summary': assignment.change_summary}
    for prompt in (revision_system_context(assignment), system_context(config)):
        assert prompt.count('当前要求') == 1
        assert '旧要求' not in prompt
        assert '变更说明' not in prompt
        assert '要求版本' not in prompt


def setup(client, teacher, student, mode='revise_argument', scoring='dimensions', questions=None):
    UserContext.current_user = teacher
    classroom = client.post('/api/v1/classrooms', json={'name': '隔离修订验收'}).json()['classroom']
    payload = dict(
        title='段落论证测试',
        description='指定材料与本次题目',
        classroom_ids=[classroom['id']],
        due_at=2000000000,
        task_mode=mode,
        scoring_mode=scoring,
        score_max=100,
        rubric_schema=_rubric_schema() if scoring == 'dimensions' else {'criteria': []},
        reflection_questions=questions or [],
    )
    if mode == 'revise_argument':
        client.app.state.MODELS = {'isolated-model': {'id': 'isolated-model', 'info': {'meta': {'capabilities': {'reasoning': True}}}}}
        client.app.state.OPENAI_MODELS = {}
        asyncio.run(Config.upsert({'education.teaching_models': {'model_ids': ['isolated-model'], 'recommended_model_id': 'isolated-model'}}))
        template = client.get('/api/v1/teacher/assignment-defaults').json()['teaching_configs'][mode]
        prep = client.post('/api/v1/teacher/teaching-preparations', json={'payload': {'assignment': payload,
            'ai': {'prompt': template['prompt'], 'model_id': 'isolated-model', 'thinking': 'medium', 'template_version': template['version']}}})
        assert prep.status_code == 200, prep.text
        prep = prep.json()
        result = client.post(f'/api/v1/teacher/teaching-preparations/{prep["id"]}/publish', json={
            'expected_revision': prep['revision'], 'idempotency_key': 'publish-' + prep['id']})
    else:
        result = client.post('/api/v1/assignments', json=payload)
    assert result.status_code == 200, result.text
    assignment = result.json()[0]
    UserContext.current_user = student
    assert client.post('/api/v1/classrooms/join', json={'invite_code': classroom['invite_code']}).status_code == 200
    workspace = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
    sid = workspace['writing_session']['id']
    if mode != 'from_scratch':
        assert client.post(f'/api/v1/writing-sessions/{sid}/draft-baseline', json={'text': DRAFT}).status_code == 200
    return assignment, sid, payload


def submit(client, assignment, sid, **extra):
    return client.post(f'/api/v1/assignments/{assignment["id"]}/submit', json={**_submit_body(sid, DRAFT), **extra})


def model_stub(monkeypatch, feedback=None, *, text=None):
    calls = []

    async def resolve(*args, **kwargs):
        return StepModel(model_id='isolated-model', fixed=True)

    async def call(*args, **kwargs):
        calls.append(kwargs['messages'])
        return {
            'choices': [
                {
                    'message': {
                        'content': text if text is not None else json.dumps(
                            feedback
                            or {
                                'understanding': '你希望说明理由和证据的关系。',
                                'strength': None,
                                'focus': [{'quote': '需要解释的联系', 'feedback': '请解释证据怎样支持判断。'}],
                                'overview': '仍有疑问，可以自行决定是否修改和提交。',
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    async def available(*args, **kwargs):
        return {'isolated-model': {'info': {'meta': {'capabilities': {'reasoning': True}}}}}

    monkeypatch.setattr(readings, 'available_models', available)
    monkeypatch.setattr(readings, 'resolve_step_model', resolve)
    monkeypatch.setattr(readings, 'call_step_model', call)
    async def captured_call(request, user, config, context, messages, stream=False):
        return await readings.call_step_model(request, user, step=context['purpose'], model=StepModel(model_id=config['ai']['model_id'], fixed=True), messages=messages)
    monkeypatch.setattr('open_webui.services.education.teaching_runtime.execute', captured_call)
    return calls


def test_authorization_create_copy_switch_and_revoke_existing(education_client):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, payload = setup(client, teacher, student)
    with factory() as db:
        set_teacher_access(teacher.id, TeacherTaskAccessForm(allowed_task_modes=[], default_task_mode=None), db)
        db.commit()
    UserContext.current_user = teacher
    defaults = client.get('/api/v1/teacher/assignment-defaults').json()
    assert defaults['allowed_task_modes'] == [] and defaults['task_mode'] is None
    assert client.post('/api/v1/assignments', json=payload).status_code == 403
    assert client.get(f'/api/v1/teacher/assignments/{assignment["id"]}').status_code == 200
    assert (
        client.patch(
            f'/api/v1/assignments/{assignment["id"]}', json={'description': '新材料', 'change_summary': '补充材料'}
        ).status_code
        == 200
    )
    assert (
        client.patch(f'/api/v1/assignments/{assignment["id"]}', json={'task_mode': 'revise_draft'}).status_code == 403
    )


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
@pytest.mark.parametrize('state', ['no_read', 'failed', 'unresolved', 'no_changes'])
def test_submission_has_no_ai_gate(education_client, monkeypatch, mode, state):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    if state != 'no_read':
        model_stub(monkeypatch)
        if state == 'failed':

            async def fail(*args, **kwargs):
                raise RuntimeError('isolated provider failure')

            monkeypatch.setattr(readings, 'call_step_model', fail)
        result = client.post(
            f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read', 'model_id': 'test'}
        )
        assert result.status_code == 200, result.text
    result = submit(client, assignment, sid)
    assert result.status_code == 200, result.text
    with factory() as db:
        frozen = db.get(Submission, result.json()['submission_id']).stats_json
        assert 'revision_items' not in frozen
        assert frozen['assignment_config']['task_mode'] == mode


def test_reading_context_is_identical_for_four_scoring_variants(education_client, monkeypatch):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    with factory() as db:
        model = Education.get_assignment_by_id(assignment['id'], db=db)
    expected = revision_system_context(model)
    for mode, criteria in [
        ('dimensions', _rubric_schema()['criteria']),
        ('dimensions', [{'key': 'format', 'label': 'SECRET_FORMAT', 'max_score': 100}]),
        ('dimensions', [{'key': 'one', 'label': 'SECRET_ONE', 'max_score': 100}]),
        ('total', []),
    ]:
        variant = model.model_copy(
            update={
                'scoring_mode': mode,
                'score_max': 999,
                'rubric_schema': {'criteria': criteria},
                'reflection_questions': [{'prompt': 'SECRET_REFLECTION'}],
            }
        )
        assert revision_system_context(variant) == expected
    calls = model_stub(monkeypatch)
    result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert result.status_code == 200, result.text
    assert 'max_score' not in json.dumps(calls)
    assert assignment['teaching_config']['prompt'] in calls[0][0]['content']
    assert '文献综述综合已有研究' not in calls[0][0]['content']


def test_reading_is_idempotent_and_revision_uses_saved_text(education_client, monkeypatch):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    calls = model_stub(monkeypatch)
    url = f'/api/v1/writing-sessions/{sid}/readings'
    first = client.post(url, json={'purpose': 'first_read'}).json()
    assert client.post(url, json={'purpose': 'first_read'}).json()['id'] == first['id']
    assert len(calls) == 1
    changed = DRAFT + '新增分析：这句话解释了中间步骤。'
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': changed}).status_code == 200
    result = client.post(url, json={'purpose': 'revision_review'})
    assert result.status_code == 200, result.text
    assert result.json()['source_text'] == changed
    assert '上次阅读稿' not in json.loads(calls[-1][1]['content'])
    assert client.get(url).json()[0]['source_text'] == DRAFT


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
@pytest.mark.parametrize('continuous', [True, False])
def test_editable_prompt_controls_reading_without_hidden_teaching_rules(education_client, monkeypatch, mode, continuous):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode=mode)
    custom_prompt = '直接回应学生的问题。需要时给出三处建议；表达顺序由本提示词决定。'
    with factory() as db:
        row = db.get(Assignment, assignment['id'])
        row.teaching_config = {**row.teaching_config, 'prompt': custom_prompt}
        if mode == 'revise_argument':
            from open_webui.models.teaching_trials import AssignmentAiRevision
            revision = db.get(AssignmentAiRevision, row.current_ai_revision_id)
            revision.config = {**revision.config, 'ai': {**revision.config['ai'], 'prompt': custom_prompt}}
        db.commit()
        session = Education.get_writing_session_by_id(sid, db=db)
    response = {
        'understanding': '',
        'strength': None,
        'focus': [] if continuous else [{'quote': '需要解释的联系', 'feedback': f'建议 {i}'} for i in range(3)],
        'overview': '按老师要求直接给学生的连续回复。' if continuous else '',
    }
    text_response = response['overview'] or '\n\n'.join(item['feedback'] for item in response['focus'])
    calls = model_stub(monkeypatch, response, text=text_response if mode == 'revise_argument' else None)
    for purpose in ('first_read', 'revision_review', 'whole_review'):
        result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': purpose})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'ready'
        expected = (
            {'understanding': '', 'strength': None, 'focus': [], 'overview': text_response}
            if mode == 'revise_argument' else response
        )
        assert result.json()['feedback'] == expected
    assert len(calls) == 3
    monkeypatch.setattr(readings, 'get_db_context', factory)
    chat, _ = readings.current_revision_chat_context(session)
    for system in [*[messages[0]['content'] for messages in calls], chat]:
        assert system.count(custom_prompt) == 1
        for hidden in ('平台核心辅导规则', '先指出成立之处', '优先一处', '最多展开两处', '先指出当前稿的一处实际文字'):
            assert hidden not in system


def test_reading_format_requires_content_but_not_a_teaching_sequence():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        readings.ReadingFeedback(understanding='', strength=None, focus=[], overview='  ')


def test_first_read_is_a_real_message_in_the_next_model_request(education_client, monkeypatch):
    from open_webui.models.chat_messages import ChatMessage
    from open_webui.models.chats import Chat, Chats
    from open_webui.models.education import WritingSession
    from open_webui.utils.middleware import load_messages_from_db

    client, teacher, _, student, _, factory = education_client
    _, sid, _ = setup(client, teacher, student)
    model_stub(monkeypatch)
    url = f'/api/v1/writing-sessions/{sid}/readings'
    first = client.post(url, json={'purpose': 'first_read'}).json()
    assert first['status'] == 'ready'
    cid, mid = first['context']['chat_id'], first['context']['message_id']
    with factory() as db:
        session = db.get(WritingSession, sid)
        assert session.active_chat_id == session.chat_id == cid
        stored = db.get(ChatMessage, f'{cid}-{mid}')
        assert stored.role == 'assistant'
        assert first['feedback']['overview'] in stored.content
        assert stored.parent_id is None
        assert db.get(Chat, cid).chat['history']['currentId'] == mid
    assert client.post(url, json={'purpose': 'first_read'}).json()['id'] == first['id']
    # This is the same storage write and chain loader used by ordinary chat requests.
    asyncio.run(Chats.upsert_message_to_chat_by_id_and_message_id(cid, 'followup', {
        'id': 'followup', 'role': 'user', 'content': '你刚才说的是什么意思？',
        'parentId': mid, 'childrenIds': [],
    }))
    messages = asyncio.run(load_messages_from_db(cid, 'followup'))
    assert [message['role'] for message in messages] == ['assistant', 'user']
    assert first['feedback']['overview'] in messages[0]['content']
    assert messages[-1]['content'] == '你刚才说的是什么意思？'
    with factory() as db:
        assert db.query(ChatMessage).filter_by(chat_id=cid, role='assistant').count() == 1


def test_revision_context_includes_only_requested_reference_material(education_client, monkeypatch):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    calls = model_stub(monkeypatch)
    result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert result.json()['status'] == 'ready'
    current = DRAFT + '这是本次新增的分析。'
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': current}).status_code == 200
    with factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
    monkeypatch.setattr(readings, 'get_db_context', factory)
    for question, has_old_draft in (
        ('这句话如何理解？', False),
        ('看看这次修改', False),
        ('上次的建议是什么？', False),
        ('看看这次修改，是否解决上次的建议？', False),
    ):
        context, metadata = readings.current_revision_chat_context(session)
        assert ('旧稿' in context) is has_old_draft
        assert '【此前阅读意见' not in context
        assert result.json()['feedback']['overview'] not in context
        assert current not in context
        messages = readings.attach_current_revision_draft(
            [{'role': 'system', 'content': context}, {'role': 'user', 'content': question}],
            metadata['source_text'],
        )
        assert sum(message['content'].count(current) for message in messages) == 1
    # Independent platform reviews also send the current draft once, without old feedback.
    client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'revision_review'})
    material = json.loads(calls[-1][1]['content'])
    assert material['当前保存稿'] == current
    assert '上次阅读稿' not in material
    assert '此前反馈' not in material


def test_revision_model_settings_are_isolated_per_request():
    model = {'info': {'params': {'system': 'unrelated persona', 'temperature': 0.4}, 'meta': {
        'knowledge': [{'id': 'private'}], 'skillIds': ['default-skill'], 'filterIds': ['default-filter'],
        'capabilities': {'vision': True, 'builtin_tools': True},
    }}}
    isolated = readings.revision_model_view(model)
    assert isolated['info']['params'] == {'temperature': 0.4}
    assert isolated['info']['meta']['knowledge'] == []
    assert isolated['info']['meta']['skillIds'] == []
    assert isolated['info']['meta']['filterIds'] == []
    assert isolated['info']['meta']['capabilities'] == {'vision': True, 'builtin_tools': False}
    assert model['info']['params']['system'] == 'unrelated persona'
    assert model['info']['meta']['knowledge'] == [{'id': 'private'}]


@pytest.mark.parametrize('revision', [False, True])
def test_provider_boundary_bypasses_model_system_only_for_revision(monkeypatch, revision):
    from types import SimpleNamespace
    from open_webui.utils import chat

    request = SimpleNamespace(state=SimpleNamespace(education_revision_context=revision),
                              app=SimpleNamespace(state=SimpleNamespace(MODELS={'model': {'id': 'model'}})))

    async def provider(request, form_data, user, **kwargs):
        assert request.state.bypass_system_prompt is revision
        assert form_data['messages'] == [{'role': 'system', 'content': 'teaching prompt'}]
        return {'ok': True}

    monkeypatch.setattr(chat, 'generate_openai_chat_completion', provider)
    result = asyncio.run(chat.generate_chat_completion(
        request, {'model': 'model', 'messages': [{'role': 'system', 'content': 'teaching prompt'}]},
        SimpleNamespace(role='admin'),
    ))
    assert result == {'ok': True}


def test_late_reading_does_not_change_frozen_submission(education_client, monkeypatch):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    model_stub(monkeypatch)
    started, finish = Event(), Event()
    original = readings.call_step_model

    async def delayed(*args, **kwargs):
        started.set()
        await asyncio.to_thread(finish.wait, 10)
        return await original(*args, **kwargs)

    monkeypatch.setattr(readings, 'call_step_model', delayed)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(client.post, f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
        assert started.wait(5)
        result = submit(client, assignment, sid)
        assert result.status_code == 200, result.text
        finish.set()
        assert future.result().json()['status'] == 'ready'
    with factory() as db:
        frozen = db.get(Submission, result.json()['submission_id']).stats_json
        assert frozen['revision_readings'] == []
        assert db.query(RevisionReading).filter_by(writing_session_id=sid, status='ready').count() == 1


def test_total_only_no_reflection_no_prompts_and_safe_correction(education_client):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    submitted = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    url = f'/api/v1/teacher/submissions/{submitted["submission_id"]}/review'
    result = client.post(url, json={'score': 81, 'review_status': 'reviewed', 'overall_comment': '已发布'})
    assert result.status_code == 200, result.text
    assert result.json()['reflection_score'] is None and result.json()['rubric_scores'] is None
    assert client.post(url, json={'review_status': 'pending'}).status_code == 409
    stale = client.post(url, json={'score': 90, 'expected_review_revision': 0})
    assert stale.status_code == 409
    assert client.post(url, json={'score': 87, 'overall_comment': '更正'}).status_code == 200
    UserContext.current_user = student
    workspace = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
    assert workspace['review']['score'] == 87
    assert submit(client, assignment, sid).status_code == 409
    profile = client.get('/api/v1/me/writing/profile').json()['timeline'][0]
    assert profile['score'] == 87 and profile['reflection_quality'] is None and profile['collaboration_index'] is None
    assert profile['rubric'] is None
    with factory() as db:
        assert db.query(SubmissionReviewEvent).count() == 2


def test_stale_grade_after_resubmission_is_rejected(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    first = submit(client, assignment, sid).json()
    second = submit(client, assignment, sid, final_content_text=DRAFT + '新稿').json()
    assert first['submission_id'] == second['submission_id']
    UserContext.current_user = teacher
    response = client.post(
        f'/api/v1/teacher/submissions/{first["submission_id"]}/review',
        json={'score': 90, 'expected_final_version_id': first['final_version_id'], 'expected_review_revision': 0},
    )
    assert response.status_code == 409


def test_changed_reflection_requires_version_and_preserves_old_snapshot(education_client):
    client, teacher, _, student, _, factory = education_client
    question = _reflection_questions()[1]
    assignment, sid, _ = setup(client, teacher, student, questions=[question])
    answers = [{'question_id': question['id'], 'text': '旧回答'}]
    first = submit(client, assignment, sid, reflection_answers=answers).json()
    UserContext.current_user = teacher
    changed = client.patch(
        f'/api/v1/assignments/{assignment["id"]}', json={'reflection_questions': [{**question, 'prompt': '新题干'}]}
    )
    assert changed.status_code == 200, changed.text
    UserContext.current_user = student
    stale = submit(client, assignment, sid, reflection_answers=answers, expected_config_revision=1)
    assert stale.status_code == 409
    with factory() as db:
        evidence = Education.get_latest_profile_evidence_snapshot(first['submission_id'], db=db)
        assert evidence.evidence_json.reflection.reflection.items[0].prompt == question['prompt']


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
def test_return_feedback_is_preserved_but_excluded_from_ai_context(education_client, monkeypatch, mode):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode=mode, scoring='total')
    submitted = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    url = f'/api/v1/teacher/submissions/{submitted["submission_id"]}/review'
    body = {'review_status': 'returned', 'returned_comment': '请说明中间推理', 'resubmit_due_at': 2000000000}
    asyncio.run(Config.upsert({'education.enable_return': False}))
    assert client.post(url, json=body).status_code == 403
    asyncio.run(Config.upsert({'education.enable_return': True}))  # This fixture owns a throwaway DB.
    assert client.post(url, json=body).status_code == 200
    with factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        feedback = readings.published_return_feedback(session, db)
        assert feedback['comment'] == body['returned_comment'] and feedback['review_revision'] == 1
    assert client.post(url, json={**body, 'returned_comment': '更正后的意见'}).status_code == 200
    UserContext.current_user = student
    calls = model_stub(monkeypatch)
    for purpose in ('first_read', 'revision_review', 'whole_review'):
        result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': purpose})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'ready'
        assert 'returned_feedback' not in result.json()['context']
    assert len(calls) == 3
    for excluded in (body['returned_comment'], '更正后的意见', '教师已发布退回意见'):
        assert excluded not in json.dumps(calls, ensure_ascii=False)
    monkeypatch.setattr(readings, 'get_db_context', factory)
    text, context = readings.current_revision_chat_context(session)
    assert '更正后的意见' not in text
    assert 'returned_feedback' not in context
    result = submit(client, assignment, sid)
    assert result.status_code == 200, result.text
    with factory() as db:
        row = db.get(Submission, result.json()['submission_id'])
        assert row.round_no == 2 and row.stats_json['returned_feedback']['comment'] == '更正后的意见'


def test_snapshot_version_and_database_constraints(education_client):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    with factory() as db:
        current = latest_teaching_config('revise_argument', db)
        assert 'standards' not in current
        current['prompt'] = '仅按这一份提示词辅导学生。'
        updated = publish_teaching_config(
            'revise_argument',
            TeachingConfigUpdate(
                **{k: v for k, v in current.items() if k not in ('task_mode', 'version', 'created_at')},
                expected_version=current['version'],
            ),
            db,
        )
        assert updated['version'] == 2
        assert updated['prompt'] == current['prompt']
        assert 'standards' not in updated
        assert db.get(Assignment, assignment['id']).teaching_config['version'] == 1
        schema = inspect(db.bind)
        assert {'teacher_task_access', 'teaching_configuration', 'revision_reading'} <= set(schema.get_table_names())
    UserContext.current_user = teacher
    assert (
        client.patch(f'/api/v1/assignments/{assignment["id"]}', json={'adopt_latest_teaching_config': True}).status_code
        == 409
    )
    with factory() as db:
        row = db.get(TeacherTaskAccess, teacher.id)
        row.default_task_mode = None
        with pytest.raises(IntegrityError):
            db.commit()


def test_missing_versions_are_rejected(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student)
    response = TestClient.request(
        client, 'POST', f'/api/v1/assignments/{assignment["id"]}/submit', json=_submit_body(sid, DRAFT)
    )
    assert response.status_code == 422


def test_quote_anchor_only_recovers_punctuation_from_the_actual_source():
    assert (
        readings.anchor_quote('有研究认为，环境有利于学习。', '有研究认为环境有利于学习')
        == '有研究认为，环境有利于学习'
    )
    assert readings.anchor_quote('环境不利于学习。', '环境有利于学习') is None
    assert readings.anchor_quote('甲，乙。甲，乙。', '甲乙') is None


def test_published_review_and_concurrent_resubmit_share_a_lock(education_client, monkeypatch):
    import open_webui.routers.education as router

    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    first = submit(client, assignment, sid).json()
    grading, release, submit_attempt = Event(), Event(), Event()
    original_projection = router.project_profile_evidence
    original_lock = router.lock_assignment

    def pause_projection(*args, **kwargs):
        grading.set()
        assert release.wait(10)
        return original_projection(*args, **kwargs)

    def observe_lock(*args, **kwargs):
        if grading.is_set():
            submit_attempt.set()
        return original_lock(*args, **kwargs)

    monkeypatch.setattr(router, 'project_profile_evidence', pause_projection)
    monkeypatch.setattr(router, 'lock_assignment', observe_lock)
    UserContext.current_user = teacher
    with ThreadPoolExecutor() as pool:
        review = pool.submit(
            client.post, f'/api/v1/teacher/submissions/{first["submission_id"]}/review', json={'score': 91}
        )
        assert grading.wait(5)
        UserContext.current_user = student
        resubmit = pool.submit(submit, client, assignment, sid, final_content_text=DRAFT + 'new')
        assert submit_attempt.wait(5)
        release.set()
        assert review.result().status_code == 200
        assert resubmit.result().status_code == 409
    with factory() as db:
        assert db.get(Submission, first['submission_id']).final_version_id == first['final_version_id']


def test_late_chat_cannot_change_teacher_submission_evidence(education_client):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    first = submit(client, assignment, sid).json()
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/chat/messages/late',
        json={'message': {'id': 'late', 'role': 'assistant', 'content': 'LATE RESULT', 'timestamp': 2000000000}},
    )
    assert result.status_code == 200
    UserContext.current_user = teacher
    detail = client.get(f'/api/v1/teacher/submissions/{first["submission_id"]}')
    assert detail.status_code == 200, detail.text
    assert detail.json()['prompt_timeline'] == []


def test_draft_review_is_not_a_student_grade(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    first = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    result = client.post(
        f'/api/v1/teacher/submissions/{first["submission_id"]}/review',
        json={'review_status': 'pending', 'score': 90, 'overall_comment': 'private draft'},
    )
    assert result.status_code == 200, result.text
    UserContext.current_user = student
    rounds = client.get(f'/api/v1/assignments/{assignment["id"]}/me/submissions').json()['rounds']
    assert rounds[0]['review']['score'] is None and rounds[0]['review']['overall_comment'] is None
    profile = client.get('/api/v1/me/writing/profile').json()['timeline'][0]
    assert profile['score'] is None


def test_submission_waits_for_async_writer_without_blocking_loop(education_client, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy import update
    from open_webui.internal import db as internal_db
    from open_webui.models.users import User
    from open_webui.routers import education as router

    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student)
    reached_lock = Event()
    original_lock = router.lock_assignment

    def observed_lock(*args):
        reached_lock.set()
        return original_lock(*args)

    monkeypatch.setattr(router, 'lock_assignment', observed_lock)

    async def exercise():
        async with internal_db.AsyncSessionLocal() as writer:
            await writer.execute(update(User).where(User.id == student.id).values(last_active_at=123))
            async with AsyncClient(transport=ASGITransport(app=client.app), base_url='http://test') as http:
                request = asyncio.create_task(
                    http.post(
                        f'/api/v1/assignments/{assignment["id"]}/submit',
                        json={**_submit_body(sid, DRAFT), 'expected_config_revision': assignment['config_revision']},
                    )
                )
                try:
                    assert await asyncio.to_thread(reached_lock.wait, 10)
                    await writer.commit()
                    response = await asyncio.wait_for(request, 10)
                    assert response.status_code == 200, response.text
                finally:
                    if not request.done():
                        request.cancel()
                        await asyncio.gather(request, return_exceptions=True)

    asyncio.run(exercise())


def test_current_draft_attachment_does_not_rewrite_student_messages():
    from open_webui.services.education.revision_reading import attach_current_revision_draft

    messages = [{'role': 'assistant', 'content': 'old quote'}, {'role': 'user', 'content': 'my explanation'}]
    result = attach_current_revision_draft(messages, 'new draft')
    assert messages[-1]['content'] == 'my explanation'
    assert result[-1]['content'].startswith('my explanation')
    assert 'new draft' in result[-1]['content']
    multimodal = [{'role': 'user', 'content': [{'type': 'text', 'text': 'question'}]}]
    attached = attach_current_revision_draft(multimodal, '')
    assert len(multimodal[0]['content']) == 1
    assert len(attached[0]['content']) == 2
    assert '""' in attached[0]['content'][-1]['text']
