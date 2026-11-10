"""Submission must preserve the published fallback route in frozen evidence."""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from pydantic import ValidationError

from open_webui.test.apps.webui.routers.test_teaching_trials import (
    DRAFT,
    UserContext,
    _submit_body,
    education_client,
    env,
    prepare,
    publish,
    runtime,
    student_session,
)
from open_webui.models.education import Education, Submission
from open_webui.models.teaching_trials import AssignmentAiRevision, ModelBinding


FALLBACK = {
    'model_id': 'backup-model',
    'capabilities': {'reasoning': True, 'vision': False},
    'connection_hash': 'a' * 64,
}


@pytest.mark.parametrize('fallback', [None, FALLBACK])
def test_submission_preserves_published_fallback(env, monkeypatch, fallback):
    async def resolve_fallback(*args):
        return copy.deepcopy(fallback)

    monkeypatch.setattr('open_webui.utils.model_fallback.resolve_fallback', resolve_fallback)
    result = publish(env, prepare(env))
    assert result.status_code == 200, result.text
    assignment = result.json()[0]
    sid = student_session(env, assignment)
    with env.factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        config, call = runtime.capture_formal(session, 'fallback-call', 'coaching_chat', db, user=env.student)
        original_revision = copy.deepcopy(db.get(AssignmentAiRevision, config['ai_revision_id']).config)
    runtime.finish_formal(call, 'ready')

    UserContext.current_user = env.student
    submitted = env.client.post(f'/api/v1/assignments/{assignment["id"]}/submit', json=_submit_body(sid, DRAFT))
    assert submitted.status_code == 200, submitted.text
    with env.factory() as db:
        submission = db.get(Submission, submitted.json()['submission_id'])
        evidence = submission.stats_json['teaching_evidence']
        binding = evidence['revisions'][0]['config']['binding']
        assert binding.get('fallback') == fallback
        assert ('fallback' in binding) == (fallback is not None)
        assert evidence['calls'][0]['context']['config']['binding'].get('fallback') == fallback
        assert db.get(AssignmentAiRevision, config['ai_revision_id']).config == original_revision
        assert db.query(Submission).count() == 1


@pytest.mark.parametrize(
    'invalid', [{'api_key': 'not-a-real-secret'}, {'capabilities': {'vision': 'yes'}}, {'model_id': ''}]
)
def test_fallback_binding_rejects_invalid_fields(invalid):
    binding = {
        'model_id': 'primary',
        'base_model_id': 'primary',
        'workspace_model': False,
        'route': {'base_model_id': 'primary', 'url_index': 0},
        'params': {},
        'filter_fingerprint': 'filters',
        'thinking_support': {},
        'thinking_format': None,
        'capabilities': {},
        'fallback': {**FALLBACK, **invalid},
    }
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(binding)
