"""Persistence and access boundaries for pending drafts and downloadable writing."""

import copy
import time
from urllib.parse import quote

from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from open_webui.models.notes import Note
from open_webui.models.writing_materials import MaterialSelection
from open_webui.services.education.writing_document import (
    DocumentValidationError,
    check_document_resources,
    document_content,
    export_docx,
    text_document,
    validate_document,
)


class PendingDraftForm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content_json: dict
    materials: list[MaterialSelection] = Field(default_factory=list, max_length=20)
    expected_revision: int = Field(ge=0)


class WordExportForm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content_json: dict
    pending: bool = False


def checked_content(document, text, session_id, db):
    try:
        document = validate_document(document if document is not None else text_document(text))
    except DocumentValidationError as error:
        raise HTTPException(
            400,
            str(error),
            headers={
                'X-Writing-Error-Code': 'document_format',
                'X-Writing-Error-Field': error.field,
            },
        ) from error
    try:
        check_document_resources(document, session_id, db)
    except HTTPException as error:
        error.headers = {
            **(error.headers or {}),
            'X-Writing-Error-Code': 'material_reference',
            'X-Writing-Error-Field': 'content_json',
        }
        raise
    return document_content(document)


def pending_draft(session, db):
    from open_webui.models.writing_materials import WritingMaterial
    from open_webui.services.education.materials import material_view

    note = db.get(Note, session.note_id)
    if note is None:
        raise HTTPException(409, 'Writing note is missing')
    pending = (note.data or {}).get('pending_draft')
    if pending is None:
        return {'content_json': text_document(''), 'materials': [], 'revision': 0}
    ids = [item['id'] for item in pending['materials']]
    rows = (
        db.query(WritingMaterial)
        .filter(WritingMaterial.id.in_(ids), WritingMaterial.writing_session_id == session.id)
        .all()
        if ids
        else []
    )
    return {**copy.deepcopy(pending), 'materials': [material_view(row) for row in rows]}


def save_pending_draft(session, form, db):
    from open_webui.models.writing_materials import WritingMaterial

    note = db.get(Note, session.note_id)
    old = (note.data or {}).get('pending_draft') or {'revision': 0}
    if old['revision'] != form.expected_revision:
        raise HTTPException(409, 'This draft changed in another window. Reload before saving.')
    content = checked_content(form.content_json, '', session.id, db)
    for selection in form.materials:
        row = db.get(WritingMaterial, selection.id)
        if row is None or row.writing_session_id != session.id:
            raise HTTPException(404, 'Material not found')
    pending = {
        'content_json': content['json'],
        'materials': [m.model_dump() for m in form.materials],
        'revision': old['revision'] + 1,
    }
    note.data = {**(note.data or {}), 'pending_draft': pending}
    note.updated_at = time.time_ns()
    db.commit()
    return {'revision': pending['revision']}


def activate_document(document, session_id, db):
    rows = check_document_resources(document, session_id, db)
    for row in rows.values():
        row.active = True
        if row.confirmed_at is None:
            row.confirmed_at = int(time.time())
    db.flush()


def save_writing_document(session, content, db):
    """Assets and note content share one connection and commit, including on SQLite."""
    from open_webui.models.education import WritingSession

    note = db.get(Note, session.note_id)
    if note is None:
        raise HTTPException(409, 'Writing note is missing')
    activate_document(content['json'], session.id, db)
    note.data = {**(note.data or {}), 'content': content}
    note.updated_at = time.time_ns()
    db.get(WritingSession, session.id).updated_at = int(time.time())
    db.commit()


def word_response(document, session_id, db, filename):
    from open_webui.services.education.materials import read_asset

    rows = check_document_resources(document, session_id, db)
    try:
        data = export_docx(document, lambda material_id, block_id: read_asset(rows[material_id], block_id + '.jpg'))
    except (ValueError, KeyError, OSError) as error:
        raise HTTPException(409, 'Could not export the complete document. Please retry or check the images.') from error
    filename = ''.join(c for c in filename if c not in '\\/:*?"<>|\r\n')[:160] + '.docx'
    return Response(
        data,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename),
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )
