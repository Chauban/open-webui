"""The document must remain the same through import, confirmation, reading and export."""

import copy
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from docx import Document
from open_webui.services.education import materials
from open_webui.services.education.writing_document import (
    document_text,
    export_docx,
    text_document,
    validate_document,
    walk_document,
)
from open_webui.test.apps.webui.routers.test_education_smoke import UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import DRAFT, setup, submit
from open_webui.test.apps.webui.routers.test_writing_materials import (
    education_client as base_education_client,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    pdf_document,
    picture,
    word_document,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    storage as base_storage,
)
from open_webui.test.apps.webui.routers.test_writing_materials import (
    vision as base_vision,
)

education_client = base_education_client
storage = base_storage
vision = base_vision


def test_word_structure_and_self_contained_export():
    parsed = materials.parse_document('draft.docx', word_document())
    document = validate_document(parsed.document)
    assert DRAFT in document_text(document)
    nodes = list(walk_document(document))
    assert len([n for n in nodes if n['type'] == 'writingImage']) == 1
    assert len([n for n in nodes if n['type'] == 'writingNote']) == 2
    exported = export_docx(document, lambda *_: picture())
    with zipfile.ZipFile(io.BytesIO(exported)) as package:
        assert 'word/footnotes.xml' in package.namelist()
        assert 'word/endnotes.xml' in package.namelist()
        assert len([n for n in package.namelist() if n.startswith('word/media/')]) == 1
        assert '史料集' in package.read('word/footnotes.xml').decode()
    assert DRAFT in '\n'.join(p.text for p in Document(io.BytesIO(exported)).paragraphs)


def test_linked_and_embedded_images_in_one_paragraph_keep_their_positions():
    from lxml import etree

    doc = Document()
    paragraph = doc.add_paragraph(DRAFT)
    paragraph.add_run().add_picture(io.BytesIO(picture()))
    paragraph.add_run().add_picture(io.BytesIO(picture()))
    stream = io.BytesIO()
    doc.save(stream)
    with zipfile.ZipFile(stream) as original:
        entries = {name: original.read(name) for name in original.namelist()}
    root = etree.fromstring(entries['word/document.xml'])
    blip = next(node for node in root.iter() if etree.QName(node).localname == 'blip')
    blip.set(f'{{{materials.R}}}embed', 'external')
    entries['word/document.xml'] = etree.tostring(root)
    rels = etree.fromstring(entries['word/_rels/document.xml.rels'])
    etree.SubElement(
        rels,
        '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
        {
            'Id': 'external',
            'TargetMode': 'External',
            'Target': 'https://example.org/not-fetched.png',
            'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',
        },
    )
    entries['word/_rels/document.xml.rels'] = etree.tostring(rels)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as package:
        for name, data in entries.items():
            package.writestr(name, data)
    parsed = materials.parse_document('mixed-links.docx', output.getvalue())
    assert [node['type'] for node in parsed.document['content'][:3]] == [
        'paragraph',
        'writingPlaceholder',
        'writingImage',
    ]
    assert len(parsed.images) == 1


@pytest.mark.parametrize('scan', [False, True])
def test_pdf_preserves_images_without_ocr(scan):
    parsed = materials.parse_document('draft.pdf', pdf_document(scan=scan))
    assert any(n['type'] == 'writingImage' for n in walk_document(parsed.document))
    assert bool(document_text(parsed.document)) is not scan


def test_formatting_lists_and_table_import():
    doc = Document()
    doc.add_heading('标题', 1)
    p = doc.add_paragraph()
    p.add_run('加粗').bold = True
    p.add_run('斜体').italic = True
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = '甲'
    table.cell(0, 1).text = '乙'
    table.cell(1, 0).merge(table.cell(1, 1)).text = '合并单元格'
    buffer = io.BytesIO()
    doc.save(buffer)
    parsed = materials.parse_document('format.docx', buffer.getvalue())
    validate_document(parsed.document)
    nodes = list(walk_document(parsed.document))
    assert nodes[1]['type'] == 'heading'
    assert any({'type': 'bold'} in n.get('marks', []) for n in nodes)
    assert any(n.get('attrs', {}).get('colspan') == 2 for n in nodes)
    exported = Document(io.BytesIO(export_docx(parsed.document, lambda *_: picture())))
    assert exported.tables[0].cell(1, 0).text == '合并单元格'


@pytest.mark.parametrize(
    'node',
    [
        {'type': 'image', 'attrs': {'src': 'https://example.org/private'}},
        {'type': 'writingImage', 'attrs': {'materialId': '../bad', 'blockId': 'm1'}},
        {'type': 'writingImage', 'attrs': {'materialId': 'm', 'blockId': 'b', 'width': -1}},
        {
            'type': 'paragraph',
            'content': [
                {'type': 'text', 'text': 'x', 'marks': [{'type': 'link', 'attrs': {'href': 'javascript:alert(1)'}}]}
            ],
        },
    ],
)
def test_rejects_unsafe_document_nodes(node):
    with pytest.raises(ValueError):
        validate_document({'type': 'doc', 'content': [node]})


def test_image_and_note_metadata_do_not_inflate_prose():
    doc = {
        'type': 'doc',
        'content': [
            {'type': 'writingImage', 'attrs': {'materialId': 'm', 'blockId': 'b', 'transcription': '字' * 300}}
        ],
    }
    assert document_text(validate_document(doc)) == ''


def test_pending_draft_confirmation_export_and_deleted_image_context(education_client, storage):
    client, teacher, other_teacher, student, other_student, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, 'revise_argument')
    assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('draft.docx', word_document())}
    )
    assert result.status_code == 200, result.text
    imported = result.json()
    document = imported['content_json']
    pending = {'content_json': document, 'materials': [{'id': imported['material']['id']}], 'expected_revision': 0}
    response = client.put(f'/api/v1/writing-sessions/{sid}/pending-draft', json=pending)
    assert response.status_code == 200, response.text
    assert client.put(f'/api/v1/writing-sessions/{sid}/pending-draft', json=pending).status_code == 409
    stale = client.post(
        f'/api/v1/writing-sessions/{sid}/draft-baseline',
        json={
            'content_json': document,
            'materials': pending['materials'],
            'expected_draft_revision': 0,
        },
    )
    assert stale.status_code == 409
    assert client.get(f'/api/v1/writing-sessions/{sid}/pending-draft').json()['content_json'] == document
    assert client.get(f'/api/v1/writing-sessions/{sid}/materials').json() == []
    exported = client.post(
        f'/api/v1/writing-sessions/{sid}/export/word', json={'content_json': document, 'pending': True}
    )
    assert exported.status_code == 200, exported.text[:200] if exported.status_code != 200 else ''
    assert zipfile.is_zipfile(io.BytesIO(exported.content))
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/draft-baseline',
        json={'content_json': document, 'materials': pending['materials'], 'expected_draft_revision': 1},
    )
    assert result.status_code == 200, result.text
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document}).status_code == 200
    with factory() as db:
        assert materials.model_materials(sid, True, db)
    # Removing all non-prose nodes cannot keep sending the old pictures as attachments.
    deleted = text_document(DRAFT)
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': deleted}).status_code == 200
    with factory() as db:
        assert materials.model_materials(sid, True, db) == []
    assert (
        client.post(f'/api/v1/writing-sessions/{sid}/export/word', json={'content_json': document}).status_code == 409
    )
    UserContext.current_user = teacher
    assert client.post(f'/api/v1/writing-sessions/{sid}/export/word', json={'content_json': deleted}).status_code == 403


def test_photos_import_even_when_vision_is_disabled(education_client, storage, monkeypatch):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'revise_argument')

    async def forbidden(*args):
        raise AssertionError('A disabled assignment must not resolve a vision model')

    monkeypatch.setattr(materials.draft_import, 'resolve_draft_image_model', forbidden)
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/images',
        data={'purpose': 'reference'},
        files=[('files', ('photo.png', picture(), 'image/png'))],
    )
    assert result.status_code == 200, result.text
    assert result.json()['content_json']['content'][0]['type'] == 'writingImage'
    assert result.json()['text'] == ''
    original = result.json()['materials'][0]
    response = client.get(f'/api/v1/writing-materials/{original["id"]}/assets/original')
    assert response.status_code == 200 and response.content == picture()


def test_submission_word_uses_frozen_document_and_checks_each_reader(education_client, storage):
    client, teacher, other_teacher, student, other_student, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch')
    imported = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('draft.docx', word_document())}
    ).json()
    document = imported['content_json']
    result = submit(client, assignment, sid, final_content_json=document, final_content_text=document_text(document))
    assert result.status_code == 200, result.text
    submission_id = result.json()['submission_id']
    viewed_version = result.json()['final_version_id']
    assert (
        client.post(
            f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': text_document('提交后改掉全部正文')}
        ).status_code
        == 200
    )
    url = f'/api/v1/submissions/{submission_id}/export/word'
    first = client.get(url)
    assert first.status_code == 200, first.text[:200] if first.status_code != 200 else ''
    word = Document(io.BytesIO(first.content))
    assert DRAFT in '\n'.join(p.text for p in word.paragraphs)
    assert len(word.inline_shapes) == 1
    for account, expected in [(teacher, 200), (other_teacher, 403), (other_student, 403)]:
        UserContext.current_user = account
        assert client.get(url).status_code == expected
    UserContext.current_user = student
    wrong = copy.deepcopy(document)
    next(n for n in walk_document(wrong) if n['type'] == 'writingImage')['attrs']['materialId'] = 'another-session'
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': wrong}).status_code == 404
    updated = submit(client, assignment, sid, final_content_json=text_document(DRAFT + '更新后的提交。'))
    assert updated.status_code == 200, updated.text
    assert updated.json()['submission_id'] == submission_id
    assert client.get(url, params={'expected_version_id': viewed_version}).status_code == 409
    assert client.get(url, params={'expected_version_id': updated.json()['final_version_id']}).status_code == 200


def test_explicit_recognition_keeps_original_evidence_immutable(education_client, storage, vision, monkeypatch):
    from open_webui.models.writing_materials import WritingMaterial

    client, teacher, _, student, _, factory = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch', image_reading=True)
    imported = client.post(
        f'/api/v1/writing-sessions/{sid}/import/images',
        data={'purpose': 'reference'},
        files={'files': ('p.png', picture())},
    ).json()
    original = imported['materials'][0]
    document = imported['content_json']
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document}).status_code == 200
    with factory() as db:
        before = copy.deepcopy(db.get(WritingMaterial, original['id']).data)

    async def revised(*args, **kwargs):
        return '第二次识别出的内容'

    monkeypatch.setattr(materials.draft_import, 'generate_transcription', revised)
    result = client.post(f'/api/v1/writing-sessions/{sid}/materials/{original["id"]}/read', params={'block_id': 'm1'})
    assert result.status_code == 200, result.text
    assert result.json()['material_id'] != original['id']
    assert result.json()['blocks'][0]['text'] == '第二次识别出的内容'
    with factory() as db:
        assert db.get(WritingMaterial, original['id']).data == before
        assert db.get(WritingMaterial, result.json()['material_id']).active is False

    async def unavailable(*args):
        raise materials.draft_import.DraftImageError(
            'Image import is not set up. Ask your administrator to choose an image parsing model.'
        )

    monkeypatch.setattr(materials.draft_import, 'resolve_draft_image_model', unavailable)
    failed = client.post(f'/api/v1/writing-sessions/{sid}/materials/{original["id"]}/read', params={'block_id': 'm1'})
    assert failed.status_code == 200
    assert failed.json()['blocks'][0]['text'] == ''
    assert failed.json()['blocks'][0]['status'] == 'unreadable'


def test_markdown_preserves_lists_and_reports_unbundled_images():
    parsed = materials.parse_document(
        'draft.md', '# 标题\n\n**重点**\n\n- 第一项\n    - 子项\n\n![来源图](https://example.org/image.png)'.encode()
    )
    validate_document(parsed.document)
    nodes = list(walk_document(parsed.document))
    assert any(n['type'] == 'heading' for n in nodes)
    assert len([n for n in nodes if n['type'] == 'writingPlaceholder']) == 1


def test_image_metadata_cannot_claim_a_nonexistent_native_text_layer(education_client, storage):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch')
    imported = client.post(
        f'/api/v1/writing-sessions/{sid}/import/images',
        data={'purpose': 'reference'},
        files={'files': ('p.png', picture())},
    ).json()
    document = imported['content_json']
    document['content'][0]['attrs']['nativeText'] = '伪造原生文字'
    result = client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document})
    assert result.status_code == 400


def test_unpreviewable_embedded_image_keeps_original_and_does_not_block_prose(education_client, storage, monkeypatch):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch')

    def unsupported(_data):
        raise materials.draft_import.DraftImageError('Could not read this image')

    monkeypatch.setattr(materials, 'prepare_material_image', unsupported)
    source = Document()
    source.add_paragraph(DRAFT)
    source.add_picture(io.BytesIO(picture()))
    source.add_paragraph('这条图注不能丢失', style='Caption')
    data = io.BytesIO()
    source.save(data)
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('original.docx', data.getvalue())}
    )
    assert result.status_code == 200, result.text
    document = result.json()['content_json']
    assert any(node['type'] == 'writingPlaceholder' for node in walk_document(document))
    assert document_text(document).endswith('这条图注不能丢失')
    assert client.post(f'/api/v1/writing-sessions/{sid}/autosave', json={'content_json': document}).status_code == 200


def test_pdf_visual_lines_become_a_continuous_paragraph():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    prose = (
        'Evidence supports a claim when the writer explains the relationship '
        + 'between the observation and the conclusion. '
    ) * 6
    pdf.multi_cell(180, 6, prose)
    parsed = materials.parse_document('lines.pdf', bytes(pdf.output()))
    paragraphs = [node for node in parsed.document['content'] if node['type'] == 'paragraph']
    assert len(paragraphs) <= 2
    assert document_text(parsed.document).replace('\n', ' ').split() == prose.split()


def test_pdf_columns_keep_reading_order():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    for index in range(4):
        pdf.text(15, 25 + index * 7, f'Left column line {index + 1}.')
        pdf.text(115, 25 + index * 7, f'Right column line {index + 1}.')
    parsed = materials.parse_document('columns.pdf', bytes(pdf.output()))
    text = document_text(parsed.document)
    assert text.index('Left column line 4.') < text.index('Right column line 1.')


def test_searchable_scan_is_not_duplicated_as_image_and_body():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.image(io.BytesIO(picture()), x=0, y=0, w=210, h=297)
    pdf.set_font('Helvetica', size=12)
    pdf.text(15, 20, 'This is the existing searchable text layer.')
    parsed = materials.parse_document('searchable-scan.pdf', bytes(pdf.output()))
    assert document_text(parsed.document) == ''
    assert len(parsed.document['content']) == 1
    assert 'searchable text layer' in parsed.document['content'][0]['attrs']['nativeText']


def test_word_export_fits_tall_images_to_paper():
    from docx.shared import Inches
    from PIL import Image

    image = io.BytesIO()
    Image.new('RGB', (100, 2000), 'white').save(image, 'PNG')
    doc = {
        'type': 'doc',
        'content': [{'type': 'writingImage', 'attrs': {'materialId': 'm', 'blockId': 'b', 'width': 100}}],
    }
    word = Document(io.BytesIO(export_docx(doc, lambda *_: image.getvalue())))
    assert word.inline_shapes[0].height <= Inches(9) + 2


def test_word_lists_preserve_style_start_and_nesting():
    word = Document()
    word.add_paragraph('要点甲', style='List Bullet')
    word.add_paragraph('要点乙', style='List Bullet')
    buffer = io.BytesIO()
    word.save(buffer)
    imported = materials.parse_document('bullets.docx', buffer.getvalue())
    assert imported.document['content'][0]['type'] == 'bulletList'
    assert len(imported.document['content'][0]['content']) == 2
    document = {
        'type': 'doc',
        'content': [
            {
                'type': 'orderedList',
                'attrs': {'start': 3},
                'content': [
                    {
                        'type': 'listItem',
                        'content': [
                            text_document('第三项')['content'][0],
                            {
                                'type': 'bulletList',
                                'content': [{'type': 'listItem', 'content': text_document('子项')['content']}],
                            },
                        ],
                    },
                    {'type': 'listItem', 'content': text_document('第四项')['content']},
                ],
            }
        ],
    }
    exported = export_docx(document, lambda *_: b'')
    parsed = materials.parse_document('lists.docx', exported)
    listing = parsed.document['content'][0]
    assert listing['attrs']['start'] == 3
    assert listing['content'][0]['content'][1]['type'] == 'bulletList'


@pytest.mark.parametrize(
    'node',
    [
        {'type': []},
        {'type': 'paragraph', 'attrs': {'textAlign': {}}},
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'x', 'marks': [{'type': []}]}]},
        {
            'type': 'paragraph',
            'content': [{'type': 'text', 'text': 'x', 'marks': [{'type': 'highlight', 'attrs': {'color': 12}}]}],
        },
    ],
)
def test_malformed_document_fields_are_validation_errors(node):
    with pytest.raises(ValueError):
        validate_document({'type': 'doc', 'content': [node]})


def test_photo_recognition_is_bounded_parallel_and_keeps_file_order(education_client, storage, vision, monkeypatch):
    import asyncio

    client, teacher, _, student, _, _ = education_client
    assignment, sid, _ = setup(client, teacher, student, 'from_scratch', image_reading=True)
    from open_webui.test.apps.webui.routers.test_photo_transcription import set_photo

    set_photo(client, teacher, student, assignment, True)
    active = 0
    peak = 0

    async def read(*args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.03)
        active -= 1
        return '图片里的文字'

    monkeypatch.setattr(materials.draft_import, 'generate_transcription', read)
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/images',
        data={'purpose': 'photo_to_text'},
        files=[('files', (f'{i}.png', picture())) for i in range(8)],
    )
    assert result.status_code == 200, result.text
    assert 2 <= peak <= 8
    assert [m['filename'] for m in result.json()['materials']] == [f'{i}.png' for i in range(8)]
