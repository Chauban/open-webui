"""Every published assignment setting change requires an explicit explanation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from fastapi.testclient import TestClient
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    _rubric_schema,
    _setup_submitted_assignment,
)
from open_webui.test.apps.webui.routers.test_education_smoke import education_client as education_client


def create(client, teacher):
    UserContext.current_user = teacher
    classroom = client.post('/api/v1/classrooms', json={'name': '测试班'}).json()['classroom']
    result = client.post(
        '/api/v1/assignments',
        json={
            'title': '原题目',
            'classroom_ids': [classroom['id']],
            'due_at': 2000000000,
            'score_max': 100,
            'rubric_schema': _rubric_schema(),
        },
    )
    assert result.status_code == 200, result.text
    return result.json()[0]


@pytest.mark.parametrize(
    'changes',
    [
        {'title': '新题目'},
        {'description': '新要求'},
        {'due_at': 2000003600},
        {'score_max': 50, 'rubric_schema': _rubric_schema(50)},
        {'scoring_mode': 'total', 'rubric_schema': {'criteria': []}},
        {'rubric_schema': {'criteria': [{'key': 'argument', 'label': '论证', 'max_score': 100}]}},
        {'reflection_questions': []},
        {'coaching_style': 'hands_off'},
        {'photo_transcription_enabled': True},
        {'image_reading_enabled': True},
        {'challenge_enabled': True, 'challenge_focus_keys': ['ideas']},
        {'challenge_rounds': 2},
        {'task_mode': 'revise_draft'},
        {'model_params': {'thinking': 'medium', 'students_choose_thinking': False}},
        {'adopt_latest_teaching_config': True},
        {'classroom_id': 'other-classroom'},
    ],
)
def test_each_setting_requires_explanation_even_before_students_start(education_client, changes):
    client, teacher, _, _, _, _ = education_client
    assignment = create(client, teacher)
    response = TestClient.request(
        client,
        'PATCH',
        f'/api/v1/assignments/{assignment["id"]}',
        json={
            **changes,
            'expected_config_revision': assignment['config_revision'],
        },
    )
    assert response.status_code == 422, response.text
    assert any(issue['loc'][-1] == 'change_summary' for issue in response.json()['detail'])


@pytest.mark.parametrize('reason', [None, '', ' \n\t ', 'x' * 1001, 123])
def test_blank_invalid_or_oversized_explanation_is_rejected(education_client, reason):
    client, teacher, _, _, _, _ = education_client
    assignment = create(client, teacher)
    response = TestClient.request(
        client,
        'PATCH',
        f'/api/v1/assignments/{assignment["id"]}',
        json={
            'due_at': 2000003600,
            'expected_config_revision': assignment['config_revision'],
            'change_summary': reason,
        },
    )
    assert response.status_code == 422, response.text


def test_visibility_needs_no_explanation_and_preserves_last_setting_change(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, _, _ = _setup_submitted_assignment(client, teacher, student)
    UserContext.current_user = teacher
    url = f'/api/v1/assignments/{assignment["id"]}'
    updated = client.patch(
        url,
        json={
            'scoring_mode': 'total',
            'rubric_schema': {'criteria': []},
            'score_max': 50,
            'change_summary': '  按课堂情况调整评分  ',
        },
    )
    assert updated.status_code == 200, updated.text
    updated = updated.json()
    assert updated['change_summary'] == '按课堂情况调整评分'
    for hidden in (True, False):
        response = TestClient.request(client, 'PATCH', url + '/visibility', json={'hidden': hidden})
        assert response.status_code == 200, response.text
        assert response.json()['hidden'] is hidden
        assert response.json()['config_revision'] == updated['config_revision']
        assert response.json()['change_summary'] == '按课堂情况调整评分'
    stale = client.patch(
        url,
        json={
            'due_at': 2000003600,
            'expected_config_revision': assignment['config_revision'],
            'change_summary': '延期',
        },
    )
    assert stale.status_code == 409
