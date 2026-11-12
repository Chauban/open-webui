"""Real migrations and HTTP resource boundaries; provider transport is deterministic."""

import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from open_webui.models.config import Config
from open_webui.models.education import Assignment, Education, EducationNotification, Submission
from open_webui.models.teaching_trials import AssignmentAiRevision, TeachingCall
from open_webui.services.education import teaching_runtime as runtime
from open_webui.services.education import teaching_trials as trials
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    _rubric_schema,
    _submit_body,
)
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client as base_education_client,
)

DRAFT = '本段提出一个判断，需要解释证据和理由之间的联系。' * 20
education_client = base_education_client


@pytest.fixture
def env(education_client, monkeypatch):
    client, teacher, other, student, outsider, factory = education_client
    client.app.state.MODELS = {
        key: {'id': key, 'name': key, 'info': {'meta': {'capabilities': {'reasoning': True}}}}
        for key in ('model-A', 'model-B')
    }
    client.app.state.OPENAI_MODELS = {}
    asyncio.run(
        Config.upsert(
            {'education.teaching_models': {'model_ids': ['model-A', 'model-B'], 'recommended_model_id': 'model-A'}}
        )
    )
    monkeypatch.setattr(runtime, 'get_db_context', factory)
    monkeypatch.setattr(trials, 'get_db_context', factory)
    calls = []
    from open_webui.utils.chat import generate_chat_completion as real_generate

    async def provider(request, form_data, user, **kwargs):
        calls.append(copy.deepcopy(form_data))
        runtime.record_provider_request(request, form_data)
        content = '请解释理由和证据的联系。'
        return {'id': 'provider-call', 'choices': [{'message': {'content': content}}], 'usage': {'total_tokens': 100}}

    monkeypatch.setattr('open_webui.utils.chat.generate_chat_completion', provider)
    monkeypatch.setattr('open_webui.services.education.ai_steps.generate_chat_completion', provider)
    UserContext.current_user = teacher
    classroom = client.post('/api/v1/classrooms', json={'name': '教师试教验收'}).json()['classroom']
    return SimpleNamespace(
        client=client,
        teacher=teacher,
        other=other,
        student=student,
        factory=factory,
        classroom=classroom,
        calls=calls,
        real_generate=real_generate,
    )


def payload(env, title='论证任务', prompt='完整教师提示词', model='model-A'):
    return {
        'assignment': {
            'title': title,
            'description': '解释材料如何支持判断',
            'classroom_ids': [env.classroom['id']],
            'due_at': 2000000000,
            'task_mode': 'revise_argument',
            'score_max': 100,
            'rubric_schema': _rubric_schema(),
        },
        'ai': {'prompt': prompt, 'model_id': model, 'thinking': 'medium', 'template_version': 1},
    }


def prepare(env, data=None, assignment_id=None):
    UserContext.current_user = env.teacher
    response = env.client.post(
        '/api/v1/teacher/teaching-preparations', json={'payload': data or payload(env), 'assignment_id': assignment_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def publish(env, prep, expected=None):
    return env.client.post(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}/publish',
        json={
            'expected_revision': prep['revision'],
            'expected_config_revision': expected,
            'idempotency_key': 'publish-' + prep['id'],
            'change_summary': '按课堂反馈调整',
        },
    )


def trial(env, prep, **extra):
    result = env.client.post(
        '/api/v1/teacher/teaching-trials',
        json={'preparation_id': prep['id'], 'expected_revision': prep['revision'], **extra},
    )
    assert result.status_code == 200, result.text
    return result.json()


def action(env, session, name, text='', **extra):
    return env.client.post(
        f'/api/v1/teacher/teaching-trials/{session["id"]}/actions',
        json={
            'expected_sequence': session['sequence'],
            'idempotency_key': str(uuid.uuid4()),
            'action': name,
            'text': text,
            **extra,
        },
    )


def student_session(env, assignment):
    UserContext.current_user = env.student
    env.client.post('/api/v1/classrooms/join', json={'invite_code': env.classroom['invite_code']})
    workspace = env.client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
    sid = workspace['writing_session']['id']
    response = env.client.post(f'/api/v1/writing-sessions/{sid}/draft-baseline', json={'text': DRAFT})
    assert response.status_code == 200, response.text
    return sid


def test_delete_trial_draft_retains_evidence_saved_plans_and_published_versions(env):
    prep = prepare(env)
    tested = action(env, trial(env, prep), 'confirm', DRAFT)
    assert tested.status_code == 200, tested.text
    tested = tested.json()
    plan_response = env.client.post(
        '/api/v1/teacher/saved-teaching-plans', json={'trial_id': tested['id'], 'name': '保留的试教方案'}
    )
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()

    # Another published preparation can already cite this draft's trial evidence.
    published_prep = prepare(env)
    published = publish(env, published_prep)
    assert published.status_code == 200, published.text
    assignment = published.json()[0]
    revisions_path = f'/api/v1/assignments/{assignment["id"]}/ai-revisions'
    revisions = env.client.get(revisions_path).json()
    assert tested['events'][-1]['id'] in revisions[0]['evidence']['event_ids']

    path = f'/api/v1/teacher/teaching-preparations/{prep["id"]}'
    deleted = env.client.delete(path, params={'expected_revision': prep['revision']})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {'deleted': True}
    assert env.client.get(path).status_code == 404
    assert prep['id'] not in {row['id'] for row in env.client.get('/api/v1/teacher/teaching-preparations').json()}
    assert env.client.get(f'/api/v1/teacher/teaching-trials/{tested["id"]}').json() == tested
    assert env.client.get('/api/v1/teacher/saved-teaching-plans').json() == [plan]
    assert env.client.get(revisions_path).json() == revisions
    with env.factory() as db:
        assert Education.get_assignment_by_id(assignment['id'], db=db).model_dump() == assignment

    target = prepare(env, payload(env, title='另一个草稿'))
    adopted = env.client.post(
        f'/api/v1/teacher/saved-teaching-plans/{plan["id"]}/adopt/{target["id"]}',
        json={'expected_revision': target['revision'], 'include_task': True, 'idempotency_key': str(uuid.uuid4())},
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()['payload']['assignment']['title'] == tested['config']['title']
    target_view = env.client.get(f'/api/v1/teacher/teaching-preparations/{target["id"]}').json()
    assert tested['events'][-1]['id'] in target_view['coverage']['event_ids']


@pytest.mark.parametrize(
    'guard,expected_status', [('other', 404), ('student', 403), ('stale', 409), ('published', 409)]
)
def test_delete_trial_draft_preserves_ownership_revision_and_publication_guards(env, guard, expected_status):
    prep = prepare(env)
    tested = trial(env, prep)
    if guard == 'published':
        result = publish(env, prep)
        assert result.status_code == 200, result.text
    if guard in ('other', 'student'):
        UserContext.current_user = getattr(env, guard)
    path = f'/api/v1/teacher/teaching-preparations/{prep["id"]}'
    response = env.client.delete(path, params={'expected_revision': prep['revision'] + (guard == 'stale')})
    assert response.status_code == expected_status, response.text
    UserContext.current_user = env.teacher
    assert env.client.get(path).status_code == 200
    assert env.client.get(f'/api/v1/teacher/teaching-trials/{tested["id"]}').status_code == 200


def test_delete_draft_without_trial(env):
    prep = prepare(env)
    path = f'/api/v1/teacher/teaching-preparations/{prep["id"]}'
    response = env.client.delete(path, params={'expected_revision': prep['revision']})
    assert response.status_code == 200, response.text
    assert env.client.get(path).status_code == 404


def test_private_draft_trial_without_publication_and_adopt_is_not_publish(env):
    data = payload(env)
    data['assignment'].update(classroom_ids=[], due_at=None)
    prep = prepare(env, data)
    session = trial(env, prep)
    result = action(env, session, 'confirm', DRAFT)
    assert result.status_code == 200, result.text
    session = result.json()
    assert session['events'][-1]['call']['status'] == 'ready'
    assert env.calls[0]['model'] == 'model-A'
    assert env.calls[0]['thinking_level'] == 'medium'
    assert data['ai']['prompt'] in env.calls[0]['messages'][0]['content']
    with env.factory() as db:
        assert (
            db.query(Assignment).count() == db.query(Submission).count() == db.query(EducationNotification).count() == 0
        )
    result = env.client.post(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}/adopt',
        json={'expected_revision': 1, 'trial_id': session['id']},
    )
    assert result.status_code == 200 and result.json()['published'] is None
    assert publish(env, result.json()).status_code == 400
    UserContext.current_user = env.other
    assert env.client.get(f'/api/v1/teacher/teaching-trials/{session["id"]}').status_code == 404
    UserContext.current_user = env.student
    assert env.client.get('/api/v1/teacher/teaching-preparations').status_code == 403


@pytest.mark.parametrize(
    'missing',
    [
        {'due_at': None},
        {'title': ' '},
        {'classroom_ids': []},
        {'title': '', 'classroom_ids': [], 'due_at': None},
    ],
)
def test_publish_reports_only_missing_fields_and_allows_corrected_retry(env, missing):
    complete = payload(env)
    incomplete = copy.deepcopy(complete)
    incomplete['assignment'].update(missing)
    prep = prepare(env, incomplete)
    result = publish(env, prep)
    assert result.status_code == 400, result.text
    messages = {
        'title': 'Assignment title is required.',
        'classroom_ids': 'At least one classroom is required',
        'due_at': 'Assignment due time is required.',
    }
    assert {error['loc'][-1]: error['msg'] for error in result.json()['detail']} == {
        field: messages[field] for field in missing
    }
    with env.factory() as db:
        assert db.query(Assignment).count() == db.query(AssignmentAiRevision).count() == 0
    updated = env.client.put(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}',
        json={'expected_revision': prep['revision'], 'payload': complete},
    )
    assert updated.status_code == 200, updated.text
    result = publish(env, updated.json())
    assert result.status_code == 200, result.text
    assert result.json()[0]['due_at'] == complete['assignment']['due_at']
    assert publish(env, updated.json()).json() == result.json()
    with env.factory() as db:
        assert db.query(Assignment).count() == db.query(AssignmentAiRevision).count() == 1


def test_atomic_publish_idempotency_and_optimistic_revision(env):
    prep = prepare(env)
    body = {'expected_revision': 1, 'payload': prep['payload']}
    assert env.client.put(f'/api/v1/teacher/teaching-preparations/{prep["id"]}', json=body).status_code == 200
    assert env.client.put(f'/api/v1/teacher/teaching-preparations/{prep["id"]}', json=body).status_code == 409
    prep['revision'] = 2
    first = publish(env, prep)
    assert first.status_code == 200, first.text
    second = publish(env, prep)
    assert second.json() == first.json()
    with env.factory() as db:
        assert db.query(Assignment).count() == db.query(AssignmentAiRevision).count() == 1
    invalid = payload(env)
    invalid['assignment']['classroom_ids'].append('missing-classroom')
    bad = prepare(env, invalid)
    assert publish(env, bad).status_code == 404
    with env.factory() as db:
        assert db.query(Assignment).count() == 1


def test_trial_and_formal_first_read_provider_boundary_matches(env):
    prep = prepare(env)
    session = trial(env, prep)
    assert action(env, session, 'confirm', DRAFT).status_code == 200
    result = publish(env, prep)
    assert result.status_code == 200, result.text
    assignment = result.json()[0]
    sid = student_session(env, assignment)
    result = env.client.post(
        f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read', 'model_id': 'model-C'}
    )
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'ready'
    assert env.calls[0] == env.calls[1]
    assert result.json()['context']['ai_revision'] == 1


def test_inflight_v1_is_not_overwritten_by_v2_and_submission_freezes_all(env):
    first = publish(env, prepare(env)).json()[0]
    sid = student_session(env, first)
    with env.factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        config1, call1 = runtime.capture_formal(session, 'request-1', 'coaching_chat', db, user=env.student)
    prep2 = prepare(env, payload(env, prompt='第二版完整提示词', model='model-B'), first['id'])
    second = publish(env, prep2, first['config_revision'])
    assert second.status_code == 200, second.text
    assert second.json()[0]['change_summary'] == '按课堂反馈调整'
    assert config1['ai']['model_id'] == 'model-A'
    runtime.finish_formal(call1, 'ready')
    with env.factory() as db:
        config2, call2 = runtime.capture_formal(session, 'request-2', 'coaching_chat', db, user=env.student)
        assert config2['ai_revision'] == 2 and config2['ai']['model_id'] == 'model-B'
    runtime.finish_formal(call2, 'ready')
    with env.factory() as db:
        frozen = runtime.frozen_evidence(sid, db)
        assert {r['revision'] for r in frozen['revisions']} == {1, 2}
    UserContext.current_user = env.student
    submitted = env.client.post(f'/api/v1/assignments/{first["id"]}/submit', json=_submit_body(sid, DRAFT))
    assert submitted.status_code == 200, submitted.text
    with env.factory() as db:
        frozen_submission = copy.deepcopy(db.get(Submission, submitted.json()['submission_id']).stats_json)
        assert {r['revision'] for r in frozen_submission['teaching_evidence']['revisions']} == {1, 2}
    prep3 = prepare(env, payload(env, prompt='恢复第一版', model='model-A'), first['id'])
    assert publish(env, prep3, second.json()[0]['config_revision']).status_code == 200
    assert {r['revision'] for r in frozen['revisions']} == {1, 2}
    with env.factory() as db:
        assert db.get(Submission, submitted.json()['submission_id']).stats_json == frozen_submission


def test_trial_fingerprint_ignores_grading_and_invalidates_model_changes(env):
    prep = prepare(env)
    session = trial(env, prep)
    assert action(env, session, 'confirm', DRAFT).status_code == 200
    original = env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()
    assert original['coverage']['stages'] == ['first_read']
    updated = copy.deepcopy(prep['payload'])
    updated['assignment']['due_at'] += 1000
    saved = env.client.put(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}', json={'expected_revision': 1, 'payload': updated}
    )
    assert saved.status_code == 200
    assert env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()['coverage']['stages'] == [
        'first_read'
    ]
    updated['ai']['prompt'] += '修改'
    assert (
        env.client.put(
            f'/api/v1/teacher/teaching-preparations/{prep["id"]}', json={'expected_revision': 2, 'payload': updated}
        ).status_code
        == 200
    )
    assert env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()['coverage']['stages'] == []


def test_no_model_fallback_and_private_trial_branch(env):
    prep = prepare(env)
    session = trial(env, prep)
    completed = action(env, session, 'confirm', DRAFT).json()
    branch = trial(env, prep, source_trial_id=session['id'], source_sequence=1)
    assert branch['state']['dialogue'] == completed['state']['dialogue']
    assert branch['state']['draft'] == DRAFT
    asyncio.run(
        Config.upsert({'education.teaching_models': {'model_ids': ['model-B'], 'recommended_model_id': 'model-B'}})
    )
    assert action(env, branch, 'coaching_chat', '我不同意').status_code == 409
    assert len(env.calls) == 1


@pytest.mark.parametrize('with_materials', [False, True])
@pytest.mark.parametrize('image_enabled', [False, True])
def test_formal_chat_resolves_assignment_before_ordinary_model_acl(env, monkeypatch, with_materials, image_enabled):
    import open_webui.internal.db as internal_db
    import open_webui.main as main
    from starlette.requests import Request

    first = publish(env, prepare(env)).json()[0]
    sid = student_session(env, first)
    monkeypatch.setattr(internal_db, 'SessionLocal', env.factory)
    with env.factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        assignment_row = db.get(Assignment, first['id'])
        assignment_row.image_reading_enabled = image_enabled
        db.commit()
        if with_materials:
            from open_webui.models.writing_materials import MaterialBlock, WritingMaterial

            block = MaterialBlock(
                id='m1',
                kind='image',
                location='正文证据之后',
                text='截图出处：史料卷三第42页',
                extracted_text='截图出处：史料卷三第42页',
                status='read',
            )
            db.add(
                WritingMaterial(
                    id='request-evidence',
                    writing_session_id=sid,
                    filename='初稿.docx',
                    bundle_path='unused-test-asset.zip',
                    data={'blocks': [block.model_dump()], 'model_id': 'vision'},
                    active=True,
                    confirmed_at=1,
                    created_at=1,
                )
            )
            from open_webui.models.notes import Note

            note = db.get(Note, session.note_id)
            data = copy.deepcopy(note.data)
            data['content']['json']['content'].append(
                {
                    'type': 'writingImage',
                    'attrs': {
                        'materialId': 'request-evidence',
                        'blockId': 'm1',
                        'width': 100,
                        'transcription': block.text,
                        'transcriptionEdited': False,
                    },
                }
            )
            note.data = data
            db.commit()

    async def deny(*args, **kwargs):
        raise HTTPException(403, 'No ordinary model access')

    monkeypatch.setattr(main, 'BYPASS_MODEL_ACCESS_CONTROL', False)
    monkeypatch.setattr(main, 'check_model_access', deny)

    async def provider(request, form_data, user):
        env.calls.append(copy.deepcopy(form_data))
        runtime.record_provider_request(request, form_data)
        return {
            'id': 'provider-chat',
            'choices': [
                {'message': {'role': 'assistant', 'content': '你可以保留自己的判断。'}, 'finish_reason': 'stop'}
            ],
        }

    monkeypatch.setattr(main, 'chat_completion_handler', provider)
    request = Request(
        {'type': 'http', 'method': 'POST', 'path': '/api/chat/completions', 'headers': [], 'app': env.client.app}
    )
    body = {
        'model': 'model-C',
        'parent_id': None,
        'user_message': {'id': str(uuid.uuid4()), 'role': 'user', 'content': '我不同意', 'parentId': None},
        'stream': False,
        'folder_id': session.folder_id,
        'id': str(uuid.uuid4()),
        'messages': [{'role': 'system', 'content': 'SECRET_STUDENT_OVERRIDE'}, {'role': 'user', 'content': '我不同意'}],
        'params': {'temperature': 9, 'thinking_level': 'off'},
    }
    result = asyncio.run(main.chat_completion(request, body, env.student, client_request=True))
    assert result
    assert env.calls[-1]['model'] == 'model-A'
    assert env.calls[-1]['thinking_level'] == 'medium'
    assert 'SECRET_STUDENT_OVERRIDE' not in json.dumps(env.calls[-1])
    assert env.calls[-1]['messages'][-1]['content'].count(DRAFT) == 1
    if with_materials:
        assert ('史料卷三第42页' in env.calls[-1]['messages'][-1]['content']) is image_enabled
    with env.factory() as db:
        call = db.query(TeachingCall).filter_by(session_id=sid).one()
        assert call.status == 'ready'
        assert env.calls[-1]['messages'][0]['content'] == runtime.system_context(call.context['config'])
        assert call.context['image_reading_enabled'] is image_enabled
        if with_materials:
            assert call.context['materials'][0]['id'] == 'request-evidence'
    request = Request(
        {'type': 'http', 'method': 'POST', 'path': '/api/chat/completions', 'headers': [], 'app': env.client.app}
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            main.chat_completion(
                request,
                {'model': 'model-A', 'messages': [{'role': 'user', 'content': 'normal chat'}]},
                env.student,
                client_request=True,
            )
        )
    assert error.value.status_code == 403


def test_concurrent_publications_have_one_winner_and_preserve_loser_input(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    assignment = publish(env, prepare(env)).json()[0]
    a = prepare(env, payload(env, prompt='候选 A'), assignment['id'])
    b = prepare(env, payload(env, prompt='候选 B'), assignment['id'])
    barrier = Barrier(2)

    def apply(prep):
        barrier.wait(timeout=10)
        return publish(env, prep, assignment['config_revision'])

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(apply, (a, b)))
    assert sorted(response.status_code for response in results) == [200, 409]
    with env.factory() as db:
        assert db.query(AssignmentAiRevision).filter_by(assignment_id=assignment['id']).count() == 2
    for prep, response in zip((a, b), results):
        saved = env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()
        assert saved['payload']['ai']['prompt'] == prep['payload']['ai']['prompt']
        assert bool(saved['published']) == (response.status_code == 200)


def test_trial_request_dedup_distinct_retest_and_save_conflict(env):
    prep = prepare(env)
    session = trial(env, prep)
    body = {'expected_sequence': 0, 'idempotency_key': 'network-request-1', 'action': 'confirm', 'text': DRAFT}
    url = f'/api/v1/teacher/teaching-trials/{session["id"]}/actions'
    first = env.client.post(url, json=body)
    assert first.status_code == 200
    assert env.client.post(url, json=body).status_code == 200
    assert len(env.calls) == 1
    assert env.client.post(url, json={**body, 'text': DRAFT + 'different'}).status_code == 409
    session = first.json()
    second = action(env, session, 'first_read')
    assert second.status_code == 200 and len(env.calls) == 2
    assert action(env, session, 'save', '旧页面的输入').status_code == 409
    assert len(second.json()['events']) == 2


def test_revoking_creation_keeps_existing_management_but_revoking_model_blocks_calls(env):
    from open_webui.models.education_types import TeacherTaskAccessForm
    from open_webui.services.education.teaching_config import set_teacher_access

    assignment = publish(env, prepare(env)).json()[0]
    with env.factory() as db:
        set_teacher_access(env.teacher.id, TeacherTaskAccessForm(allowed_task_modes=[], default_task_mode=None), db)
        db.commit()
    assert env.client.post('/api/v1/teacher/teaching-preparations', json={'payload': payload(env)}).status_code == 403
    prep = prepare(env, assignment_id=assignment['id'])
    session = trial(env, prep)
    assert action(env, session, 'confirm', DRAFT).status_code == 200


def test_adoption_preserves_changed_requirements_and_invalidates_coverage(env):
    prep = prepare(env)
    session = trial(env, prep)
    assert action(env, session, 'confirm', DRAFT).status_code == 200
    changed = copy.deepcopy(prep['payload'])
    changed['assignment']['description'] = '已经修改的题目要求'
    saved = env.client.put(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}', json={'expected_revision': 1, 'payload': changed}
    ).json()
    result = env.client.post(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}/adopt',
        json={'expected_revision': saved['revision'], 'trial_id': session['id']},
    )
    assert result.json()['payload']['assignment']['description'] == changed['assignment']['description']
    assert env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()['coverage']['stages'] == []


def test_provider_payload_parity_after_filters_and_plain_text_initial_reading(env, monkeypatch):  # noqa: C901
    import open_webui.routers.openai as provider
    import open_webui.services.education.ai_steps as steps
    import open_webui.services.education.teaching_filters as filters
    from open_webui.models.models import Model

    sent = []
    with env.factory() as db:
        db.add(
            Model(
                id='model-A',
                user_id=env.teacher.id,
                name='A',
                base_model_id=None,
                params={'temperature': 0.25, 'system': 'SECRET_MODEL_SYSTEM'},
                meta={'capabilities': {'reasoning': True}},
                is_active=True,
                created_at=1,
                updated_at=1,
            )
        )
        db.commit()
    env.client.app.state.OPENAI_MODELS = {'model-A': {'id': 'model-A', 'urlIdx': 0}}

    async def connection(idx):
        return 'https://api.deepseek.com', 'SECRET_CONNECTION', {}

    async def headers(*args, **kwargs):
        return {}, {}

    async def global_filter(request, context, functions, phase, body, extra):
        assert extra['__user__']['role'] == 'user'
        if phase == 'inlet':
            body['messages'][0]['content'] += '\nGLOBAL_FILTER_MARKER'
        return body, {}

    class Response:
        status = 200
        headers = {'Content-Type': 'application/json'}
        closed = False

        def __init__(self, content):
            self.content_text = content

        def close(self):
            self.closed = True

        async def read(self):
            return b'{}'

        async def json(self, **kwargs):
            return {'id': 'transport-id', 'choices': [{'message': {'role': 'assistant', 'content': self.content_text}}]}

    class Transport:
        async def request(self, **kwargs):
            sent.append(json.loads(kwargs['data']))
            if sent[-1].get('stream'):
                response = Response('')
                response.headers = {'Content-Type': 'text/event-stream'}
                data = json.dumps(
                    {
                        'id': 'streamed-reply',
                        'choices': [{'index': 0, 'delta': {'content': '可以保留你的判断。'}, 'finish_reason': 'stop'}],
                    },
                    ensure_ascii=False,
                )

                class Content:
                    def __init__(self):
                        self.chunks = [(f'data: {data}\n\n'.encode(), False), (b'data: [DONE]\n\n', False)]

                    async def readchunk(self):
                        return self.chunks.pop(0)

                    async def iter_chunks(self):
                        while self.chunks:
                            yield self.chunks.pop(0)

                response.content = Content()
                return response
            content = (
                '## 初读反馈\n\n你可以使用"引号"，保留自己的判断。\n\n'
                '| 要素 | 反馈 |\n| --- | --- |\n| 理由 | 请说明依据 |'
            )
            return Response(content)

    async def transport():
        return Transport()

    monkeypatch.setattr(provider, 'get_openai_connection', connection)
    monkeypatch.setattr(provider, 'get_headers_and_cookies', headers)
    monkeypatch.setattr(provider, 'get_session', transport)
    monkeypatch.setattr(steps, 'generate_chat_completion', env.real_generate)
    monkeypatch.setattr(filters, 'process_filter_functions', global_filter)
    prep = prepare(env)
    tested = trial(env, prep)
    trial_response = action(env, tested, 'confirm', DRAFT)
    assert trial_response.status_code == 200, trial_response.text
    assert trial_response.json()['events'][-1]['call']['status'] == 'ready'
    assignment = publish(env, prep).json()[0]
    # Live defaults change after publication; the already published temperature remains fixed.
    with env.factory() as db:
        model = db.get(Model, 'model-A')
        model.params = {'temperature': 9.0, 'system': 'ANOTHER_SECRET_SYSTEM'}
        db.commit()
    sid = student_session(env, assignment)
    formal = env.client.post(
        f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read', 'model_id': 'model-B'}
    )
    assert formal.status_code == 200, formal.text
    assert formal.json()['status'] == 'ready'
    assert len(sent) == 2 and sent[0] == sent[1]
    assert all(body['temperature'] == 0.25 and body['reasoning_effort'] == 'high' for body in sent)
    assert all('GLOBAL_FILTER_MARKER' in body['messages'][0]['content'] for body in sent)
    assert 'SECRET' not in json.dumps(sent)
    assert len(formal.json()['context']['attempts']) == 1
    assert formal.json()['context']['output_contract'] == 'markdown-v1'
    assert formal.json()['feedback']['overview'] == trial_response.json()['state']['dialogue'][0]['content']
    import open_webui.internal.db as internal_db
    import open_webui.main as main
    from open_webui.models.chats import Chat
    from starlette.requests import Request
    from starlette.responses import StreamingResponse

    monkeypatch.setattr(internal_db, 'SessionLocal', env.factory)
    monkeypatch.setattr(main, 'chat_completion_handler', env.real_generate)
    tested = trial_response.json()
    for stage, question in [('coaching_chat', '我不同意'), ('revision_review', '看看这次修改')]:
        if stage == 'revision_review':
            changed = DRAFT + '这里补充了解释证据如何支持判断的分析。'
            UserContext.current_user = env.teacher
            tested = action(env, tested, 'save', changed).json()
            UserContext.current_user = env.student
            assert (
                env.client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': changed}).status_code
                == 200
            )
        UserContext.current_user = env.teacher
        streamed = action(env, tested, 'coaching_chat', question)
        assert streamed.status_code == 200 and '"done": true' in streamed.text, streamed.text
        tested = env.client.get(f'/api/v1/teacher/teaching-trials/{tested["id"]}').json()
        with env.factory() as db:
            session = Education.get_writing_session_by_id(sid, db=db)
            chat = db.get(Chat, session.active_chat_id)
            chat_id, parent_id = chat.id, chat.current_message_id

        async def formal_stream():
            request = Request(
                {
                    'type': 'http',
                    'method': 'POST',
                    'path': '/api/chat/completions',
                    'headers': [],
                    'app': env.client.app,
                }
            )
            result = await main.chat_completion(
                request,
                {
                    'model': 'model-B',
                    'stream': True,
                    'chat_id': chat_id,
                    'parent_id': parent_id,
                    'id': str(uuid.uuid4()),
                    'user_message': {
                        'id': str(uuid.uuid4()),
                        'role': 'user',
                        'content': question,
                        'parentId': parent_id,
                    },
                    'messages': [
                        {'role': 'assistant', 'content': 'FABRICATED_CLIENT_HISTORY'},
                        {'role': 'user', 'content': question},
                    ],
                },
                env.student,
                client_request=True,
            )
            if isinstance(result, StreamingResponse):
                async for _ in result.body_iterator:
                    pass

        asyncio.run(formal_stream())
        assert sent[-2] == sent[-1]
        assert 'FABRICATED_CLIENT_HISTORY' not in json.dumps(sent[-1])


def test_existing_assignment_upgrade_requires_explicit_mapping_and_preserves_frozen_evidence(
    env, monkeypatch, tmp_path
):
    from open_webui.test.util.database import _run_migrations, migration_database_at
    from sqlalchemy import MetaData, Table, create_engine, inspect, text

    config = trial(env, prepare(env))['config']
    historic = '{"original_model":"unknown","grade":88,"prompt":"old teaching"}'
    with migration_database_at('f9a1b3c5d7e0') as url:
        engine = create_engine(url)
        metadata = MetaData()
        assignments = Table('assignment', metadata, autoload_with=engine)
        submissions = Table('submission', metadata, autoload_with=engine)
        with engine.begin() as db:
            db.execute(
                assignments.insert(),
                dict(
                    id='old-argument',
                    teacher_id='teacher-old',
                    classroom_id='class-old',
                    title=config['title'],
                    description=config['description'],
                    due_at=2000000000,
                    score_max=100,
                    coaching_style='balanced',
                    task_mode='revise_argument',
                    scoring_mode='total',
                    teaching_config=json.dumps({'prompt': 'old teaching'}),
                    config_revision=1,
                    description_version=1,
                    reflection_version=1,
                    challenge_enabled=False,
                    challenge_rounds=3,
                    challenge_focus_keys='[]',
                    reflection_questions='[]',
                    rubric_schema='{"criteria":[]}',
                    model_params='{}',
                    created_at=1,
                    updated_at=1,
                ),
            )
            db.execute(
                submissions.insert(),
                dict(
                    id='frozen-before-upgrade',
                    assignment_id='old-argument',
                    student_id='student-old',
                    writing_session_id='session-old',
                    final_version_id='version-old',
                    stats_json=historic,
                    micro_reflection_id='reflection-old',
                    submitted_at=1,
                    round_no=1,
                    is_current=1,
                ),
            )
        monkeypatch.delenv('TEACHING_AI_MIGRATION_MAP', raising=False)
        with pytest.raises(RuntimeError, match='TEACHING_AI_MIGRATION_MAP'):
            _run_migrations(url)
        assert 'assignment_ai_revision' not in inspect(engine).get_table_names()
        mapping = tmp_path / 'teaching-map.json'
        mapping.write_text(json.dumps({'old-argument': config}), encoding='utf-8')
        monkeypatch.setenv('TEACHING_AI_MIGRATION_MAP', str(mapping))
        _run_migrations(url)
        with engine.connect() as db:
            assert (
                db.execute(text("SELECT stats_json FROM submission WHERE id='frozen-before-upgrade'")).scalar_one()
                == historic
            )
            assert db.execute(
                text("SELECT current_ai_revision_id FROM assignment WHERE id='old-argument'")
            ).scalar_one()
            recorded = json.loads(
                db.execute(
                    text("SELECT config FROM assignment_ai_revision WHERE assignment_id='old-argument'")
                ).scalar_one()
            )
            assert recorded['ai']['model_id'] == 'model-A'
        engine.dispose()


def test_rollback_copies_frozen_generation_parameters_and_updates_ai_only(env):
    asyncio.run(Config.upsert({'models.default_params': {'temperature': 0.2}}))
    assignment = publish(env, prepare(env)).json()[0]
    first_version = env.client.get(f'/api/v1/assignments/{assignment["id"]}/ai-revisions').json()[0]
    asyncio.run(Config.upsert({'models.default_params': {'temperature': 0.9}}))
    second = publish(
        env, prepare(env, payload(env, prompt='第二版'), assignment['id']), assignment['config_revision']
    ).json()[0]
    changed = payload(env, title='不应改写正式题目')
    prep = prepare(env, changed, assignment['id'])
    assert prep['payload']['assignment']['title'] == assignment['title']
    adopted = env.client.post(
        f'/api/v1/teacher/teaching-preparations/{prep["id"]}/adopt-revision',
        json={'expected_revision': prep['revision'], 'revision_id': first_version['id']},
    )
    assert adopted.status_code == 200, adopted.text
    third = publish(env, adopted.json(), second['config_revision'])
    assert third.status_code == 200, third.text
    versions = env.client.get(f'/api/v1/assignments/{assignment["id"]}/ai-revisions').json()
    assert [v['revision'] for v in versions] == [3, 2, 1]
    assert versions[0]['config']['binding']['params']['temperature'] == 0.2
    assert versions[1]['config']['binding']['params']['temperature'] == 0.9
    assert third.json()[0]['title'] == assignment['title']


def test_trial_does_not_offer_submission_preview(env):
    prep = prepare(env)
    session = trial(env, prep)
    session = action(env, session, 'confirm', DRAFT).json()
    response = action(env, session, 'finish')
    assert response.status_code == 422
    stored = env.client.get(f'/api/v1/teacher/teaching-trials/{session["id"]}').json()
    assert stored['state']['status'] == 'active'
    assert 'submission_preview' not in stored['state']


def test_assignment_trial_sources_include_published_preparations_and_stay_private(env):
    prep = prepare(env)
    source = trial(env, prep)
    completed = action(env, source, 'confirm', DRAFT).json()
    assignment = publish(env, prep).json()[0]
    url = f'/api/v1/assignments/{assignment["id"]}/teaching-trials'
    sources = env.client.get(url)
    assert sources.status_code == 200 and [row['id'] for row in sources.json()] == [source['id']]
    candidate = prepare(env, payload(env, prompt='新辅导方案'), assignment_id=assignment['id'])
    continued = trial(env, candidate, source_trial_id=source['id'], source_sequence=1)
    assert continued['state']['dialogue'] == completed['state']['dialogue']
    assert continued['config']['ai']['prompt'] == '新辅导方案'
    UserContext.current_user = env.other
    assert env.client.get(url).status_code == 403
    UserContext.current_user = env.other.model_copy(update={'role': 'admin'})
    assert env.client.get(url).json() == []


def test_worker_update_invalidates_old_trial_but_keeps_published_assignment_usable(env, monkeypatch):
    prep = prepare(env)
    old_trial = trial(env, prep)
    assignment = publish(env, prep).json()[0]
    sid = student_session(env, assignment)
    original_execution = old_trial['config']['execution_version']
    monkeypatch.setattr(runtime, 'execution_version', lambda: 'new-worker-version')
    response = env.client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'ready'
    assert response.json()['context']['ai_revision'] == 1
    assert response.json()['context']['config']['execution_version'] == 'new-worker-version'
    with env.factory() as db:
        published = db.get(AssignmentAiRevision, assignment['current_ai_revision_id'])
        assert published.config['execution_version'] == original_execution
    UserContext.current_user = env.teacher
    assert action(env, old_trial, 'confirm', DRAFT).status_code == 409


def test_accepted_call_retains_execution_snapshot_for_internal_retry(env, monkeypatch):
    from starlette.requests import Request

    prep = prepare(env)
    snapshot = trial(env, prep)['config']
    original = snapshot['execution_version']
    monkeypatch.setattr(runtime, 'execution_version', lambda: 'later-worker-version')
    request = Request({'type': 'http', 'method': 'POST', 'path': '/trial', 'headers': [], 'app': env.client.app})
    context = {'purpose': 'coaching_chat', 'attempts': []}
    asyncio.run(runtime.execute(request, env.teacher, snapshot, context, [{'role': 'user', 'content': '继续'}]))
    assert snapshot['execution_version'] == original
    assert len(env.calls) == 1


def test_first_read_retry_does_not_claim_the_edited_draft_version(env):
    assignment = publish(env, prepare(env)).json()[0]
    sid = student_session(env, assignment)
    created = env.client.post(
        f'/api/v1/writing-sessions/{sid}/versions',
        json={'trigger_type': 'manual', 'content_text': DRAFT + '新的改动。', 'content_json': None},
    )
    assert created.status_code == 200, created.text
    assert (
        env.client.post(
            f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': DRAFT + '新的改动。'}
        ).status_code
        == 200
    )
    with env.factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        latest = Education.get_latest_version(sid, db=db)
        _, call = runtime.capture_formal(session, 'retry-initial-source', 'first_read', db, user=env.student)
        assert call['source_text'] == DRAFT
        assert latest.note_snapshot_text != DRAFT
        assert call['source_version_id'] != latest.id


def test_shared_stream_boundary_retains_raw_output_and_rejects_empty_reply(env):
    from open_webui.services.education.teaching_filters import finish
    from starlette.responses import StreamingResponse

    async def raw_stream():
        yield 'data: {"choices":[{"delta":{"reasoning_content":"only thinking"},"finish_reason":"stop"}]}\n\n'
        yield 'data: [DONE]\n\n'

    evidence = {}
    request = SimpleNamespace(
        state=SimpleNamespace(
            teaching_filters=(env.teacher, None, [], {}, {'model': 'model-A', 'messages': []}, False),
            teaching_evidence=evidence,
        )
    )

    async def consume():
        response = await finish(request, StreamingResponse(raw_stream()))
        async for _ in response.body_iterator:
            pass

    with pytest.raises(ValueError, match='no visible reply'):
        asyncio.run(consume())
    assert 'only thinking' in evidence['provider_streams'][0]


@pytest.mark.parametrize(
    'raw',
    [
        '你用了"文化自立型"这个判断，请先界定它。\n\n| 要素 | 建议 |\n| --- | --- |\n| 理由 | 说明判据 |',
        '```text\n这里的 {"引号": "无需转义"} 是正文示例\n```\n\n' + '这是长反馈。' * 2500,
    ],
    ids=['quotes-and-table', 'long-feedback-with-code'],
)
def test_plain_initial_feedback_is_preserved_in_trial_and_formal_chat(env, monkeypatch, raw):
    async def provider(request, form_data, user, **kwargs):
        env.calls.append(copy.deepcopy(form_data))
        runtime.record_provider_request(request, form_data)
        return {'id': 'plain-reply', 'choices': [{'finish_reason': 'stop', 'message': {'content': raw}}]}

    monkeypatch.setattr('open_webui.utils.chat.generate_chat_completion', provider)
    monkeypatch.setattr('open_webui.services.education.ai_steps.generate_chat_completion', provider)
    prep = prepare(env)
    tested = action(env, trial(env, prep), 'confirm', DRAFT).json()
    assert tested['events'][-1]['call']['status'] == 'ready'
    assert tested['state']['dialogue'][0]['content'] == raw
    assert tested['events'][-1]['call']['feedback'] == {
        'understanding': '',
        'strength': None,
        'focus': [],
        'overview': raw,
    }
    assert tested['events'][-1]['call']['outputs'][0]['raw'] == raw
    assert len(env.calls) == 1
    assert '只输出 JSON' not in env.calls[0]['messages'][0]['content']
    assert 'json_schema' not in json.dumps(env.calls[0])
    assignment = publish(env, prep).json()[0]
    sid = student_session(env, assignment)
    response = env.client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
    assert response.status_code == 200, response.text
    assert response.json()['feedback']['overview'] == raw
    assert len(env.calls) == 2 and env.calls[0] == env.calls[1]
    from open_webui.models.chats import Chat

    with env.factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        chat = db.get(Chat, session.active_chat_id)
        assert chat.chat['history']['messages'][chat.current_message_id]['content'] == raw


@pytest.mark.parametrize(
    ('content', 'finish_reason', 'error_code'),
    [
        ('', 'stop', 'empty_response'),
        ('   ', 'stop', 'empty_response'),
        (None, 'stop', 'empty_response'),
        ('半截反馈', 'length', 'incomplete_response'),
        ('被截断', 'content_filter', 'incomplete_response'),
    ],
)
def test_initial_text_output_rejects_empty_or_incomplete_without_format_retry(
    env, monkeypatch, content, finish_reason, error_code
):
    async def provider(request, form_data, user, **kwargs):
        env.calls.append(copy.deepcopy(form_data))
        return {'choices': [{'finish_reason': finish_reason, 'message': {'content': content}}]}

    monkeypatch.setattr('open_webui.utils.chat.generate_chat_completion', provider)
    monkeypatch.setattr('open_webui.services.education.ai_steps.generate_chat_completion', provider)
    result = action(env, trial(env, prepare(env)), 'confirm', DRAFT).json()
    call = result['events'][-1]['call']
    assert call['status'] == 'failed'
    assert call['output_contract'] == 'markdown-v1'
    assert call['error_code'] == error_code
    assert call['outputs'][0]['raw'] == content
    assert result['state']['dialogue'] == []
    assert len(env.calls) == 1


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
def test_autosave_keeps_incomplete_form_private_until_publication(env, mode):
    data = payload(env, title='', prompt='', model='')
    data['assignment'].update(
        task_mode=mode,
        score_max='',
        classroom_ids=[],
        due_at=None,
        rubric_schema={'criteria': [{'key': 'ideas', 'label': '', 'max_score': '-'}]},
        reflection_questions=[{'id': 'q', 'kind': 'text', 'prompt': ''}],
    )
    prep = prepare(env, data)
    restored = env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}')
    assert restored.status_code == 200, restored.text
    assert restored.json()['payload']['assignment']['score_max'] == ''
    assert restored.json()['payload']['assignment']['rubric_schema']['criteria'][0]['max_score'] == '-'
    assert restored.json()['payload']['ai']['model_id'] == ''
    assert publish(env, prep).status_code == 422
    with env.factory() as db:
        assert db.query(Assignment).count() == db.query(EducationNotification).count() == 0
    UserContext.current_user = env.other
    assert env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').status_code == 404


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft'])
def test_autosaved_other_task_modes_publish_once_without_argument_ai(env, mode):
    data = payload(env, prompt='', model='')
    data['assignment'].update(task_mode=mode, image_reading_enabled=True)
    prep = prepare(env, data)
    result = publish(env, prep)
    assert result.status_code == 200, result.text
    assignment = result.json()[0]
    assert assignment['task_mode'] == mode
    assert assignment['image_reading_enabled'] is True
    assert assignment['current_ai_revision_id'] is None
    assert publish(env, prep).json()[0]['id'] == assignment['id']
    with env.factory() as db:
        assert db.query(Assignment).count() == 1
        assert db.query(AssignmentAiRevision).count() == 0
    assert not env.calls


def test_autosave_creation_retry_and_revision_conflict_do_not_overwrite(env):
    draft_id = str(uuid.uuid4())
    body = {'id': draft_id, 'payload': payload(env)}
    first = env.client.post('/api/v1/teacher/teaching-preparations', json=body).json()
    newer = copy.deepcopy(first['payload'])
    newer['assignment']['title'] = '另一页面保存的标题'
    result = env.client.put(
        f'/api/v1/teacher/teaching-preparations/{draft_id}',
        json={
            'expected_revision': 1,
            'payload': newer,
        },
    )
    assert result.status_code == 200
    retried = env.client.post('/api/v1/teacher/teaching-preparations', json=body)
    assert retried.status_code == 200
    assert retried.json()['revision'] == 2
    assert retried.json()['payload']['assignment']['title'] == '另一页面保存的标题'
    assert (
        env.client.put(
            f'/api/v1/teacher/teaching-preparations/{draft_id}',
            json={
                'expected_revision': 1,
                'payload': body['payload'],
            },
        ).status_code
        == 409
    )
    UserContext.current_user = env.other
    assert env.client.post('/api/v1/teacher/teaching-preparations', json=body).status_code == 404


def test_incomplete_grading_does_not_block_trial_but_incomplete_ai_does(env):
    data = payload(env)
    data['assignment']['score_max'] = ''
    prep = prepare(env, data)
    assert trial(env, prep)['id']
    data['ai']['prompt'] = ''
    invalid = prepare(env, data)
    result = env.client.post(
        '/api/v1/teacher/teaching-trials',
        json={
            'preparation_id': invalid['id'],
            'expected_revision': invalid['revision'],
        },
    )
    assert result.status_code == 422
    assert not env.calls


def test_draft_input_is_typed_and_rejects_unknown_fields(env):
    data = payload(env)
    data['assignment']['unexpected'] = True
    assert env.client.post('/api/v1/teacher/teaching-preparations', json={'payload': data}).status_code == 422
    del data['assignment']['unexpected']
    data['ai']['web_search'] = 'true'
    assert env.client.post('/api/v1/teacher/teaching-preparations', json={'payload': data}).status_code == 422
