"""Teachers control recognition; OCR text is never independently verified evidence."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.models.education import Submission
from open_webui.services.education import draft_import, materials
from open_webui.test.apps.webui.routers.test_education_smoke import UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import DRAFT, model_stub, setup, submit
from open_webui.test.apps.webui.routers.test_writing_materials import (
    education_client as base_client,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    pdf_document,
    imported_document,
    picture,
    word_document,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    storage as isolated_storage,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    vision as mock_vision,
)

education_client = base_client
storage = isolated_storage
vision = mock_vision


def switch(client, teacher, student, assignment, enabled):
    UserContext.current_user = teacher
    current = client.get(f'/api/v1/teacher/assignments/{assignment["id"]}').json()['assignment']
    result = client.patch(
        f'/api/v1/assignments/{assignment["id"]}',
        json={
            'expected_config_revision': current['config_revision'],
            'image_reading_enabled': enabled,
        },
    )
    UserContext.current_user = student
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
@pytest.mark.parametrize('extension', ['docx', 'pdf'])
def test_default_off_keeps_originals_and_never_resolves_a_vision_model(
    education_client, storage, monkeypatch, mode, extension
):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    assert assignment['image_reading_enabled'] is False
    if mode != 'from_scratch':
        assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200

    async def unexpected(*args):
        pytest.fail('Disabled assignments must not resolve or call an image model')

    monkeypatch.setattr(draft_import, 'resolve_draft_image_model', unexpected)
    data = word_document() if extension == 'docx' else pdf_document()
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': (f'draft.{extension}', data)}
    )
    assert result.status_code == 200, result.text
    material = result.json()['material']
    visual = next(block for block in material['blocks'] if block['kind'] in materials.VISUAL_KINDS)
    assert visual['status'] == 'disabled'
    assert visual['text'] == visual['extracted_text'] == ''
    assert visual['image'] is True
    assert client.get(f'/api/v1/writing-materials/{material["id"]}/assets/original').content == data
    photo = client.post(
        f'/api/v1/writing-sessions/{sid}/import/images', files={'files': ('photo.png', picture(), 'image/png')}
    )
    assert photo.status_code == 200
    assert photo.json()['text'] == ''
    assert photo.json()['content_json']['content'][0]['type'] == 'writingImage'
    if extension == 'docx':
        assert any('第42页' in block['text'] for block in material['blocks'] if block['kind'] == 'footnote')


@pytest.mark.parametrize('mode', ['from_scratch', 'revise_draft', 'revise_argument'])
def test_only_assignment_teacher_can_toggle_and_snapshot_setting_is_immutable(education_client, mode):
    client, teacher, other_teacher, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    url = f'/api/v1/assignments/{assignment["id"]}'
    payload = {'expected_config_revision': assignment['config_revision'], 'image_reading_enabled': True}
    assert client.patch(url, json=payload).status_code == 403
    UserContext.current_user = other_teacher
    assert client.patch(url, json=payload).status_code == 403
    enabled = switch(client, teacher, student, assignment, True)
    assert enabled['image_reading_enabled'] is True
    UserContext.current_user = teacher
    assert client.patch(url, json=payload).status_code == 409
    assert (
        client.patch(
            url,
            json={**payload, 'expected_config_revision': enabled['config_revision'], 'image_reading_enabled': 'true'},
        ).status_code
        == 422
    )
    UserContext.current_user = student
    submitted = submit(client, assignment, sid)
    assert submitted.status_code == 200, submitted.text
    disabled = switch(client, teacher, student, assignment, False)
    assert disabled['image_reading_enabled'] is False
    with factory() as db:
        assert (
            db.get(Submission, submitted.json()['submission_id']).stats_json['assignment_config'][
                'image_reading_enabled'
            ]
            is True
        )


@pytest.mark.parametrize('mode', ['revise_draft', 'revise_argument'])
def test_turning_off_excludes_prior_transcription_without_rewriting_evidence(
    education_client, storage, vision, monkeypatch, mode
):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode, image_reading=True)
    assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200
    imported = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('draft.docx', word_document())}
    ).json()
    mid = imported['material']['id']
    visual = next(block for block in imported['material']['blocks'] if block['kind'] == 'image')
    assert (
        client.post(
            f'/api/v1/writing-sessions/{sid}/draft-baseline',
            json={
                'text': DRAFT,
                'content_json': imported_document(imported, {visual['id']: 'OCR_UNVERIFIED_错字'}),
                'materials': [{'id': mid, 'corrections': {visual['id']: 'OCR_UNVERIFIED_错字'}}],
            },
        ).status_code
        == 200
    )
    calls = model_stub(monkeypatch, text='请对照原图核对。' if mode == 'revise_argument' else None)
    endpoint = f'/api/v1/writing-sessions/{sid}/readings'
    first = client.post(endpoint, json={'purpose': 'first_read'})
    assert first.status_code == 200, first.text
    original = copy.deepcopy(first.json())
    first_system = calls[-1][0]['content']
    assert original['context']['image_reading_enabled'] is True
    assert 'OCR_UNVERIFIED_错字' in json.dumps(calls[-1], ensure_ascii=False)
    assert '未独立核验' in json.dumps(calls[-1], ensure_ascii=False)
    switch(client, teacher, student, assignment, False)
    second = client.post(endpoint, json={'purpose': 'first_read'})
    assert second.status_code == 200, second.text
    assert second.json()['id'] != original['id']
    assert second.json()['context']['image_reading_enabled'] is False
    assert 'OCR_UNVERIFIED_错字' not in json.dumps(calls[-1], ensure_ascii=False)
    assert calls[-1][0]['content'] == first_system
    preserved = client.get(f'/api/v1/writing-sessions/{sid}/materials').json()[0]['blocks']
    assert next(b for b in preserved if b['id'] == visual['id'])['text'] == 'OCR_UNVERIFIED_错字'

    old = next(item for item in client.get(endpoint).json() if item['id'] == original['id'])
    assert old['context']['image_reading_enabled'] is True
    assert old['context']['materials'] == original['context']['materials']


def test_switch_off_during_recognition_discards_result_before_returning(education_client, storage, vision, monkeypatch):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch', image_reading=True)

    async def in_flight(*args):
        switch(client, teacher, student, assignment, False)
        return 'OCR_SHOULD_NOT_ENTER_DRAFT'

    monkeypatch.setattr(draft_import, 'generate_transcription', in_flight)
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('scan.pdf', pdf_document(scan=True))}
    )
    assert result.status_code == 200, result.text
    assert 'OCR_SHOULD_NOT_ENTER_DRAFT' not in result.text
    assert result.json()['material']['blocks'][0]['status'] == 'disabled'


def test_image_blocks_are_removed_from_provider_input_but_saved_messages_are_untouched():
    original = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': '解释正文'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,secret'}},
            ],
            'files': [{'type': 'image', 'url': 'secret'}, {'type': 'file', 'id': 'text-source'}],
        }
    ]
    before = copy.deepcopy(original)
    result = materials.apply_image_reading_policy(original, False)
    assert 'secret' not in json.dumps(result)
    assert result[0]['files'] == [{'type': 'file', 'id': 'text-source'}]
    assert original == before
    assert materials.apply_image_reading_policy(original, True) == original


def test_builtin_defaults_have_no_appended_image_coaching_rules():
    from open_webui.services.education.teaching_defaults import DEFAULT_TEACHING_CONFIGS

    for defaults in DEFAULT_TEACHING_CONFIGS.values():
        assert '图片证据的判断边界' not in defaults['prompt']
        assert '确认导入或确认初稿不等于' not in defaults['prompt']
    assert not hasattr(materials, 'MATERIAL_RULES')
    assert not hasattr(materials, 'material_rules')
