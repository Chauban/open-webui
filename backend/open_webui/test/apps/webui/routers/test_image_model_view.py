"""Teacher pages report the platform image model without changing model selection."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.services.education import ai_steps
from open_webui.test.apps.webui.routers.test_education_smoke import (
    UserContext,
    _set_image_model,
)
from open_webui.test.apps.webui.routers.test_education_smoke import (
    education_client as base_client,
)

education_client = base_client


@pytest.mark.parametrize(
    'choice,models,expected',
    [
        (None, {}, None),
        (
            'vision',
            {
                'vision': {
                    'id': 'vision',
                    'name': '图片模型',
                    'info': {'meta': {'capabilities': {'vision': True}, 'api_key': 'SHOULD_NOT_LEAK'}},
                }
            },
            {'id': 'vision', 'name': '图片模型', 'available': True},
        ),
        (
            'deleted',
            {'coaching': {'id': 'coaching', 'name': '辅导模型'}},
            {'id': 'deleted', 'name': 'deleted', 'available': False},
        ),
        (
            'text',
            {'text': {'id': 'text', 'info': {'meta': {'capabilities': {'vision': False}}}}},
            {'id': 'text', 'name': 'text', 'available': False},
        ),
    ],
)
def test_teacher_defaults_show_only_platform_image_model(education_client, choice, models, expected):
    client, teacher, _, student, _, _ = education_client
    _set_image_model(choice)
    client.app.state.MODELS = models
    UserContext.current_user = teacher
    response = client.get('/api/v1/teacher/assignment-defaults')
    assert response.status_code == 200, response.text
    assert response.json()['image_parsing_model'] == expected
    assert 'SHOULD_NOT_LEAK' not in response.text
    assert asyncio.run(ai_steps.get_ai_step_policy()).image_parsing.model == choice
    UserContext.current_user = student
    assert client.get('/api/v1/teacher/assignment-defaults').status_code == 403


def test_unconfigured_image_model_does_not_load_provider_catalog(monkeypatch):
    async def unexpected(*args):
        pytest.fail('A missing platform selection must not trigger model discovery')

    monkeypatch.setattr(ai_steps, 'available_models', unexpected)
    policy = SimpleNamespace(image_parsing=SimpleNamespace(model=None))
    assert asyncio.run(ai_steps.describe_image_parsing_model(None, None, policy)) is None
