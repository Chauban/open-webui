"""Convert source structure into the editor schema without calling a language model."""

import io
import posixpath
import re
import zipfile
from collections import defaultdict, deque
from contextlib import closing

from lxml import etree

from open_webui.services.education.writing_document import document_text, safe_link

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def image_node(block):
    return {
        'type': 'writingImage' if block.image else 'writingPlaceholder',
        'attrs': {
            'materialId': 'pending',
            'blockId': block.id,
            'width': 100,
            'alt': '稿件图片' if block.location.startswith('正文第 ') else block.location,
            'transcription': '',
            'transcriptionEdited': False,
        }
        if block.image
        else {'materialId': 'pending', 'blockId': block.id, 'label': block.detail or '请查看上传原件'},
    }


def word_layout(data, parsed):  # noqa: C901
    """Reuse the exhaustive asset traversal's identifiers, retaining OOXML text/run structure."""
    lookup = defaultdict(deque)
    for block in parsed.blocks:
        lookup[(block.location, block.kind)].append(block)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:

        def xml(name):
            return etree.fromstring(archive.read(name), etree.XMLParser(resolve_entities=False, no_network=True))

        styles = {}
        if 'word/styles.xml' in archive.namelist():
            styles = {node.get(f'{{{W}}}styleId'): node for node in xml('word/styles.xml')}
        rels = {}
        embedded_images = set()
        if 'word/_rels/document.xml.rels' in archive.namelist():
            relationships = list(xml('word/_rels/document.xml.rels'))
            rels = {node.get('Id'): node.get('Target', '') for node in relationships}
            embedded_images = {
                node.get('Id')
                for node in relationships
                if node.get('TargetMode') != 'External'
                and posixpath.normpath(posixpath.join('word', node.get('Target', ''))).lstrip('/') in archive.namelist()
            }
        numbering = {}
        numbering_starts = {}
        numbering_counts = defaultdict(int)
        if 'word/numbering.xml' in archive.namelist():
            root = xml('word/numbering.xml')
            abstract = {n.get(f'{{{W}}}abstractNumId'): n for n in root.findall(f'{{{W}}}abstractNum')}
            for num in root.findall(f'{{{W}}}num'):
                ref = num.find(f'{{{W}}}abstractNumId')
                levels = abstract.get(ref.get(f'{{{W}}}val') if ref is not None else '')
                if levels is not None:
                    for level in levels:
                        fmt = level.find(f'{{{W}}}numFmt')
                        numbering[(num.get(f'{{{W}}}numId'), level.get(f'{{{W}}}ilvl'))] = (
                            fmt.get(f'{{{W}}}val') if fmt is not None else 'decimal'
                        )
                        start = level.find(f'{{{W}}}start')
                        numbering_starts[(num.get(f'{{{W}}}numId'), level.get(f'{{{W}}}ilvl'))] = (
                            int(start.get(f'{{{W}}}val', '1')) if start is not None else 1
                        )

        def val(node, path, default=None):
            found = node.find('/'.join(f'{{{W}}}{part}' for part in path.split('/')))
            return found.get(f'{{{W}}}val', default) if found is not None else default

        def marks_for(node, inherited):
            marks = list(inherited)
            for tag, mark in [('b', 'bold'), ('i', 'italic'), ('u', 'underline'), ('strike', 'strike')]:
                prop = node.find(f'{{{W}}}rPr/{{{W}}}{tag}')
                if prop is not None:
                    marks = [m for m in marks if m['type'] != mark]
                    if prop.get(f'{{{W}}}val') not in {'0', 'false', 'none'}:
                        marks.append({'type': mark})
            vertical = val(node, 'rPr/vertAlign')
            if vertical in {'superscript', 'subscript'}:
                marks.append({'type': vertical})
            return marks

        def consume(location, kinds):
            for kind in kinds:
                if lookup[(location, kind)]:
                    return lookup[(location, kind)].popleft()
            return None

        def inline(node, location, inherited=()):  # noqa: C901
            tag = etree.QName(node).localname
            if tag in {'del', 'moveFrom', 'pPr', 'rPr', 'tblPr', 'tcPr'}:
                return []
            if tag == 't':
                return (
                    [{'type': 'text', 'text': node.text, **({'marks': list(inherited)} if inherited else {})}]
                    if node.text
                    else []
                )
            if tag == 'tab':
                return [{'type': 'text', 'text': '\t'}]
            if tag in {'br', 'cr'}:
                return [{'type': 'hardBreak'}]
            if tag == 'AlternateContent':
                return inline(node[0], location, inherited) if len(node) else []
            if tag == 'r':
                style = styles.get(val(node, 'rPr/rStyle'))
                inherited = marks_for(style, inherited) if style is not None else inherited
                inherited = marks_for(node, inherited)
            if tag == 'hyperlink':
                target = rels.get(node.get(f'{{{R}}}id'))
                if safe_link(target):
                    inherited = [*inherited, {'type': 'link', 'attrs': {'href': target}}]
            if tag in {'blip', 'imagedata'}:
                rid = node.get(f'{{{R}}}embed') or node.get(f'{{{R}}}id') or node.get(f'{{{R}}}link')
                block = consume(location, ('image',) if rid in embedded_images else ('unsupported',))
                return [image_node(block)] if block else []
            if tag in {'footnoteReference', 'endnoteReference', 'commentReference'}:
                kind = tag.removesuffix('Reference')
                identifier = node.get(f'{{{W}}}id')
                label = {'footnote': '脚注', 'endnote': '尾注', 'comment': '批注'}[kind]
                candidates = lookup[(f'{label} {identifier}', 'annotation' if kind == 'comment' else kind)]
                block = candidates[0] if candidates else None
                if block:
                    return [
                        {
                            'type': 'writingNote',
                            'attrs': {
                                'materialId': 'pending',
                                'blockId': block.id,
                                'label': identifier,
                                'kind': 'annotation' if kind == 'comment' else kind,
                                'note': block.text,
                            },
                        }
                    ]
            if tag in {'chart', 'OLEObject', 'altChunk', 'oMath', 'oMathPara', 'relIds'}:
                block = consume(location, ('unsupported',))
                return [image_node(block)] if block else []
            if tag == 'txbxContent':
                return containers(node, location + ' 文本框')
            return [item for child in node if isinstance(child.tag, str) for item in inline(child, location, inherited)]

        def paragraph(node, location):
            style_id = val(node, 'pPr/pStyle')
            style = styles.get(style_id)
            style_name = val(style, 'name', '') if style is not None else ''
            outline = val(node, 'pPr/outlineLvl')
            if outline is None and style is not None:
                outline = val(style, 'pPr/outlineLvl')
            heading = re.search(r'(?:heading|标题)\s*([1-6])', style_name or style_id or '', re.I)
            level = (
                min(int(outline) + 1, 6)
                if outline is not None and outline.isdigit() and int(outline) < 6
                else int(heading[1])
                if heading
                else None
            )
            attrs = {'level': level} if level else {}
            align = val(node, 'pPr/jc')
            if align in {'left', 'center', 'right', 'both', 'justify'}:
                attrs['textAlign'] = 'justify' if align == 'both' else align
            inherited = marks_for(style, []) if style is not None else []
            items = inline(node, location, inherited)
            result, text = [], []

            def flush():
                if text:
                    result.append(
                        {
                            'type': 'heading' if level else 'paragraph',
                            **({'attrs': attrs} if attrs else {}),
                            'content': text.copy(),
                        }
                    )
                    text.clear()

            for item in items:
                if item['type'] in {'text', 'hardBreak', 'writingNote'}:
                    text.append(item)
                else:
                    flush()
                    result.append(item)
            flush()
            return result or [{'type': 'paragraph'}]

        def containers(parent, location=None):  # noqa: C901 -- Lists and merged table cells preserve source hierarchy.
            result = []
            list_stack = []
            for i, node in enumerate(parent, 1):
                loc = location or f'正文第 {i} 块'
                tag = etree.QName(node).localname
                if tag == 'p':
                    blocks = paragraph(node, loc)
                    paragraph_style = styles.get(val(node, 'pPr/pStyle'))
                    num_id = val(node, 'pPr/numPr/numId') or (
                        val(paragraph_style, 'pPr/numPr/numId') if paragraph_style is not None else None
                    )
                    level = (
                        val(node, 'pPr/numPr/ilvl')
                        or (val(paragraph_style, 'pPr/numPr/ilvl') if paragraph_style is not None else None)
                        or '0'
                    )
                    if num_id and num_id != '0':
                        depth = min(int(level), 8) if level.isdigit() else 0
                        list_type = 'bulletList' if numbering.get((num_id, level)) == 'bullet' else 'orderedList'
                        while list_stack and (
                            list_stack[-1][0] > depth
                            or (list_stack[-1][0] == depth and list_stack[-1][1] != (num_id, list_type))
                        ):
                            list_stack.pop()
                        if not list_stack or list_stack[-1][0] < depth:
                            listing = {'type': list_type, 'content': []}
                            if list_type == 'orderedList':
                                listing['attrs'] = {
                                    'start': max(
                                        1, numbering_starts.get((num_id, level), 1) + numbering_counts[(num_id, level)]
                                    )
                                }
                            (
                                list_stack[-1][2]['content'][-1]['content']
                                if list_stack and list_stack[-1][2]['content']
                                else result
                            ).append(listing)
                            list_stack.append((depth, (num_id, list_type), listing))
                        if blocks[0]['type'] != 'paragraph':
                            blocks.insert(0, {'type': 'paragraph'})
                        list_stack[-1][2]['content'].append({'type': 'listItem', 'content': blocks})
                        numbering_counts[(num_id, level)] += 1
                        for key in list(numbering_counts):
                            if key[0] == num_id and int(key[1]) > depth:
                                numbering_counts[key] = 0
                    else:
                        list_stack = []
                        # A Word caption immediately after a figure moves together with that figure.
                        style = val(node, 'pPr/pStyle', '')
                        if (
                            result
                            and result[-1]['type'] == 'writingImage'
                            and (style.lower() == 'caption' or style == '题注')
                        ):
                            result[-1]['content'] = [
                                part
                                for block in blocks
                                for part in block.get('content', [])
                                if part['type'] in {'text', 'hardBreak', 'writingNote'}
                            ]
                        else:
                            result.extend(blocks)
                elif tag == 'tbl':
                    list_stack = []
                    rows = []
                    origins = {}
                    for row_index, row in enumerate(node.findall(f'{{{W}}}tr')):
                        cells, column = [], 0
                        for cell in row.findall(f'{{{W}}}tc'):
                            span = int(val(cell, 'tcPr/gridSpan', '1'))
                            merge = cell.find(f'{{{W}}}tcPr/{{{W}}}vMerge')
                            if merge is not None and merge.get(f'{{{W}}}val') != 'restart' and column in origins:
                                origins[column]['attrs']['rowspan'] += 1
                            else:
                                item = {
                                    'type': 'tableCell',
                                    'attrs': {'colspan': span, 'rowspan': 1},
                                    'content': containers(cell, loc) or [{'type': 'paragraph'}],
                                }
                                cells.append(item)
                                if merge is not None:
                                    origins[column] = item
                                else:
                                    origins.pop(column, None)
                            column += span
                        rows.append({'type': 'tableRow', 'content': cells})
                    result.append({'type': 'table', 'content': rows})
                elif tag not in {'sectPr', 'tcPr', 'tblPr', 'tblGrid'}:
                    result.extend(containers(node, loc))
            return result

        body = xml('word/document.xml').find(f'{{{W}}}body')
        return {'type': 'doc', 'content': containers(body)}


def markdown_layout(text, parsed):  # noqa: C901 -- HTML nodes map to a deliberately restricted editor schema.
    import markdown
    from lxml import html

    root = html.fragment_fromstring(markdown.markdown(text, extensions=['tables', 'fenced_code']), create_parent='div')
    mark_tags = {
        'strong': 'bold',
        'b': 'bold',
        'em': 'italic',
        'i': 'italic',
        'u': 'underline',
        's': 'strike',
        'code': 'code',
    }
    blocks = {
        'p': 'paragraph',
        'ul': 'bulletList',
        'ol': 'orderedList',
        'li': 'listItem',
        'blockquote': 'blockquote',
        'table': 'table',
        'tr': 'tableRow',
        'td': 'tableCell',
        'th': 'tableHeader',
        'pre': 'codeBlock',
    }

    def convert(element, marks=()):  # noqa: C901 -- Enumerates supported block and inline structures.
        tag = element.tag
        if tag in {'script', 'style'}:
            return []
        if tag == 'img':
            block = parsed.add('unsupported', 'Markdown 图片', detail='Linked image is not embedded in the document')
            return [image_node(block)]
        if tag == 'br':
            return [{'type': 'hardBreak'}]
        if tag == 'hr':
            return [{'type': 'horizontalRule'}]
        if tag in mark_tags:
            marks = [*marks, {'type': mark_tags[tag]}]
        if tag == 'a' and safe_link(element.get('href')):
            marks = [*marks, {'type': 'link', 'attrs': {'href': element.get('href')}}]
        content = []

        def add_text(value):
            if value:
                content.append({'type': 'text', 'text': value, **({'marks': list(marks)} if marks else {})})

        add_text(element.text)
        for child in element:
            content.extend(convert(child, marks))
            add_text(child.tail)
        if tag in blocks or re.fullmatch(r'h[1-6]', tag):
            kind = blocks.get(tag, 'heading')
            if kind in {'listItem', 'tableCell', 'tableHeader'}:
                grouped, pending = [], []
                for child in content:
                    if child['type'] in {'text', 'hardBreak'}:
                        pending.append(child)
                    else:
                        if pending:
                            grouped.append({'type': 'paragraph', 'content': pending})
                            pending = []
                        grouped.append(child)
                if pending:
                    grouped.append({'type': 'paragraph', 'content': pending})
                content = grouped or [{'type': 'paragraph'}]
            if kind == 'paragraph' and any(c['type'] == 'writingPlaceholder' for c in content):
                result, pending = [], []
                for child in content:
                    if child['type'] == 'writingPlaceholder':
                        if pending:
                            result.append({'type': 'paragraph', 'content': pending})
                            pending = []
                        result.append(child)
                    else:
                        pending.append(child)
                if pending:
                    result.append({'type': 'paragraph', 'content': pending})
                return result
            if kind == 'codeBlock':
                content = [{'type': 'text', 'text': ''.join(element.itertext())}] if ''.join(element.itertext()) else []
            return [
                {'type': kind, **({'attrs': {'level': int(tag[1])}} if kind == 'heading' else {}), 'content': content}
            ]
        return content

    content = [item for child in root for item in convert(child)]
    return {'type': 'doc', 'content': content or [{'type': 'paragraph'}]}


def reflow_pdf_entries(entries, page_width):  # noqa: C901 -- Separate column, line and paragraph boundaries.
    """Read columns in order and join adjacent visual lines only within a paragraph."""
    from statistics import median

    text_entries = [entry for entry in entries if entry[1] == 'text']
    normal_size = median([entry[3] for entry in text_entries]) if text_entries else 12
    left = [e for e in entries if e[0][2] < page_width * 0.56 and e[0][0] < page_width * 0.4]
    right = [e for e in entries if e[0][0] > page_width * 0.44]
    columns = len(left) >= 3 and len(right) >= 3
    ordered = []
    remaining = sorted(entries, key=lambda e: (-e[0][3], e[0][0]))
    if columns:
        wide = [e for e in remaining if e not in left and e not in right]
        for boundary in [*wide, None]:
            band = [e for e in remaining if boundary is None or e[0][3] > boundary[0][3] + 2]
            ordered.extend(sorted(band, key=lambda e: (0 if e in left else 1, -round(e[0][3], 1), e[0][0])))
            remaining = [e for e in remaining if e not in band]
            if boundary is not None:
                ordered.append(boundary)
                remaining.remove(boundary)
    else:
        ordered = remaining
    lines = []
    for entry in ordered:
        bounds, kind, value, size = entry
        if kind != 'text':
            lines.append([bounds, kind, value, size])
            continue
        value = ' '.join(part.strip() for part in value.splitlines() if part.strip())
        if lines and lines[-1][1] == 'text':
            previous = lines[-1]
            same_line = abs(previous[0][3] - bounds[3]) < max(2, min(size, previous[3]) * 0.2)
            if same_line and 0 <= bounds[0] - previous[0][2] < max(size * 2, 12):
                space = (
                    ''
                    if re.search(r'[\u4e00-\u9fff]$', previous[2])
                    or re.match(r'[,.;:!?，。；：！？\u4e00-\u9fff]', value)
                    else ' '
                )
                previous[2] += space + value
                previous[0] = (
                    previous[0][0],
                    min(previous[0][1], bounds[1]),
                    bounds[2],
                    max(previous[0][3], bounds[3]),
                )
                continue
        lines.append([bounds, kind, value, size])
    content = []
    previous_line = None
    column_right = {
        0: max((e[0][2] for e in left), default=page_width),
        1: max((e[0][2] for e in right), default=page_width),
    }
    full_right = max((e[0][2] for e in text_entries), default=page_width)
    for bounds, kind, value, size in lines:
        if kind == 'image':
            content.append(value)
            previous_line = None
            continue
        heading = size > normal_size * 1.3 and len(value) < 100
        edge = column_right[0 if bounds[0] < page_width * 0.44 else 1] if columns else full_right
        if previous_line and not heading and content[-1]['type'] == 'paragraph':
            pb, ps = previous_line
            gap = pb[1] - bounds[3]
            if (
                abs(pb[0] - bounds[0]) < 6
                and 0 <= gap < max(ps, size) * 1.25
                and abs(ps - size) < 1.5
                and pb[2] > edge - ps * 3
            ):
                previous_text = content[-1]['content'][-1]['text']
                space = (
                    ''
                    if re.search(r'[\u4e00-\u9fff，。；：！？]$', previous_text)
                    or re.match(r'[\u4e00-\u9fff，。；：！？]', value)
                    else ' '
                )
                content[-1]['content'][-1]['text'] += space + value
                previous_line = (bounds, size)
                continue
        content.append(
            {
                'type': 'heading' if heading else 'paragraph',
                **({'attrs': {'level': 2}} if heading else {}),
                'content': [{'type': 'text', 'text': value}],
            }
        )
        previous_line = (bounds, size)
    return content


def pdf_layout(data, parsed, max_pages=50):  # noqa: C901 -- Native, scanned and vector pages have separate paths.
    """Use PDF object bounds for native content; preserve complex vector pages as page images."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from open_webui.services.education.writing_context import DraftFileError

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(''):
        raise DraftFileError('This file is password protected')
    if len(reader.pages) > max_pages:
        raise DraftFileError('The PDF has more than 50 pages')
    content = []
    with pdfium.PdfDocument(data) as pdf:
        for index in range(len(pdf)):
            with closing(pdf[index]) as page, closing(page.get_textpage()) as textpage:
                objects = list(page.get_objects(textpage=textpage))
                page_width, page_height = page.get_size()
                native = textpage.get_text_bounded().strip()
                invalid = '\x00' in native or '\ufffd' in native
                complex_page = any(obj.type not in (1, 3) for obj in objects)
                page_bitmap = any(
                    obj.type == 3
                    and (obj.get_bounds()[2] - obj.get_bounds()[0]) >= page_width * 0.85
                    and (obj.get_bounds()[3] - obj.get_bounds()[1]) >= page_height * 0.85
                    for obj in objects
                )

                def raster(bounds=None):
                    crop = (
                        (0, 0, 0, 0)
                        if bounds is None
                        else (
                            max(0, bounds[0]),
                            max(0, bounds[1]),
                            max(0, page_width - bounds[2]),
                            max(0, page_height - bounds[3]),
                        )
                    )
                    bitmap = page.render(scale=2400 / max(page_width, page_height), crop=crop)
                    try:
                        out = io.BytesIO()
                        bitmap.to_pil().convert('RGB').save(out, 'PNG')
                        return out.getvalue()
                    finally:
                        bitmap.close()

                location = f'第 {index + 1} 页'
                if objects and (not native or invalid or complex_page or page_bitmap):
                    block = parsed.add(
                        'page',
                        location,
                        image=raster(),
                        detail='Complex page preserved as an image' if complex_page else '',
                    )
                    node = image_node(block)
                    # Complex layouts stay visible exactly once. The native layer can be explicitly
                    # converted to prose without OCR, including when image reading is disabled.
                    node['attrs']['nativeText'] = native if not invalid else ''
                    block.native_text = node['attrs']['nativeText']
                    node['attrs']['nativeTextEdited'] = False
                    content.append(node)
                else:
                    entries = []
                    for obj in objects:
                        bounds = obj.get_bounds()
                        if obj.type == 1:
                            text = obj.extract().strip()
                            if text:
                                entries.append((bounds, 'text', text, obj.get_font_size()))
                        elif obj.type == 3 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                            block = parsed.add('image', location, image=raster(bounds))
                            entries.append((bounds, 'image', image_node(block), 0))
                    content.extend(reflow_pdf_entries(entries, page_width))
                for reference in reader.pages[index].get('/Annots', []):
                    annotation = reference.get_object()
                    text = '\n'.join(
                        str(v) for v in (annotation.get('/Contents'), (annotation.get('/A') or {}).get('/URI')) if v
                    )
                    if text:
                        block = parsed.add('annotation', location + ' 批注/链接', text)
                        content.append(
                            {
                                'type': 'paragraph',
                                'content': [
                                    {
                                        'type': 'writingNote',
                                        'attrs': {
                                            'materialId': 'pending',
                                            'blockId': block.id,
                                            'label': str(index + 1),
                                            'kind': 'annotation',
                                            'note': text,
                                        },
                                    }
                                ],
                            }
                        )
                if sum(len(v) for v in parsed.images.values()) > 64 * 1024 * 1024:
                    raise DraftFileError('The file is too large')
    parsed.document = {'type': 'doc', 'content': content or [{'type': 'paragraph'}]}
    parsed.text = document_text(parsed.document)
    return parsed
