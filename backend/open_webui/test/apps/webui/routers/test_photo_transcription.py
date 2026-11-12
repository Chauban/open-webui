"""Photo prose and reference images use independent permissions and models."""

import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.models.config import Config
from open_webui.models.education import Submission
from open_webui.services.education import ai_steps, materials
from open_webui.services.education.writing_document import document_text
from open_webui.test.apps.webui.routers.test_education_smoke import UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import DRAFT, setup, submit
from open_webui.test.apps.webui.routers.test_writing_materials import (
    education_client as base_client,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    picture,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    storage as isolated_storage,
)

education_client = base_client
storage = isolated_storage


def set_photo(client, teacher, student, assignment, enabled):
    UserContext.current_user = teacher
    current = client.get(f'/api/v1/teacher/assignments/{assignment["id"]}').json()['assignment']
    response = client.patch(
        f'/api/v1/assignments/{assignment["id"]}',
        json={
            'expected_config_revision': current['config_revision'],
            'photo_transcription_enabled': enabled,
        },
    )
    UserContext.current_user = student
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def models(education_client, monkeypatch):
    client = education_client[0]
    policy = asyncio.run(ai_steps.get_ai_step_policy()).model_dump()
    policy['photo_transcription'] = {'model': 'photo', 'thinking': 'off'}
    policy['image_parsing'] = {'model': 'reference', 'thinking': 'low'}
    asyncio.run(Config.upsert({'education.ai_steps': policy}))
    client.app.state.MODELS = {
        name: {'id': name, 'info': {'meta': {'capabilities': {'vision': True}}}} for name in ('photo', 'reference')
    }
    calls = []

    async def provider(request, form_data, user, **kwargs):
        calls.append(copy.deepcopy(form_data))
        return {'choices': [{'message': {'content': DRAFT}, 'finish_reason': 'stop'}]}

    monkeypatch.setattr(ai_steps, 'generate_chat_completion', provider)
    return calls


def upload(client, sid, purpose):
    return client.post(
        f'/api/v1/writing-sessions/{sid}/import/images',
        data={'purpose': purpose},
        files=[('files', ('handwriting.png', picture(), 'image/png'))],
    )


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
def test_photo_becomes_prose_without_reference_permission_and_freezes_original(
    education_client,
    storage,
    models,
    mode,
):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    if mode != 'from_scratch':
        assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200
    assignment = set_photo(client, teacher, student, assignment, True)
    assert assignment['image_reading_enabled'] is False
    client.app.state.MODELS.update(
        {name: {'id': name, 'info': {'meta': {'capabilities': {'vision': True}}}} for name in ('photo', 'reference')}
    )
    response = upload(client, sid, 'photo_to_text')
    assert response.status_code == 200, response.text
    imported = response.json()
    assert imported['text'] == document_text(imported['content_json']) == DRAFT
    assert all(node['type'] == 'paragraph' for node in imported['content_json']['content'])
    assert models[0]['model'] == 'photo'
    assert '只转录，不改写' in models[0]['messages'][0]['content']
    mid = imported['materials'][0]['id']
    assert client.get(f'/api/v1/writing-materials/{mid}/assets/original').content == picture()
    if mode != 'from_scratch':
        pending = client.put(
            f'/api/v1/writing-sessions/{sid}/pending-draft',
            json={
                'content_json': imported['content_json'],
                'materials': [{'id': mid}],
                'expected_revision': 0,
            },
        )
        assert pending.status_code == 200, pending.text
        confirmed = client.post(
            f'/api/v1/writing-sessions/{sid}/draft-baseline',
            json={
                'content_json': imported['content_json'],
                'materials': [{'id': mid}],
                'expected_draft_revision': 1,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
    else:
        attached = client.post(f'/api/v1/writing-sessions/{sid}/materials', json={'materials': [{'id': mid}]})
        assert attached.status_code == 200, attached.text
    saved = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': imported['content_json']})
    assert saved.status_code == 200, saved.text
    with factory() as db:
        assert materials.model_materials(sid, True, db) == []  # Source photos are not reference attachments.
    submitted = submit(client, assignment, sid, final_content_json=imported['content_json'], final_content_text=DRAFT)
    assert submitted.status_code == 200, submitted.text
    set_photo(client, teacher, student, assignment, False)
    with factory() as db:
        frozen = db.get(Submission, submitted.json()['submission_id']).stats_json
        assert frozen['assignment_config']['photo_transcription_enabled'] is True
        assert mid in {m['id'] for m in frozen['materials']}


def test_reference_never_auto_reads_and_uses_only_reference_model_on_request(education_client, storage, models):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch', image_reading=True)
    assert assignment['photo_transcription_enabled'] is False
    assert upload(client, sid, 'photo_to_text').status_code == 403
    response = upload(client, sid, 'reference')
    assert response.status_code == 200, response.text
    imported = response.json()
    assert imported['text'] == '' and models == []
    assert imported['content_json']['content'][0]['type'] == 'writingImage'
    material = imported['materials'][0]
    read = client.post(f'/api/v1/writing-sessions/{sid}/materials/{material["id"]}/read', params={'block_id': 'm1'})
    assert read.status_code == 200, read.text
    assert models[0]['model'] == 'reference'
    assert '文档材料识读工具' in models[0]['messages'][0]['content']


@pytest.mark.parametrize('who', ['teacher', 'admin'])
def test_both_settings_are_editable_by_authorized_teachers_and_admins(education_client, who):
    client, teacher, outsider, student, _, _ = education_client
    assignment, _, _ = setup(client, teacher, student, 'from_scratch')
    url = f'/api/v1/assignments/{assignment["id"]}'
    payload = {
        'expected_config_revision': assignment['config_revision'],
        'photo_transcription_enabled': True,
        'image_reading_enabled': False,
    }
    assert client.patch(url, json=payload).status_code == 403
    UserContext.current_user = outsider
    assert client.patch(url, json=payload).status_code == 403
    UserContext.current_user = teacher if who == 'teacher' else teacher.model_copy(update={'role': 'admin'})
    assert client.patch(url, json={**payload, 'photo_transcription_enabled': 'true'}).status_code == 422
    result = client.patch(url, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['photo_transcription_enabled'] is True
    assert result.json()['image_reading_enabled'] is False


def test_photo_disabled_during_conversion_does_not_return_prose(education_client, storage, models, monkeypatch):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch')
    set_photo(client, teacher, student, assignment, True)

    async def provider(*args, **kwargs):
        set_photo(client, teacher, student, assignment, False)
        return {'choices': [{'message': {'content': 'DO_NOT_RETURN'}, 'finish_reason': 'stop'}]}

    monkeypatch.setattr(ai_steps, 'generate_chat_completion', provider)
    result = upload(client, sid, 'photo_to_text')
    assert result.status_code == 403
    assert 'DO_NOT_RETURN' not in result.text


def test_upload_requires_explicit_valid_intent(education_client, storage):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch')
    assert upload(client, sid, 'guess').status_code == 422


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
@pytest.mark.parametrize('purpose', ['photo_to_text', 'reference'])
def test_both_image_actions_work_after_baseline_without_replacing_it(education_client, storage, models, mode, purpose):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    set_photo(client, teacher, student, assignment, True)
    client.app.state.MODELS.update(
        {name: {'id': name, 'info': {'meta': {'capabilities': {'vision': True}}}} for name in ('photo', 'reference')}
    )
    imported = upload(client, sid, purpose)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    mid = body['materials'][0]['id']
    attached = client.post(f'/api/v1/writing-sessions/{sid}/materials', json={'materials': [{'id': mid}]})
    assert attached.status_code == 200, attached.text
    saved = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': body['content_json']})
    assert saved.status_code == 200, saved.text
    from open_webui.models.education import Education

    with factory() as db:
        assert Education.get_writing_session_by_id(sid, db=db).draft_baseline_text == DRAFT
        assert mid in {m['id'] for m in materials.snapshot_materials(sid, db)}


def test_before_baseline_materials_must_be_confirmed_with_the_draft(education_client, storage):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'revise_draft')
    assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200
    imported = upload(client, sid, 'reference').json()
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/materials', json={'materials': [{'id': imported['materials'][0]['id']}]}
    )
    assert result.status_code == 400


def test_blank_reference_is_valid_but_blank_photo_cannot_silently_become_prose(
    education_client, storage, models, monkeypatch
):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch', image_reading=True)
    set_photo(client, teacher, student, assignment, True)

    async def provider(*args, **kwargs):
        return {'choices': [{'message': {'content': '<<NO_TEXT>>'}, 'finish_reason': 'stop'}]}

    monkeypatch.setattr(ai_steps, 'generate_chat_completion', provider)
    assert upload(client, sid, 'photo_to_text').status_code == 400
    imported = upload(client, sid, 'reference').json()
    reference = imported['materials'][0]
    result = client.post(f'/api/v1/writing-sessions/{sid}/materials/{reference["id"]}/read', params={'block_id': 'm1'})
    assert result.status_code == 200, result.text
    assert result.json()['blocks'][0]['status'] == 'read'
    assert result.json()['blocks'][0]['text'] == ''

    document = imported['content_json']
    document['content'][0]['attrs'].update(materialId=result.json()['material_id'], readStatus='read')
    saved = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document})
    assert saved.status_code == 200, saved.text
    with factory() as db:
        block = materials.model_materials(sid, True, db)[0]['blocks'][0]
        assert block['status'] == 'read'
        assert block['detail'] == '未发现可提取文字，原图已保留。'


def test_photo_migration_preserves_reference_policy_and_starts_disabled():
    import sqlalchemy as sa
    from open_webui.test.util.database import _run_migrations, migration_database_at

    with migration_database_at('a7c9e1f365b8') as url:
        engine = sa.create_engine(url)
        table = sa.table('config', sa.column('key', sa.Text), sa.column('value', sa.JSON))
        previous = {'image_parsing': {'model': 'original-reference', 'thinking': 'low'}}
        with engine.begin() as connection:
            connection.execute(table.insert().values(key='education.ai_steps', value=previous))
        _run_migrations(url)
        with engine.connect() as connection:
            policy = connection.execute(
                sa.select(table.c.value).where(table.c.key == 'education.ai_steps')
            ).scalar_one()
            assert policy == {**previous, 'photo_transcription': {'model': None, 'thinking': 'off'}}
        column = next(
            c for c in sa.inspect(engine).get_columns('assignment') if c['name'] == 'photo_transcription_enabled'
        )
        assert not column['nullable']
        assert column['default'] in ('false', '0', "'0'")
        engine.dispose()
