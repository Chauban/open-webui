"""Mixed documents must retain their evidence through import, teaching and submission."""

import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from docx import Document
from lxml import etree
from open_webui.models.education import Education, Submission
from open_webui.models.writing_materials import WritingMaterial
from open_webui.services.education import draft_import, materials, teaching_runtime
from open_webui.services.education.ai_steps import StepModel
from open_webui.test.apps.webui.routers.test_education_smoke import UserContext
from open_webui.test.apps.webui.routers.test_education_smoke import education_client as base_education_client
from open_webui.test.apps.webui.routers.test_revision_coaching import DRAFT, model_stub, setup, submit
from PIL import Image

education_client = base_education_client


def picture():
    buffer = io.BytesIO()
    Image.new('RGB', (400, 300), 'white').save(buffer, 'PNG')
    return buffer.getvalue()


def word_document():
    doc = Document()
    doc.add_paragraph(DRAFT)
    doc.add_paragraph('证据')
    doc.add_picture(io.BytesIO(picture()))
    doc.sections[0].footer.paragraphs[0].text = '页脚来源：地方志卷五'
    stream = io.BytesIO()
    doc.save(stream)
    with zipfile.ZipFile(stream) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    root = etree.fromstring(entries['word/document.xml'])
    ns = materials.W
    first = root.find(f'.//{{{ns}}}p')
    for kind, identifier in [('footnote', '1'), ('endnote', '2')]:
        run = etree.SubElement(first, f'{{{ns}}}r')
        etree.SubElement(run, f'{{{ns}}}{kind}Reference', {f'{{{ns}}}id': identifier})
        entries[f'word/{kind}s.xml'] = (
            f'<w:{kind}s xmlns:w="{ns}"><w:{kind} w:id="{identifier}"><w:p><w:r><w:t>'
            f'{kind}出处：《史料集》卷三，第42页。</w:t></w:r></w:p></w:{kind}></w:{kind}s>'
        ).encode()
    textbox = etree.SubElement(first, f'{{{ns}}}txbxContent')
    etree.SubElement(
        etree.SubElement(etree.SubElement(textbox, f'{{{ns}}}p'), f'{{{ns}}}r'), f'{{{ns}}}t'
    ).text = '文本框出处：某研究，2024。'
    entries['word/document.xml'] = etree.tostring(root)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as result:
        for name, data in entries.items():
            result.writestr(name, data)
    return output.getvalue()


def pdf_document(*, scan=False):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    if not scan:
        pdf.set_font('Helvetica', size=12)
        pdf.text(15, 20, 'A substantial argument with evidence and more than ten characters.')
        pdf.text(15, 270, 'Footnote: Source volume III, page 42.')
        pdf.link(15, 270, 80, 10, 'https://example.org/source')
    pdf.image(io.BytesIO(picture()), x=20, y=40, w=100)
    return bytes(pdf.output())


@pytest.fixture
def storage(monkeypatch, tmp_path):
    class IsolatedStorage:
        @staticmethod
        def upload_file(stream, name, tags):
            data = stream.read()
            path = tmp_path / name
            path.write_bytes(data)
            return data, str(path)

        @staticmethod
        def get_file(path):
            assert Path(path).parent == tmp_path
            return path

        @staticmethod
        def delete_file(path):
            Path(path).unlink(missing_ok=True)

    monkeypatch.setattr(materials, 'Storage', IsolatedStorage)
    return tmp_path


@pytest.fixture
def vision(monkeypatch):
    calls = []

    async def resolve(*args):
        return StepModel(model_id='evidence-vision', fixed=True)

    async def generate(request, user, model, messages):
        calls.append(messages)
        return '截图出处：《史料集》卷三，第42页。图示：横轴为年份，纵轴为数量。'

    monkeypatch.setattr(draft_import, 'resolve_draft_image_model', resolve)
    monkeypatch.setattr(draft_import, 'generate_transcription', generate)
    return calls


def test_word_preserves_notes_textboxes_and_embedded_images():
    result = materials.parse_document('初稿.docx', word_document())
    assert '【脚注 1】' in result.text and '【尾注 2】' in result.text
    assert DRAFT in result.text
    assert len(result.images) == 1
    by_kind = {block.kind: block for block in result.blocks}
    assert '第42页' in by_kind['footnote'].text
    assert '第42页' in by_kind['endnote'].text
    assert '2024' in by_kind['textbox'].text
    assert '地方志' in by_kind['footer'].text
    assert '史料集' not in result.text  # Evidence never becomes student prose.


def test_pdf_text_does_not_suppress_visual_reading_or_footnotes():
    result = materials.parse_document('混排.pdf', pdf_document())
    assert 'substantial argument' in result.text
    assert 'volume III, page 42' in result.text
    assert len(result.images) == 1
    assert any('https://example.org/source' in block.text for block in result.blocks)
    assert next(block for block in result.blocks if block.kind == 'page').location == '第 1 页'


def test_word_external_images_and_unsupported_objects_are_explicit():
    original = word_document()
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    root = etree.fromstring(entries['word/document.xml'])
    node = root.find(f'.//{{{materials.W}}}p')
    etree.SubElement(node, '{http://schemas.openxmlformats.org/drawingml/2006/chart}chart')
    entries['word/document.xml'] = etree.tostring(root)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as target:
        for name, data in entries.items():
            target.writestr(name, data)
    result = materials.parse_document('objects.docx', output.getvalue())
    assert any(block.status == 'unreadable' and block.kind == 'unsupported' for block in result.blocks)


@pytest.mark.parametrize('mode', ['revise_argument', 'revise_draft'])
@pytest.mark.parametrize('format', ['docx', 'pdf'])
def test_materials_reach_first_read_review_chat_and_frozen_submission(
    education_client, monkeypatch, storage, vision, mode, format
):
    client, teacher, other_teacher, student, other_student, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, mode)
    assert client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline').status_code == 200
    data = word_document() if format == 'docx' else pdf_document()
    response = client.post(f'/api/v1/writing-sessions/{sid}/import/document', files={'file': (f'draft.{format}', data)})
    assert response.status_code == 200, response.text
    imported = response.json()
    material = imported['material']
    image_block = next(block for block in material['blocks'] if block['image'])
    assert image_block['status'] == 'read'
    assert vision and '页码' in vision[0][0]['content']
    assert client.get(f'/api/v1/writing-sessions/{sid}/materials').json() == []
    confirmed = client.post(
        f'/api/v1/writing-sessions/{sid}/draft-baseline',
        json={
            'text': DRAFT,
            'materials': [
                {'id': material['id'], 'corrections': {image_block['id']: '学生核对出处：《史料集》卷三，第43页。'}}
            ],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    calls = model_stub(monkeypatch, text='已读到你的证据来源。' if mode == 'revise_argument' else None)
    for purpose in ('first_read', 'revision_review'):
        if purpose == 'revision_review':
            assert (
                client.post(
                    f'/api/v1/writing-sessions/{sid}/autosave', json={'content_text': DRAFT + '最新修改。'}
                ).status_code
                == 200
            )
        reading = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': purpose})
        assert reading.status_code == 200, reading.text
        assert reading.json()['status'] == 'ready', reading.text
        payload = json.dumps(calls[-1], ensure_ascii=False)
        assert '第43页' in payload
        assert '未读取、未提供、未核实' in payload
        assert reading.json()['context']['materials'][0]['id'] == material['id']
    with factory() as db:
        snapshot = materials.snapshot_materials(sid, db)
        messages = teaching_runtime.build_messages(
            {'ai': {'prompt': '辅导'}, 'title': '论证', 'description': ''},
            'coaching_chat',
            '最新修改后的正文',
            [{'role': 'user', 'content': '这次呢？'}],
            snapshot,
        )
        assert '第43页' in messages[-1]['content']
        assert '最新修改后的正文' in messages[-1]['content']
    submitted = submit(client, assignment, sid)
    assert submitted.status_code == 200, submitted.text
    submission_id = submitted.json()['submission_id']
    with factory() as db:
        frozen = db.get(Submission, submission_id).stats_json['materials']
        frozen_block = next(block for block in frozen[0]['blocks'] if block['id'] == image_block['id'])
        assert frozen_block['text'] == '学生核对出处：《史料集》卷三，第43页。'
        assert '第42页' in frozen_block['extracted_text']
        assert frozen_block['status'] == 'corrected'
        row = db.get(WritingMaterial, material['id'])
        row.active = False  # Later live state must not change the frozen submission.
        db.commit()
    asset_url = f'/api/v1/writing-materials/{material["id"]}/assets/original'
    assert client.get(asset_url).content == data
    UserContext.current_user = other_student
    assert client.get(asset_url).status_code == 403
    UserContext.current_user = other_teacher
    assert client.get(asset_url, params={'submission_id': submission_id}).status_code == 403
    UserContext.current_user = teacher
    assert client.get(asset_url, params={'submission_id': submission_id}).content == data
    detail = client.get(f'/api/v1/teacher/submissions/{submission_id}')
    assert detail.status_code == 200, detail.text
    assert detail.json()['submission']['stats_json']['materials'] == frozen


def test_missing_vision_is_visible_and_does_not_block_submission(education_client, monkeypatch, storage):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student)
    client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline')

    async def unavailable(*args):
        raise draft_import.DraftImageError(
            'Image import is not set up. Ask your administrator to choose an image parsing model.'
        )

    monkeypatch.setattr(draft_import, 'resolve_draft_image_model', unavailable)
    response = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('mixed.pdf', pdf_document())}
    )
    assert response.status_code == 200, response.text
    material = response.json()['material']
    assert any(block['status'] == 'unreadable' for block in material['blocks'])
    assert (
        client.post(
            f'/api/v1/writing-sessions/{sid}/draft-baseline',
            json={'text': DRAFT, 'materials': [{'id': material['id']}]},
        ).status_code
        == 200
    )
    calls = model_stub(monkeypatch, text='第1页图片尚未读取，不能判断是否缺少出处。')
    assert client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'}).status_code == 200
    assert 'unreadable' in json.dumps(calls)
    assert submit(client, assignment, sid).status_code == 200


def test_unrelated_material_cannot_be_attached(education_client, storage):
    client, teacher, _, student, other_student, factory = education_client
    _, sid, _ = setup(client, teacher, student)
    client.delete(f'/api/v1/writing-sessions/{sid}/draft-baseline')
    response = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('draft.txt', DRAFT.encode())}
    )
    identifier = response.json()['material']['id']
    with factory() as db:
        row = db.get(WritingMaterial, identifier)
        row.writing_session_id = 'different-session'
        # Ownership checked before activation. No commit is needed for this service boundary test.
        from fastapi import HTTPException
        from open_webui.models.writing_materials import MaterialSelection

        with pytest.raises(HTTPException) as error:
            materials.confirm_materials(sid, [MaterialSelection(id=identifier)], db)
        assert error.value.status_code == 404


def test_partial_image_failure_keeps_success_and_reports_missing(monkeypatch, vision):
    parsed = materials.ParsedDocument(text=DRAFT)
    parsed.add('image', '第一张来源', image=picture())
    parsed.add('image', '第二张来源', image=picture())
    count = 0

    async def generate(*args):
        nonlocal count
        count += 1
        if count == 1:
            raise draft_import.TranscriptionCallError(400, False)
        return '第二张可读出处：第42页'

    monkeypatch.setattr(draft_import, 'generate_transcription', generate)
    asyncio.run(materials.read_visuals(parsed, None, None))
    assert parsed.blocks[0].status == 'unreadable'
    assert parsed.blocks[0].detail
    assert parsed.blocks[1].text == '第二张可读出处：第42页'
    assert parsed.blocks[1].status == 'read'


def test_scanned_pdf_populates_body_and_preserves_original_page(education_client, storage, vision):
    client, teacher, _, student, _, _ = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch')
    result = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('scan.pdf', pdf_document(scan=True))}
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert '第42页' in body['text']
    assert body['material']['blocks'][0]['image'] is True
    response = client.post(
        f'/api/v1/writing-sessions/{sid}/materials',
        json={'materials': [{'id': body['material']['id']}], 'replace': True},
    )
    assert response.status_code == 200, response.text


def test_from_scratch_keeps_materials_separate_and_replaces_explicitly(education_client, storage, vision):
    client, teacher, _, student, _, factory = education_client
    _, sid, _ = setup(client, teacher, student, 'from_scratch')
    original = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('original.docx', word_document())}
    ).json()
    assert (
        client.post(
            f'/api/v1/writing-sessions/{sid}/materials', json={'materials': [{'id': original['material']['id']}]}
        ).status_code
        == 200
    )
    from open_webui.services.education.writing_context import build_current_text_context

    with factory() as db:
        session = Education.get_writing_session_by_id(sid, db=db)
        prompt = asyncio.run(build_current_text_context(session, captured_text='改过的正文', db=db))
        assert '第42页' in prompt and '改过的正文' in prompt
    new = client.post(
        f'/api/v1/writing-sessions/{sid}/import/document', files={'file': ('new.txt', DRAFT.encode())}
    ).json()
    assert (
        client.post(
            f'/api/v1/writing-sessions/{sid}/materials',
            json={'materials': [{'id': new['material']['id']}], 'replace': True},
        ).status_code
        == 200
    )
    assert [m['id'] for m in client.get(f'/api/v1/writing-sessions/{sid}/materials').json()] == [new['material']['id']]


@pytest.mark.parametrize('filename,phrase', [('zh_draft.pdf', '社区参与'), ('en_draft.pdf', 'Urban Renewal')])
def test_native_pdf_fixtures_keep_text(filename, phrase):
    directory = Path(__file__).resolve().parents[6] / 'src/lib/utils/fixtures'
    parsed = materials.parse_document(filename, (directory / filename).read_bytes())
    assert phrase in parsed.text
    assert not parsed.images


def test_blank_pdf_pages_are_not_reported_as_missing_evidence():
    directory = Path(__file__).resolve().parents[6] / 'src/lib/utils/fixtures'
    parsed = materials.parse_document('mixed.pdf', (directory / 'mixed.pdf').read_bytes())
    assert [block.location for block in parsed.blocks] == ['第 2 页']
