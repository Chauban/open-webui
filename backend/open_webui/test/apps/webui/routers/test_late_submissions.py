"""Deadlines label frozen submissions without closing the writing workflow."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.models.education import SubmissionReview
from open_webui.services.education.submission_timing import build_submission_timing
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    _setup_revise_draft_assignment,
    _setup_submitted_assignment,
    _submit_assignment,
)
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client as base_education_client,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import env as teaching_env
from open_webui.test.apps.webui.routers.test_teaching_trials import payload, prepare, publish, student_session

education_client = base_education_client
env = teaching_env


@pytest.mark.parametrize(
    'due_at,submitted_at,late', [(100, 99, False), (100, 100, True), (100, 101, True), (None, 101, False)]
)
def test_submission_timing_boundary(due_at, submitted_at, late):
    evidence = SimpleNamespace(assignment=SimpleNamespace(effective_due_at=due_at), submitted_at=submitted_at)
    assert build_submission_timing(evidence).is_late is late


def test_pending_resubmission_updates_timing_but_return_preserves_prior_round(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    assignment, _, first_id = _setup_submitted_assignment(client, teacher, student, reflection_questions=[])
    UserContext.current_user = teacher
    detail_url = f'/api/v1/teacher/submissions/{first_id}'
    assert client.get(detail_url).json()['timing']['is_late'] is False
    changed = client.patch(f'/api/v1/assignments/{assignment["id"]}', json={'due_at': 1})
    assert changed.status_code == 200, changed.text
    assert client.get(detail_url).json()['timing']['is_late'] is False

    UserContext.current_user = student
    replaced = _submit_assignment(client, assignment['id'])
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()['submission_id'] == first_id

    UserContext.current_user = teacher
    assert client.get(detail_url).json()['timing'] == {'effective_due_at': 1, 'is_late': True}
    returned = client.post(
        f'{detail_url}/review',
        json={
            'review_status': 'returned',
            'returned_comment': 'Revise the evidence',
            'resubmit_due_at': 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text
    # Simulate the return deadline passing without changing the frozen first round.
    with SessionLocal() as db:
        db.query(SubmissionReview).filter_by(submission_id=first_id).update({'resubmit_due_at': 2})
        db.commit()
    UserContext.current_user = student
    second = _submit_assignment(client, assignment['id'])
    assert second.status_code == 200, second.text
    assert second.json()['submission_id'] != first_id
    history = client.get(f'/api/v1/assignments/{assignment["id"]}/me/submissions').json()['rounds']
    assert [item['timing'] for item in history] == [
        {'effective_due_at': 1, 'is_late': True},
        {'effective_due_at': 2, 'is_late': True},
    ]


def test_late_revision_can_confirm_reset_and_submit_baseline(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id = _setup_revise_draft_assignment(client, teacher, student, due_at=1)
    baseline_url = f'/api/v1/writing-sessions/{session_id}/draft-baseline'
    for _ in range(2):
        confirmed = client.post(baseline_url, json={'text': 'A university writing draft. ' * 30})
        assert confirmed.status_code == 200, confirmed.text
        if _ == 0:
            reset = client.delete(baseline_url)
            assert reset.status_code == 200, reset.text
    submitted = _submit_assignment(client, assignment['id'])
    assert submitted.status_code == 200, submitted.text


def test_late_argument_can_confirm_baseline_and_submit(env):
    data = payload(env)
    data['assignment']['due_at'] = 1
    response = publish(env, prepare(env, data))
    assert response.status_code == 200, response.text
    assignment = response.json()[0]
    student_session(env, assignment)
    submitted = _submit_assignment(env.client, assignment['id'])
    assert submitted.status_code == 200, submitted.text
    UserContext.current_user = env.teacher
    detail = env.client.get(f'/api/v1/teacher/submissions/{submitted.json()["submission_id"]}').json()
    assert detail['timing'] == {'effective_due_at': 1, 'is_late': True}
