"""AI 步骤的模型：管理员可为平台步骤指定模型，没指定跟学生 / 教师选的；实际用的模型随轮次冻存。"""

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.config import DEFAULT_EDUCATION_AI_STEPS
from open_webui.models.config import Config
from open_webui.models.education import ChallengeTurn, Submission, WritingSession
from open_webui.test.apps.webui.routers.test_education_smoke import (
    _DRAFT_MD,
    UserContext,
    _fake_challenge_model,
    _fake_diagnosis,
    _respond,
    _revise_draft_with_baseline,
    _setup_challenge_assignment,
    _start_challenge,
    _start_first_read,
    _submit_body,
    education_client,  # noqa: F401  pytest fixture
)

# 学生在写作区选的是 test-model；管理员可指定的模型
MODELS = {
    'test-model': {'id': 'test-model', 'name': 'Student pick'},
    'reader-model': {'id': 'reader-model', 'name': 'Reader'},
    'diagnosis-model': {'id': 'diagnosis-model', 'name': 'Diagnosis'},
}


def _set_step_models(**models):
    steps = {
        key: ({**value, 'model': models[key]} if key in models else value)
        for key, value in DEFAULT_EDUCATION_AI_STEPS.items()
    }
    asyncio.run(Config.upsert({'education.ai_steps': steps}))


def test_reader_check_uses_the_admin_model_and_freezes_it(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    client.app.state.MODELS = MODELS
    _set_step_models(reader_check='reader-model')
    assignment, session_id = _setup_challenge_assignment(client, teacher, student, rounds=2)

    with _fake_challenge_model() as calls:
        challenge = _start_challenge(client, assignment['id'], session_id)
        assert challenge.status_code == 200, challenge.text
        challenge_id = challenge.json()['session']['id']
        for turn_no in (1, 2):
            assert _respond(client, challenge_id, turn_no).status_code == 200

    # 学生选的是 test-model，质疑与收尾都按管理员指定的模型发出
    assert {call['model'] for call in calls} == {'reader-model'}
    with SessionLocal() as db:
        assert {turn.model_id for turn in db.query(ChallengeTurn).all()} == {'reader-model'}

    submit = client.post(
        f'/api/v1/assignments/{assignment["id"]}/submit',
        json=_submit_body(session_id, 'final essay text after the reader check'),
    )
    assert submit.status_code == 200, submit.text
    with SessionLocal() as db:
        stats = db.get(Submission, submit.json()['submission_id']).stats_json
    assert stats['challenge']['models'] == ['reader-model']


_ALL_OK = {
    'items': [
        {'key': key, 'status': 'ok', 'finding': '', 'quote': ''} for key in ('ideas', 'structure', 'evidence')
    ]
}


def _first_read_model(client, teacher, student, SessionLocal):
    _, session_id = _revise_draft_with_baseline(client, teacher, student)
    with _fake_diagnosis(_ALL_OK) as calls:
        res = _start_first_read(client, session_id)
        assert res.json()['status'] == 'ready', res.text
    with SessionLocal() as db:
        recorded = db.get(WritingSession, session_id).revision_items_model_id
    return calls[0]['model_id'], recorded, session_id


def test_first_read_follows_the_student_until_the_admin_picks_a_model(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    client.app.state.MODELS = MODELS

    assert _first_read_model(client, teacher, student, SessionLocal)[:2] == ('test-model', 'test-model')


def test_first_read_uses_the_admin_model_and_freezes_it(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    client.app.state.MODELS = MODELS
    _set_step_models(first_read='diagnosis-model')

    used, recorded, session_id = _first_read_model(client, teacher, student, SessionLocal)
    assert (used, recorded) == ('diagnosis-model', 'diagnosis-model')

    UserContext.current_user = student
    with SessionLocal() as db:
        assignment_id = db.get(WritingSession, session_id).assignment_id
    submit = client.post(f'/api/v1/assignments/{assignment_id}/submit', json=_submit_body(session_id, _DRAFT_MD))
    assert submit.status_code == 200, submit.text
    with SessionLocal() as db:
        stats = db.get(Submission, submit.json()['submission_id']).stats_json
    assert stats['revision_items']['models'] == {'first_read': 'diagnosis-model', 'follow_up': None}


def test_deleted_admin_model_falls_back_to_the_student_pick(education_client):
    client, teacher, _, student, _, SessionLocal = education_client
    client.app.state.MODELS = MODELS
    _set_step_models(first_read='deleted-model')

    assert _first_read_model(client, teacher, student, SessionLocal)[:2] == ('test-model', 'test-model')
