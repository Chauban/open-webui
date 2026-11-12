"""Scoring edits affect pending work while published grades keep their standard."""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.models.education import Education, Submission
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
)
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client as education_client,
)
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, submit


def scoring(mode, maximum):
    return {
        'scoring_mode': mode,
        'score_max': maximum,
        'rubric_schema': {
            'criteria': [{'key': 'argument', 'label': '论证质量', 'max_score': maximum}] if mode == 'dimensions' else []
        },
    }


def grade(config, value):
    return {
        'score': value,
        'rubric_scores': {'argument': value} if config['scoring_mode'] == 'dimensions' else None,
        'review_status': 'reviewed',
        'expected_scoring_config': config,
    }


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
@pytest.mark.parametrize('initial_mode', ['dimensions', 'total'])
def test_pending_uses_new_scoring_and_published_grades_keep_their_standard(education_client, mode, initial_mode):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode=mode, scoring=initial_mode)
    submitted = submit(client, assignment, sid).json()
    submission_id = submitted['submission_id']
    with factory() as db:
        original_stats = deepcopy(db.get(Submission, submission_id).stats_json)
        original_evidence = Education.get_latest_profile_evidence_snapshot(submission_id, db=db)
    UserContext.current_user = teacher
    detail_url = f'/api/v1/teacher/submissions/{submission_id}'
    review_url = detail_url + '/review'
    assignment_url = f'/api/v1/assignments/{assignment["id"]}'
    old = {key: assignment[key] for key in ('scoring_mode', 'score_max', 'rubric_schema')}
    new = scoring('total' if initial_mode == 'dimensions' else 'dimensions', 50)
    response = client.patch(assignment_url, json=new)
    assert response.status_code == 200, response.text
    detail = client.get(detail_url).json()
    for key in new:
        assert detail['assignment'][key] == new[key]
    stale = client.post(review_url, json={**grade(new, 40), 'expected_scoring_config': old})
    assert stale.status_code == 409, stale.text
    result = client.post(review_url, json=grade(new, 40))
    assert result.status_code == 200, result.text
    assert result.json()['scoring_config'] == new

    # Published grades (including explicit corrections) keep the earlier standard.
    latest = scoring('dimensions', 200)
    assert client.patch(assignment_url, json=latest).status_code == 200
    detail = client.get(detail_url).json()
    assert detail['assignment']['score_max'] == 50
    assert detail['review']['score'] == 40
    result = client.post(review_url, json=grade(new, 45))
    assert result.status_code == 200, result.text
    queue = client.get('/api/v1/teacher/review').json()['items']
    item = next(item for item in queue if item['submission']['id'] == submission_id)
    assert item['score'] == 45 and item['assignment']['score_max'] == 50
    roster = client.get(f'/api/v1/teacher/classrooms/{assignment["classroom_id"]}/members').json()
    assert next(item for item in roster if item['member']['user_id'] == student.id)['average_score_percent'] == 90
    UserContext.current_user = student
    workspace = client.get(assignment_url + '/workspace').json()
    assert workspace['assignment']['score_max'] == 200
    assert workspace['review']['score_max'] == 50
    assert workspace['review']['rubric_schema'] == new['rubric_schema']
    rounds = client.get(assignment_url + '/me/submissions').json()['rounds']
    assert rounds[0]['score_max'] == 50
    assert rounds[0]['rubric_schema'] == new['rubric_schema']
    profile = client.get('/api/v1/me/writing/profile').json()
    assert profile['timeline'][0]['score_max'] == 50
    assert profile['timeline'][0]['normalized_score'] == 90
    assert profile['portfolio_summary']['average_score_percent'] == 90
    assert profile['assignments'][0]['assignment']['score_max'] == 50
    with factory() as db:
        assert db.get(Submission, submission_id).stats_json == original_stats
        evidence = Education.get_latest_profile_evidence_snapshot(submission_id, db=db)
        assert evidence.evidence_hash == original_evidence.evidence_hash
        events = Education.get_submission_review_history(submission_id, db=db)
        assert [event.scoring_config.model_dump() for event in events] == [new, new]


def test_scoring_change_clears_incompatible_draft_scores_and_keeps_comments(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, mode='revise_draft', scoring='total')
    submitted = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    detail_url = f'/api/v1/teacher/submissions/{submitted["submission_id"]}'
    draft = client.post(
        detail_url + '/review',
        json={
            'review_status': 'pending',
            'score': 80,
            'overall_comment': '保留这条评语',
        },
    )
    assert draft.status_code == 200, draft.text
    new = scoring('dimensions', 60)
    assert client.patch(f'/api/v1/assignments/{assignment["id"]}', json=new).status_code == 200
    detail = client.get(detail_url).json()
    assert detail['review']['score'] is None
    assert detail['review']['rubric_scores'] is None
    assert detail['review']['overall_comment'] == '保留这条评语'
    assert detail['assignment']['rubric_schema'] == new['rubric_schema']
    response = client.post(detail_url + '/review', json=grade(new, 55))
    assert response.status_code == 200, response.text


def test_scoring_update_keeps_validation_permissions_and_other_locks(education_client):
    client, teacher, other_teacher, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, mode='revise_draft')
    assert submit(client, assignment, sid).status_code == 200
    url = f'/api/v1/assignments/{assignment["id"]}'
    UserContext.current_user = other_teacher
    assert client.patch(url, json=scoring('total', 50)).status_code == 403
    UserContext.current_user = teacher
    assert client.patch(url, json={'score_max': 0}).status_code == 422
    assert client.patch(url, json={'score_max': 50}).status_code == 400
    assert client.patch(url, json={'scoring_mode': 'total'}).status_code == 400
    assert client.patch(url, json={'task_mode': 'from_scratch'}).status_code == 409
    classroom = client.post('/api/v1/classrooms', json={'name': '另一个班'}).json()['classroom']
    assert client.patch(url, json={'classroom_id': classroom['id']}).status_code == 400
    assert client.patch(url, json={**scoring('total', 50), 'expected_config_revision': 0}).status_code == 422


@pytest.mark.parametrize('mode', ['total', 'dimensions'])
def test_populated_scoring_migration_preserves_original_grades_and_evidence(education_client, mode):
    import json

    import open_webui.env as env
    from alembic import command
    from alembic.config import Config
    from open_webui.test.util.database import BACKEND_ROOT, _run_migrations
    from sqlalchemy import text

    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode='revise_draft', scoring=mode)
    submitted = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    response = client.post(
        f'/api/v1/teacher/submissions/{submitted["submission_id"]}/review',
        json={
            'score': 90,
            'rubric_scores': {'ideas': 30, 'structure': 30, 'evidence': 30} if mode == 'dimensions' else None,
        },
    )
    assert response.status_code == 200, response.text
    assert client.patch(f'/api/v1/assignments/{assignment["id"]}', json=scoring('total', 200)).status_code == 200
    with factory() as db:
        engine = db.get_bind()
        url = engine.url.render_as_string(hide_password=False)
        before = dict(db.execute(text('SELECT * FROM submission_review_event')).mappings().one())
        evidence = dict(db.execute(text('SELECT * FROM profile_evidence_snapshot')).mappings().one())
        stats = db.get(Submission, submitted['submission_id']).stats_json
    config = Config(str(BACKEND_ROOT / 'open_webui' / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_ROOT / 'open_webui' / 'migrations'))
    original = env.DATABASE_URL
    env.DATABASE_URL = url
    try:
        command.downgrade(config, 'b8d0f2a476c9')
    finally:
        env.DATABASE_URL = original
    _run_migrations(url)
    with factory() as db:
        after = dict(db.execute(text('SELECT * FROM submission_review_event')).mappings().one())
        assert json.loads(after.pop('scoring_config')) == json.loads(before.pop('scoring_config'))
        assert after == before
        assert dict(db.execute(text('SELECT * FROM profile_evidence_snapshot')).mappings().one()) == evidence
        assert db.get(Submission, submitted['submission_id']).stats_json == stats
        review = Education.get_submission_review_by_submission_id(submitted['submission_id'], db=db)
        assert review.score == 90
        assert review.scoring_config.score_max == 100
        assert review.scoring_config.scoring_mode == mode


@pytest.mark.parametrize('change_standard', [False, True])
def test_round_progress_only_compares_scores_under_the_same_standard(education_client, change_standard):
    import asyncio

    from open_webui.models.config import Config

    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, mode='revise_draft', scoring='total')
    first = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    asyncio.run(Config.upsert({'education.enable_return': True}))
    returned = client.post(
        f'/api/v1/teacher/submissions/{first["submission_id"]}/review',
        json={
            'review_status': 'returned',
            'score': 80,
            'returned_comment': '请补充证据',
            'resubmit_due_at': 2000000000,
        },
    )
    assert returned.status_code == 200, returned.text
    if change_standard:
        assert client.patch(f'/api/v1/assignments/{assignment["id"]}', json=scoring('total', 50)).status_code == 200
    UserContext.current_user = student
    second = submit(client, assignment, sid).json()
    UserContext.current_user = teacher
    response = client.post(
        f'/api/v1/teacher/submissions/{second["submission_id"]}/review',
        json={
            'score': 45 if change_standard else 90,
        },
    )
    assert response.status_code == 200, response.text
    UserContext.current_user = student
    profile = client.get('/api/v1/me/writing/profile').json()
    assert profile['round_progress'][0]['score_delta'] == (None if change_standard else 10)
