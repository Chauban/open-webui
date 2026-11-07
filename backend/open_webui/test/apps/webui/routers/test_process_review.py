import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
import pytest
from open_webui.services.education.process_review import build_process_catalog, catalog_metadata, compare_snapshots
from open_webui.test.apps.webui.routers.test_education_smoke import education_client, UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, submit, DRAFT


def facts():
    return {
        'round_no': 1,
        'draft_baseline_text': '初稿。',
        'submitted_at': 10,
        'document': {'final_version_id': 'vf', 'content_text': '终稿。'},
        'versions': [
            {'id': 'v1', 'version_no': 1, 'trigger_type': 'autosave', 'created_at': 2, 'content_text': '第一改稿。'},
            {'id': 'v2', 'version_no': 2, 'trigger_type': 'autosave', 'created_at': 3, 'content_text': '第二改稿。'},
            {'id': 'vf', 'version_no': 3, 'trigger_type': 'submit', 'created_at': 10, 'content_text': '终稿。'},
        ],
    }


def test_catalog_binds_exact_reading_and_parent_without_guessing_by_time():
    stats = {
        'revision_readings': [{'id': 'r', 'source_text': '初稿。', 'created_at': 1}],
        'prompt_timeline': [
            {'id': 'chat-u', 'role': 'user'},
            {'id': 'chat-a', 'chat_id': 'chat', 'role': 'assistant', 'parent_id': 'u', 'created_at': 4},
        ],
        'chat_contexts': [
            {'message_id': 'chat-a', 'source_version_id': 'v1', 'source_text': '第一改稿。', 'called_at': 4}
        ],
    }
    catalog = build_process_catalog(facts(), stats)
    assert catalog['event_snapshots'] == {
        'reading:r': 'initial',
        'prompt:chat-a': 'version:v1',
        'prompt:chat-u': 'version:v1',
    }
    rows = {row['id']: row for row in catalog['snapshots']}
    assert rows['version:v1']['major'] and not rows['version:v2']['major']
    assert all('text' not in row for row in catalog_metadata(catalog)['snapshots'])
    result = compare_snapshots(catalog, 'initial', 'final')
    assert ''.join(row['old_text'] for row in result['blocks']) == '初稿。'
    assert ''.join(row['new_text'] for row in result['blocks']) == '终稿。'
    assert compare_snapshots(catalog, 'final', 'final')['unchanged']
    with pytest.raises(Exception):
        compare_snapshots(catalog, 'foreign', 'final')


def test_mismatched_version_id_keeps_actual_model_snapshot_and_empty_start():
    source = facts()
    source['draft_baseline_text'] = None
    catalog = build_process_catalog(
        source,
        {
            'prompt_timeline': [{'id': 'a', 'role': 'assistant', 'created_at': 4}],
            'chat_contexts': [
                {'message_id': 'a', 'source_version_id': 'v1', 'source_text': '实际给模型的不同稿件', 'called_at': 4}
            ],
        },
    )
    assert catalog['event_snapshots']['prompt:a'] != 'version:v1'
    record = next(row for row in catalog['snapshots'] if row['id'] == catalog['event_snapshots']['prompt:a'])
    assert record['text'] == '实际给模型的不同稿件'
    assert catalog['snapshots'][0]['kind'] == 'empty_start'


def test_process_api_is_frozen_scoped_and_rejects_resubmit_conflict(education_client):
    client, teacher, other_teacher, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    version = client.post(
        f'/api/v1/writing-sessions/{sid}/versions',
        json={'trigger_type': 'autosave', 'content_text': DRAFT + '中间修改。'},
    ).json()
    first = submit(client, assignment, sid).json()
    endpoint = f'/api/v1/teacher/submissions/{first["submission_id"]}/process'
    params = {'expected_final_version_id': first['final_version_id']}
    UserContext.current_user = teacher
    response = client.get(endpoint, params=params)
    assert response.status_code == 200, response.text
    original = response.json()
    snapshot = 'version:' + version['id']
    assert any(row['id'] == snapshot for row in original['snapshots'])
    compared = client.get(endpoint + '/compare', params={**params, 'before': 'initial', 'after': snapshot})
    assert compared.status_code == 200, compared.text
    assert compared.json()['after']['text'] == DRAFT + '中间修改。'
    UserContext.current_user = other_teacher
    assert client.get(endpoint, params=params).status_code in (403, 404)
    UserContext.current_user = student
    assert client.get(endpoint, params=params).status_code == 403
    later = client.post(
        f'/api/v1/writing-sessions/{sid}/versions', json={'trigger_type': 'autosave', 'content_text': '尚未提交的新稿'}
    ).json()
    UserContext.current_user = teacher
    assert client.get(endpoint, params=params).json() == original
    assert (
        client.get(
            endpoint + '/compare', params={**params, 'before': 'initial', 'after': 'version:' + later['id']}
        ).status_code
        == 404
    )
    listed = client.get(f'/api/v1/teacher/submissions/{first["submission_id"]}/versions').json()
    assert later['id'] not in [row['id'] for row in listed]
    UserContext.current_user = student
    changed = submit(
        client,
        assignment,
        sid,
        final_content_text=DRAFT + '重新提交。',
        final_content_html='<p>' + DRAFT + '重新提交。</p>',
    )
    assert changed.status_code == 200, changed.text
    UserContext.current_user = teacher
    assert client.get(endpoint, params=params).status_code == 409
    assert (
        client.get(endpoint + '/compare', params={**params, 'before': 'initial', 'after': 'final'}).status_code == 409
    )


def test_regenerated_replies_with_different_drafts_do_not_mislabel_parent_question():
    stats = {
        'prompt_timeline': [
            {'id': 'u', 'role': 'user'},
            {'id': 'a', 'role': 'assistant', 'parent_id': 'u'},
            {'id': 'b', 'role': 'assistant', 'parent_id': 'u'},
        ],
        'chat_contexts': [
            {'message_id': 'a', 'source_version_id': 'v1', 'source_text': '第一改稿。'},
            {'message_id': 'b', 'source_version_id': 'v2', 'source_text': '第二改稿。'},
        ],
    }
    catalog = build_process_catalog(facts(), stats)
    assert catalog['event_snapshots']['prompt:a'] == 'version:v1'
    assert catalog['event_snapshots']['prompt:b'] == 'version:v2'
    assert 'prompt:u' not in catalog['event_snapshots']
