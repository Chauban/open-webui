"""Real writing HTTP routes reject malformed drafts without losing diagnostic context or leaking text."""

import copy
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.services.education.writing_document import DocumentValidationError, validate_document, walk_document
from open_webui.test.apps.webui.routers.test_revision_coaching import setup
from open_webui.test.apps.webui.routers.test_writing_materials import education_client as base_education_client
from open_webui.test.apps.webui.routers.test_writing_materials import storage as isolated_storage
from open_webui.test.apps.webui.routers.test_writing_materials import word_document

education_client = base_education_client
storage = isolated_storage


def test_supported_link_titles_do_not_allow_executable_or_non_text_attributes():
    import pytest

    for attrs in (
        {'href': 'https://example.org', 'title': {'unexpected': 'object'}},
        {'href': 'javascript:alert(1)', 'title': None},
        {'href': 'https://example.org', 'title': None, 'onclick': 'alert(1)'},
    ):
        with pytest.raises(DocumentValidationError):
            validate_document(
                {
                    'type': 'doc',
                    'content': [
                        {
                            'type': 'paragraph',
                            'content': [{'type': 'text', 'text': 'link', 'marks': [{'type': 'link', 'attrs': attrs}]}],
                        }
                    ],
                }
            )


def test_format_error_has_private_diagnostics_and_correcting_format_recovers(education_client, caplog):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'revise_argument')
    document = {
        'type': 'doc',
        'content': [
            {
                'type': 'paragraph',
                'attrs': {'textAlign': 'start'},
                'content': [{'type': 'text', 'text': 'PRIVATE_DRAFT_DO_NOT_LOG'}],
            }
        ],
    }
    with caplog.at_level(logging.WARNING):
        result = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document})
    assert result.status_code == 400
    assert result.json()['detail'] == 'Invalid paragraph alignment'
    request_id = result.headers['x-request-id']
    assert request_id in caplog.text
    assert result.headers['x-writing-error-field'] == 'content_json.content.0.attrs.textAlign'
    assert 'PRIVATE_DRAFT_DO_NOT_LOG' not in caplog.text
    assert sid not in '\n'.join(r.message for r in caplog.records if r.name.endswith('save_diagnostics'))
    document['content'][0]['attrs']['textAlign'] = 'left'
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document}).status_code == 200


def test_request_validation_records_only_field_names_not_input(education_client, caplog):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'revise_argument')
    with caplog.at_level(logging.WARNING):
        result = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': 'SECRET_BAD_INPUT'})
    assert result.status_code == 422
    assert result.headers['x-request-id'] in caplog.text
    assert result.headers['x-writing-error-field'] == 'body.content_json'
    assert 'SECRET_BAD_INPUT' not in result.text + caplog.text


def test_unexpected_save_error_has_reference_without_exception_values(education_client, monkeypatch, caplog):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'revise_argument')

    def fail(*_args):
        raise RuntimeError('PRIVATE_DATABASE_OR_DRAFT_VALUE')

    monkeypatch.setattr('open_webui.routers.education.save_writing_document', fail)
    with caplog.at_level(logging.ERROR):
        result = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': 'synthetic draft'})
    assert result.status_code == 500
    assert result.headers['x-request-id'] in caplog.text
    assert 'PRIVATE_DATABASE_OR_DRAFT_VALUE' not in result.text + caplog.text


def test_real_editor_documents_save_and_round_trip_through_http(education_client, storage):
    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, 'revise_argument')
    imported = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('sample.docx', word_document())}
    )
    assert imported.status_code == 200
    source_nodes = list(walk_document(imported.json()['content_json']))
    fixture = Path(__file__).resolve().parents[6] / 'src/lib/utils/fixtures/writing-save-contract.json'
    for case in json.loads(fixture.read_text(encoding='utf-8')):
        document = copy.deepcopy(case['document'])
        for node in walk_document(document):
            if node['type'] in {'writingImage', 'writingNote'}:
                source = next(n for n in source_nodes if n['type'] == node['type'])
                node['attrs']['materialId'] = source['attrs']['materialId']
                node['attrs']['blockId'] = source['attrs']['blockId']
        response = client.post(
            f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document, 'content_text': case['text']}
        )
        assert response.status_code == 200, (case['name'], response.text)
        workspace = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
        assert workspace['note']['data']['content']['json'] == document
        assert workspace['note']['data']['content']['md'] == case['text']
