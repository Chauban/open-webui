"""One validated document for editing, evidence, plain-text projection and DOCX export."""

import copy
import io
import re
from urllib.parse import urlsplit

from fastapi import HTTPException

MAX_TEXT = 200_000
BLOCKS = {
    'paragraph',
    'heading',
    'blockquote',
    'bulletList',
    'orderedList',
    'taskList',
    'codeBlock',
    'table',
    'horizontalRule',
    'writingImage',
    'writingPlaceholder',
}
INLINE = {'text', 'hardBreak', 'writingNote'}
CONTAINERS = {'doc', 'listItem', 'taskItem', 'tableRow', 'tableCell', 'tableHeader'}
MARKS = {'bold', 'italic', 'underline', 'strike', 'code', 'link', 'highlight', 'superscript', 'subscript'}
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def text_document(text):
    return {
        'type': 'doc',
        'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': line}] if line else []}
            for line in text.split('\n')
        ]
        or [{'type': 'paragraph'}],
    }


def walk_document(node):
    yield node
    for child in node.get('content', []):
        yield from walk_document(child)


def safe_link(value):
    try:
        return (
            isinstance(value, str)
            and len(value) <= 4096
            and urlsplit(value).scheme.lower() in {'http', 'https', 'mailto'}
        )
    except ValueError:
        return False


def validate_document(document):  # noqa: C901
    """Reject unknown nodes, unbounded structures and executable/resource URL attributes."""
    count = 0
    characters = 0

    def visit(node, depth=0):  # noqa: C901
        nonlocal count, characters
        count += 1
        if depth > 48 or count > 30_000 or not isinstance(node, dict):
            raise ValueError('The document is too complex')
        if node.keys() - {'type', 'attrs', 'content', 'text', 'marks'}:
            raise ValueError('Unsupported document properties')
        kind = node.get('type')
        if not isinstance(kind, str) or kind not in BLOCKS | INLINE | CONTAINERS:
            raise ValueError('Unsupported document node')
        attrs = node.get('attrs') or {}
        if not isinstance(attrs, dict):
            raise ValueError('Invalid document attributes')
        allowed = {
            'paragraph': {'textAlign'},
            'heading': {'level', 'textAlign'},
            'orderedList': {'start', 'type'},
            'taskItem': {'checked'},
            'codeBlock': {'language'},
            'tableCell': {'colspan', 'rowspan', 'colwidth', 'align'},
            'tableHeader': {'colspan', 'rowspan', 'colwidth', 'align'},
            'writingImage': {
                'materialId',
                'blockId',
                'width',
                'alt',
                'transcription',
                'transcriptionEdited',
                'nativeText',
                'nativeTextEdited',
                'readStatus',
                'readDetail',
            },
            'writingNote': {'materialId', 'blockId', 'label', 'note', 'kind'},
            'writingPlaceholder': {'materialId', 'blockId', 'label'},
        }.get(kind, set())
        if attrs.keys() - allowed:
            raise ValueError('Unsupported document attributes')
        if kind == 'taskItem' and type(attrs.get('checked', False)) is not bool:
            raise ValueError('Invalid document attribute type')
        for key in ('alt', 'readDetail', 'label', 'note', 'language'):
            if attrs.get(key) is not None and not isinstance(attrs[key], str):
                raise ValueError('Invalid document attribute type')
        for key, value in attrs.items():
            if isinstance(value, str):
                characters += len(value)
        if kind.startswith('writing'):
            if not all(
                isinstance(attrs.get(key), str) and ID.fullmatch(attrs[key]) for key in ('materialId', 'blockId')
            ):
                raise ValueError('Invalid material reference')
        if kind == 'writingImage':
            width = attrs.get('width', 100)
            if type(width) is not int or not 20 <= width <= 100:
                raise ValueError('Invalid image width')
            if (
                not isinstance(attrs.get('transcription', ''), str)
                or type(attrs.get('transcriptionEdited', False)) is not bool
            ):
                raise ValueError('Invalid image transcription')
            if (
                not isinstance(attrs.get('nativeText', ''), str)
                or type(attrs.get('nativeTextEdited', False)) is not bool
            ):
                raise ValueError('Invalid native text')
            if (
                not isinstance(attrs.get('readStatus', ''), str)
                or attrs.get('readStatus', '') not in {'', 'read', 'unreadable', 'corrected', 'disabled'}
                or not isinstance(attrs.get('readDetail', ''), str)
            ):
                raise ValueError('Invalid reading status')
        if kind == 'writingNote' and (
            not isinstance(attrs.get('kind'), str)
            or attrs.get('kind') not in {'footnote', 'endnote', 'annotation'}
            or not isinstance(attrs.get('note'), str)
        ):
            raise ValueError('Invalid note')
        if attrs.get('textAlign') is not None and (
            not isinstance(attrs['textAlign'], str) or attrs['textAlign'] not in {'left', 'center', 'right', 'justify'}
        ):
            raise ValueError('Invalid paragraph alignment')
        for key, low, high in [('level', 1, 6), ('start', 1, 100000), ('colspan', 1, 30), ('rowspan', 1, 100)]:
            if key in attrs and (type(attrs[key]) is not int or not low <= attrs[key] <= high):
                raise ValueError('Invalid document dimensions')
        if attrs.get('colwidth') is not None and (
            not isinstance(attrs['colwidth'], list)
            or len(attrs['colwidth']) > 30
            or any(type(n) is not int or n < 0 or n > 10000 for n in attrs['colwidth'])
        ):
            raise ValueError('Invalid table column width')
        children = node.get('content', [])
        if not isinstance(children, list):
            raise ValueError('Invalid document content')
        expected = {
            'doc': BLOCKS,
            'paragraph': INLINE,
            'heading': INLINE,
            'codeBlock': {'text'},
            'writingImage': INLINE,
            'blockquote': BLOCKS,
            'listItem': BLOCKS,
            'taskItem': BLOCKS,
            'bulletList': {'listItem'},
            'orderedList': {'listItem'},
            'taskList': {'taskItem'},
            'table': {'tableRow'},
            'tableRow': {'tableCell', 'tableHeader'},
            'tableCell': BLOCKS,
            'tableHeader': BLOCKS,
        }.get(kind, set())
        for child in children:
            if (
                not isinstance(child, dict)
                or not isinstance(child.get('type'), str)
                or child.get('type') not in expected
            ):
                raise ValueError('Invalid document nesting')
            visit(child, depth + 1)
        if kind == 'text':
            if not isinstance(node.get('text'), str) or not node['text']:
                raise ValueError('Invalid text node')
            characters += len(node['text'])
        elif 'text' in node:
            raise ValueError('Text is only allowed on text nodes')
        marks = node.get('marks', [])
        if not isinstance(marks, list) or len(marks) > 12:
            raise ValueError('Invalid document marks')
        for mark in marks:
            if (
                not isinstance(mark, dict)
                or mark.keys() - {'type', 'attrs'}
                or not isinstance(mark.get('type'), str)
                or mark.get('type') not in MARKS
            ):
                raise ValueError('Unsupported text mark')
            ma = mark.get('attrs') or {}
            if not isinstance(ma, dict):
                raise ValueError('Invalid text mark')
            for value in ma.values():
                if value is not None and not isinstance(value, str):
                    raise ValueError('Invalid text mark')
                if isinstance(value, str):
                    characters += len(value)
            if mark['type'] == 'link':
                if ma.keys() - {'href', 'target', 'rel', 'class'} or not safe_link(ma.get('href')):
                    raise ValueError('Invalid link')
            elif mark['type'] == 'highlight':
                if ma.keys() - {'color'} or (
                    ma.get('color') is not None
                    and (not isinstance(ma['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{3,8}', ma['color']))
                ):
                    raise ValueError('Invalid highlight')
            elif ma:
                raise ValueError('Unsupported text mark attributes')
        if characters > MAX_TEXT:
            raise ValueError('The document contains too much text')

    if not isinstance(document, dict) or document.get('type') != 'doc':
        raise ValueError('A writing document is required')
    visit(document)
    return copy.deepcopy(document)


def document_text(document):
    """Visible editable prose only. Asset labels and OCR never inflate character/source counts."""

    def render(node):
        kind = node['type']
        if kind == 'text':
            return node['text']
        if kind == 'hardBreak':
            return '\n'
        if kind in {'writingNote', 'writingPlaceholder'}:
            return ''
        children = [render(child) for child in node.get('content', [])]
        return ('' if kind in {'paragraph', 'heading', 'codeBlock', 'writingImage'} else '\n').join(children)

    return render(document).strip()


def document_refs(document):
    return [node for node in walk_document(document) if node['type'].startswith('writing')]


def document_content(document):
    return {'json': document, 'md': document_text(document), 'html': None}


def check_document_resources(document, session_id, db):
    from open_webui.models.writing_materials import WritingMaterial

    refs = document_refs(document)
    identifiers = {node['attrs']['materialId'] for node in refs}
    rows = db.query(WritingMaterial).filter(WritingMaterial.id.in_(identifiers)).all() if identifiers else []
    if len({row.data.get('origin_id', row.id) for row in rows}) > 20:
        raise HTTPException(400, 'Too many attached documents')
    by_id = {row.id: row for row in rows}
    for node in refs:
        attrs = node['attrs']
        row = by_id.get(attrs['materialId'])
        if row is None or row.writing_session_id != session_id:
            raise HTTPException(404, 'Material not found')
        block = next((b for b in row.data['blocks'] if b['id'] == attrs['blockId']), None)
        if block is None or (node['type'] == 'writingImage' and not block['image']):
            raise HTTPException(400, 'Invalid material reference')
        if node['type'] == 'writingNote' and (
            block['kind'] not in {'footnote', 'endnote', 'annotation'} or attrs['kind'] != block['kind']
        ):
            raise HTTPException(400, 'Invalid note reference')
        if node['type'] == 'writingPlaceholder' and block['kind'] != 'unsupported':
            raise HTTPException(400, 'Invalid document placeholder')
        if node['type'] == 'writingImage' and attrs.get('nativeText') and not block.get('native_text'):
            raise HTTPException(400, 'This image has no native document text layer')
    return by_id


def export_docx(document, load_image):  # noqa: C901
    """Export a self-contained Word file; resource failure fails the whole download."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt
    from lxml import etree

    validate_document(document)
    word = Document()
    word.core_properties.author = ''
    normal = word.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    normal.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), '宋体')
    word.sections[0].page_width = Inches(8.27)
    word.sections[0].page_height = Inches(11.69)
    word.sections[0].left_margin = word.sections[0].right_margin = Inches(0.9)
    note_roots = {}
    note_ids = {}

    def inline(paragraph, nodes):  # noqa: C901 -- Word requires a distinct encoding for each supported mark and note.
        for node in nodes:
            if node['type'] == 'hardBreak':
                paragraph.add_run().add_break()
                continue
            if node['type'] == 'writingNote':
                attrs = node['attrs']
                kind = 'endnote' if attrs['kind'] == 'endnote' else 'footnote'
                if kind not in note_roots:
                    root = etree.Element(
                        qn(f'w:{kind}s'), nsmap={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    )
                    for identifier, note_type in [(-1, 'separator'), (0, 'continuationSeparator')]:
                        special = etree.SubElement(
                            root, qn(f'w:{kind}'), {qn('w:id'): str(identifier), qn('w:type'): note_type}
                        )
                        etree.SubElement(
                            etree.SubElement(etree.SubElement(special, qn('w:p')), qn('w:r')), qn(f'w:{note_type}')
                        )
                    note_roots[kind] = root
                root = note_roots[kind]
                key = (attrs['materialId'], attrs['blockId'], kind, attrs['note'])
                if key not in note_ids:
                    identifier = str(len(root) - 1)
                    note_ids[key] = identifier
                    note = etree.SubElement(root, qn(f'w:{kind}'), {qn('w:id'): identifier})
                    p = etree.SubElement(note, qn('w:p'))
                    etree.SubElement(etree.SubElement(p, qn('w:r')), qn(f'w:{kind}Ref'))
                    etree.SubElement(etree.SubElement(p, qn('w:r')), qn('w:t')).text = attrs['note']
                identifier = note_ids[key]
                etree.SubElement(paragraph.add_run()._r, qn(f'w:{kind}Reference'), {qn('w:id'): identifier})
                continue
            run = paragraph.add_run(node.get('text', ''))
            for mark in node.get('marks', []):
                kind = mark['type']
                if kind in {'bold', 'italic', 'underline'}:
                    setattr(run, kind, True)
                elif kind in {'strike', 'superscript', 'subscript'}:
                    setattr(run.font, kind, True)
                elif kind == 'code':
                    run.font.name = 'Consolas'
                elif kind == 'link':
                    hyperlink = OxmlElement('w:hyperlink')
                    from docx.opc.constants import RELATIONSHIP_TYPE as RT

                    hyperlink.set(
                        qn('r:id'), paragraph.part.relate_to(mark['attrs']['href'], RT.HYPERLINK, is_external=True)
                    )
                    run._r.getparent().remove(run._r)
                    hyperlink.append(run._r)
                    paragraph._p.append(hyperlink)

    def list_numbering(ordered, start, depth):
        numbering = word.part.numbering_part.element
        identifier = (
            max((int(n.get(qn('w:abstractNumId'))) for n in numbering.findall(qn('w:abstractNum'))), default=-1) + 1
        )
        abstract = OxmlElement('w:abstractNum')
        abstract.set(qn('w:abstractNumId'), str(identifier))
        multi = etree.SubElement(abstract, qn('w:multiLevelType'))
        multi.set(qn('w:val'), 'multilevel')
        for level in range(min(depth, 9)):
            element = etree.SubElement(abstract, qn('w:lvl'), {qn('w:ilvl'): str(level)})
            for tag, value in [
                ('start', str(start if level == depth - 1 else 1)),
                ('numFmt', 'decimal' if ordered else 'bullet'),
                ('lvlText', f'%{level + 1}.' if ordered else '•'),
                ('lvlJc', 'left'),
            ]:
                etree.SubElement(element, qn('w:' + tag), {qn('w:val'): value})
            props = etree.SubElement(element, qn('w:pPr'))
            etree.SubElement(props, qn('w:ind'), {qn('w:left'): str((level + 1) * 360), qn('w:hanging'): '180'})
        numbering.append(abstract)
        return numbering.add_num(identifier).numId, min(depth - 1, 8)

    def blocks(container, nodes, list_style=None, list_id=None, depth=0):  # noqa: C901 -- Explicit document-node serialization.
        for node in nodes:
            kind = node['type']
            attrs = node.get('attrs') or {}
            children = node.get('content', [])
            if kind in {'bulletList', 'orderedList', 'taskList'}:
                number = (
                    None
                    if kind == 'taskList'
                    else list_numbering(kind == 'orderedList', attrs.get('start', 1), depth + 1)
                )
                blocks(container, children, 'List Paragraph', number, depth + 1)
            elif kind in {'listItem', 'taskItem', 'blockquote'}:
                if kind == 'taskItem' and children and children[0]['type'] == 'paragraph':
                    first = children[0]
                    children = [
                        {
                            **first,
                            'content': [
                                {'type': 'text', 'text': '☑ ' if attrs.get('checked') is True else '☐ '},
                                *first.get('content', []),
                            ],
                        },
                        *children[1:],
                    ]
                blocks(container, children, list_style or ('Quote' if kind == 'blockquote' else None), list_id, depth)
            elif kind == 'table':
                if not children:
                    continue
                cols = max(
                    sum((cell.get('attrs') or {}).get('colspan', 1) for cell in row.get('content', []))
                    for row in children
                )
                table = container.add_table(rows=len(children), cols=max(1, cols))
                table.style = 'Table Grid'
                occupied = set()
                for y, row in enumerate(children):
                    x = 0
                    for cell in row.get('content', []):
                        while (y, x) in occupied:
                            x += 1
                        ca = cell.get('attrs') or {}
                        w, h = ca.get('colspan', 1), ca.get('rowspan', 1)
                        if x + w > cols or y + h > len(children):
                            raise ValueError('Invalid table dimensions')
                        target = table.cell(y, x)
                        if w > 1 or h > 1:
                            target = target.merge(table.cell(y + h - 1, x + w - 1))
                        occupied.update((yy, xx) for yy in range(y, y + h) for xx in range(x, x + w))
                        blocks(target, cell.get('content', []))
                        if len(target.paragraphs) > 1 and not target.paragraphs[0].text:
                            target._tc.remove(target.paragraphs[0]._p)
                        x += w
            elif kind == 'writingImage':
                picture = load_image(attrs['materialId'], attrs['blockId'])
                from PIL import Image

                with Image.open(io.BytesIO(picture)) as pixels:
                    ratio = pixels.width / pixels.height
                available_width = (
                    min(6.47, container.width / 914400) if hasattr(container, 'width') and container.width else 6.47
                )
                width = min(available_width * attrs.get('width', 100) / 100, 9 * ratio)
                p = container.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = bool(children)
                p.add_run().add_picture(io.BytesIO(picture), width=Inches(width))
                if children:
                    caption = container.add_paragraph(style='Caption')
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    inline(caption, children)
            elif kind == 'horizontalRule':
                container.add_paragraph('────────────────')
            elif kind == 'writingPlaceholder':
                container.add_paragraph(attrs.get('label', '请查看上传原件'))
            else:
                style = f'Heading {attrs.get("level", 1)}' if kind == 'heading' else list_style
                p = container.add_paragraph(style=style)
                if depth:
                    p.paragraph_format.left_indent = Inches(0.25 * depth)
                if list_id is not None:
                    props = p._p.get_or_add_pPr().get_or_add_numPr()
                    props.get_or_add_ilvl().val = list_id[1]
                    props.get_or_add_numId().val = list_id[0]
                    list_id = None
                if attrs.get('textAlign'):
                    p.alignment = {'left': 0, 'center': 1, 'right': 2, 'justify': 3}[attrs['textAlign']]
                inline(p, children)

    blocks(word, document.get('content', []))
    for kind, root in note_roots.items():
        part = Part(
            PackURI(f'/word/{kind}s.xml'),
            f'application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}s+xml',
            etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True),
            word.part.package,
        )
        word.part.relate_to(part, f'http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}s')
    output = io.BytesIO()
    word.save(output)
    return output.getvalue()
