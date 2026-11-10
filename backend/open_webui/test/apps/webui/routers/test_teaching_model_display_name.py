"""Student teaching labels use current administrator names without changing bindings."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.models.models import Model
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    UserContext,
    prepare,
    publish,
    student_session,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    education_client as base_education_client,
)
from open_webui.test.apps.webui.routers.test_teaching_trials import (
    env as base_env,
)

education_client = base_education_client
env = base_env


def test_student_summary_reads_saved_name_and_administrator_rename(env):
    result = publish(env, prepare(env))
    assert result.status_code == 200, result.text
    sid = student_session(env, result.json()[0])
    url = f'/api/v1/writing-sessions/{sid}/teaching-summary'
    with env.factory() as db:
        db.add(
            Model(
                id='model-A',
                name='课程助教',
                user_id=env.teacher.id,
                params={'system': 'PRIVATE_PROMPT'},
                meta={},
                created_at=1,
                updated_at=1,
            )
        )
        db.commit()

    response = env.client.get(url)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary['name'] == '课程助教'
    assert summary['id'] == 'model-A'
    assert 'PRIVATE_PROMPT' not in response.text

    # The process cache still holds the ID as name; changing the saved name must
    # take effect without republishing the assignment or granting chat access.
    with env.factory() as db:
        db.get(Model, 'model-A').name = '写作伙伴'
        db.commit()
    renamed = env.client.get(url).json()
    assert renamed == {**summary, 'name': '写作伙伴'}
    assert env.calls == []

    UserContext.current_user = env.other
    assert env.client.get(url).status_code in (403, 404)


@pytest.mark.parametrize('catalog_name', ['提供方名称', None])
def test_unconfigured_name_uses_catalog_then_id(env, catalog_name):
    result = publish(env, prepare(env))
    assert result.status_code == 200, result.text
    sid = student_session(env, result.json()[0])
    env.client.app.state.MODELS['model-A']['name'] = catalog_name
    response = env.client.get(f'/api/v1/writing-sessions/{sid}/teaching-summary')
    assert response.status_code == 200, response.text
    assert response.json()['name'] == (catalog_name or 'model-A')
    assert response.json()['id'] == 'model-A'
