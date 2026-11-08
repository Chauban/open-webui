"""Comparison persistence, immutable retention and ownership with real migrations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor

from open_webui.test.apps.webui.routers.test_teaching_trials import (
    DRAFT,
    UserContext,
    action,
    payload,
    prepare,
    publish,
    trial,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    education_client as education_client,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    env as env,
)


def open_work(env, prep=None):
    prep = prep or prepare(env)
    seed = trial(env, prep)
    response = env.client.post(
        '/api/v1/teacher/teaching-workbenches', json={'trial_id': seed['id'], 'preparation_id': prep['id']}
    )
    assert response.status_code == 200, response.text
    return prep, response.json()


def run(env, work, **extra):
    response = env.client.post(
        f'/api/v1/teacher/teaching-workbenches/{work["id"]}/comparisons',
        json={'expected_revision': work['revision'], 'idempotency_key': str(uuid.uuid4()), **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_workbench_independent_input_conflict_and_batch_idempotency(env):
    prep, work = open_work(env)
    data = copy.deepcopy(work['payload'])
    data.update(title='试教新题目', description='试教新要求', sample=DRAFT)
    data['candidates'].append({**data['candidates'][0], 'model_id': 'model-B'})
    endpoint = f'/api/v1/teacher/teaching-workbenches/{work["id"]}'
    body = {'expected_revision': work['revision'], 'payload': data}
    response = env.client.put(endpoint, json=body)
    assert response.status_code == 200, response.text
    work = response.json()
    assert env.client.put(endpoint, json=body).status_code == 409
    assert env.client.get(f'/api/v1/teacher/teaching-preparations/{prep["id"]}').json()['payload'] == prep['payload']
    key = str(uuid.uuid4())
    group = run(env, work, idempotency_key=key)
    assert run(env, work, idempotency_key=key)['id'] == group['id']
    assert len(group['trials']) == 2
    assert {t['config']['ai']['model_id'] for t in group['trials']} == {'model-A', 'model-B'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda t: action(env, t, 'confirm', DRAFT), group['trials']))
    assert all(r.status_code == 200 for r in results)
    assert all(r.json()['events'][-1]['call']['status'] == 'ready' for r in results)
    listed = env.client.get(endpoint + '/comparisons').json()
    assert len(listed) == 1 and len(listed[0]['trials'][0]['state']['dialogue']) == 1


def test_candidate_limit_and_shared_prompt_are_server_enforced(env):
    _, work = open_work(env)
    path = f'/api/v1/teacher/teaching-workbenches/{work["id"]}'
    data = copy.deepcopy(work['payload'])
    data['candidates'] *= 4
    assert env.client.put(path, json={'expected_revision': 1, 'payload': data}).status_code == 422
    data['candidates'] = data['candidates'][:2]
    assert env.client.put(path, json={'expected_revision': 1, 'payload': data}).status_code == 422
    data['candidates'][1] = {**data['candidates'][1], 'model_id': 'model-B', 'prompt': 'different'}
    assert env.client.put(path, json={'expected_revision': 1, 'payload': data}).status_code == 422


def test_retention_uses_output_snapshot_and_adoption_is_explicit(env):
    prep, work = open_work(env)
    group = run(env, work)
    tested = group['trials'][0]
    endpoint = '/api/v1/teacher/saved-teaching-plans'
    body = {'trial_id': tested['id'], 'name': '满意的方案'}
    assert env.client.post(endpoint, json=body).status_code == 409
    tested = action(env, tested, 'confirm', DRAFT).json()
    changed = copy.deepcopy(work['payload'])
    changed['candidates'][0]['prompt'] = '后来修改的提示词'
    assert (
        env.client.put(
            f'/api/v1/teacher/teaching-workbenches/{work["id"]}', json={'expected_revision': 1, 'payload': changed}
        ).status_code
        == 200
    )
    plan = env.client.post(endpoint, json=body).json()
    assert plan['config']['ai']['prompt'] == tested['config']['ai']['prompt']
    assert env.client.post(endpoint, json=body).json()['id'] == plan['id']
    target = prepare(env, payload(env, title='另一个题目'))
    path = f'{endpoint}/{plan["id"]}/adopt/{target["id"]}'
    response = env.client.post(
        path, json={'expected_revision': target['revision'], 'include_task': True, 'idempotency_key': str(uuid.uuid4())}
    )
    assert response.status_code == 200, response.text
    assert response.json()['payload']['assignment']['title'] == tested['config']['title']
    assert response.json()['published'] is None
    assert (
        env.client.post(
            path,
            json={'expected_revision': target['revision'], 'include_task': True, 'idempotency_key': str(uuid.uuid4())},
        ).status_code
        == 409
    )


def test_other_teacher_cannot_read_run_or_retain_private_resources(env):
    prep, work = open_work(env)
    group = run(env, work)
    tested = action(env, group['trials'][0], 'confirm', DRAFT).json()
    plan = env.client.post(
        '/api/v1/teacher/saved-teaching-plans', json={'trial_id': tested['id'], 'name': 'private'}
    ).json()
    UserContext.current_user = env.other
    assert env.client.get('/api/v1/teacher/saved-teaching-plans').json() == []
    assert env.client.get(f'/api/v1/teacher/teaching-workbenches/{work["id"]}/comparisons').status_code == 404
    assert (
        env.client.post(
            '/api/v1/teacher/teaching-workbenches', json={'trial_id': tested['id'], 'preparation_id': prep['id']}
        ).status_code
        == 404
    )
    assert (
        env.client.post(
            '/api/v1/teacher/saved-teaching-plans', json={'trial_id': tested['id'], 'name': 'stolen'}
        ).status_code
        == 404
    )
    assert (
        env.client.post(
            f'/api/v1/teacher/saved-teaching-plans/{plan["id"]}/adopt/{prep["id"]}',
            json={'expected_revision': 1, 'idempotency_key': str(uuid.uuid4())},
        ).status_code
        == 404
    )


def test_existing_assignment_adoption_does_not_edit_task(env):
    prep, work = open_work(env)
    group = run(env, work)
    tested = action(env, group['trials'][0], 'confirm', DRAFT).json()
    plan = env.client.post(
        '/api/v1/teacher/saved-teaching-plans', json={'trial_id': tested['id'], 'name': 'retain'}
    ).json()
    assignment = publish(env, prep).json()[0]
    target = prepare(env, assignment_id=assignment['id'])
    path = f'/api/v1/teacher/saved-teaching-plans/{plan["id"]}/adopt/{target["id"]}'
    assert (
        env.client.post(
            path, json={'expected_revision': 1, 'include_task': True, 'idempotency_key': str(uuid.uuid4())}
        ).status_code
        == 400
    )
    result = env.client.post(
        path, json={'expected_revision': 1, 'include_task': False, 'idempotency_key': str(uuid.uuid4())}
    )
    assert result.status_code == 200, result.text
    assert result.json()['payload']['assignment']['title'] == assignment['title']


def test_removed_trial_actions_rejected_and_branch_is_independent(env):
    _, work = open_work(env)
    tested = run(env, work)['trials'][0]
    for removed in ['whole_review', 'revision_review', 'evaluate']:
        assert action(env, tested, removed, 'test').status_code == 422
    tested = action(env, tested, 'confirm', DRAFT).json()
    group = run(env, work, source_trial_id=tested['id'], source_sequence=tested['sequence'])
    child = group['trials'][0]
    assert child['state']['dialogue'] == tested['state']['dialogue']
    assert child['state']['draft'] == DRAFT
    assert child['id'] != tested['id']


def test_adoption_network_retry_returns_original_receipt(env):
    prep, work = open_work(env)
    tested = action(env, run(env, work)['trials'][0], 'confirm', DRAFT).json()
    plan = env.client.post(
        '/api/v1/teacher/saved-teaching-plans', json={'trial_id': tested['id'], 'name': 'stable'}
    ).json()
    path = f'/api/v1/teacher/saved-teaching-plans/{plan["id"]}/adopt/{prep["id"]}'
    body = {'expected_revision': 1, 'include_task': True, 'idempotency_key': str(uuid.uuid4())}
    first = env.client.post(path, json=body)
    assert first.status_code == 200, first.text
    assert env.client.post(path, json=body).json() == first.json()
    assert env.client.post(path, json={**body, 'include_task': False}).status_code == 409


def test_independent_parallel_calls_and_retry_keeps_original_input(env, monkeypatch):
    import asyncio
    import threading

    from open_webui.services.education import teaching_trials as service

    _, work = open_work(env)
    data = copy.deepcopy(work['payload'])
    data['candidates'].append({**data['candidates'][0], 'model_id': 'model-B'})
    response = env.client.put(
        f'/api/v1/teacher/teaching-workbenches/{work["id"]}', json={'expected_revision': 1, 'payload': data}
    )
    group = run(env, response.json())
    started = set()
    guard = threading.Lock()
    release = threading.Event()
    inputs = []

    async def delayed(request, user, config, context, paragraphs):
        with guard:
            started.add(config['ai']['model_id'])
            inputs.append(context['source_text'])
            if len(started) == 2:
                release.set()
        assert await asyncio.to_thread(release.wait, 5), 'Models ran serially'
        if config['ai']['model_id'] == 'model-B':
            raise ValueError('isolated provider failure')
        return {'understanding': '', 'strength': None, 'focus': [], 'overview': 'successful A'}

    monkeypatch.setattr(service, 'execute_first_read', delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda t: action(env, t, 'confirm', DRAFT).json(), group['trials']))
    assert [r['events'][-1]['call']['status'] for r in results] == ['ready', 'failed']
    failed = results[1]
    retry = action(env, failed, 'retry', 'this must not replace the original sample').json()
    assert retry['events'][-1]['call']['source_text'] == DRAFT
    assert inputs == [DRAFT, DRAFT, DRAFT]
    assert retry['state']['dialogue'] == failed['state']['dialogue']
    first = env.client.get(f'/api/v1/teacher/teaching-trials/{results[0]["id"]}').json()
    assert first['state']['dialogue'] == results[0]['state']['dialogue']
