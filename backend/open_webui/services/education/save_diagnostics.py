"""Content-free diagnostics for writing saves, including dependency/validation failures."""

import logging
import re
import uuid

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from open_webui.env import WEBUI_BUILD_HASH

log = logging.getLogger(__name__)
SAVE_ACTIONS = {'autosave', 'versions', 'operations', 'provenance', 'pending-draft', 'draft-baseline'}
FORM_FIELDS = {
    'body',
    'content_json',
    'content_text',
    'content_html',
    'save_reason',
    'trigger_type',
    'operations',
    'op_type',
    'source_type',
    'start_offset',
    'end_offset',
    'inserted_text',
    'deleted_text',
    'batch_id',
    'occurred_at_ms',
    'client_sequence',
    'metadata_json',
    'segments',
    'segment_id',
    'segment_text',
    'source_message_id',
    'version_id',
    'replace_existing',
    'materials',
    'expected_revision',
    'text',
    'expected_draft_revision',
}


class WritingSaveRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def diagnosed(request):
            if request.method not in {'POST', 'PUT', 'PATCH'} or self.path.rsplit('/', 1)[-1] not in SAVE_ACTIONS:
                return await handler(request)
            try:
                return await handler(request)
            except (HTTPException, RequestValidationError) as error:
                request_id = uuid.uuid4().hex
                if isinstance(error, RequestValidationError):
                    fields = error.errors()[0].get('loc', ()) if error.errors() else ()
                    field = '.'.join(str(f) if isinstance(f, int) or f in FORM_FIELDS else 'field' for f in fields)
                    status, code = 422, 'invalid_request'
                    headers = {}
                else:
                    status = error.status_code
                    headers = dict(error.headers or {})
                    field = headers.get('X-Writing-Error-Field', '')
                    code = headers.get('X-Writing-Error-Code', 'writing_state' if status < 500 else 'save_unavailable')
                # Only server-generated identifiers, route templates and known field paths enter logs.
                log.warning(
                    'writing_save_rejected request_id=%s route=%s status=%s code=%s field=%s build=%s client_build=%s',
                    request_id,
                    self.path,
                    status,
                    code,
                    field,
                    re.sub(r'[^A-Za-z0-9._-]', '', WEBUI_BUILD_HASH)[:80],
                    request.headers.get('X-Writing-Client-Build', '')
                    if re.fullmatch(r'[A-Za-z0-9._-]{1,80}', request.headers.get('X-Writing-Client-Build', ''))
                    else 'unknown',
                )
                headers['X-Request-ID'] = request_id
                headers['X-Writing-Error-Code'] = code
                if field:
                    headers['X-Writing-Error-Field'] = field
                if isinstance(error, RequestValidationError):
                    return JSONResponse({'detail': 'Invalid writing request'}, status_code=422, headers=headers)
                error.headers = headers
                raise
            except Exception as error:
                request_id = uuid.uuid4().hex
                log.error(
                    'writing_save_failed request_id=%s route=%s status=500 exception_type=%s',
                    request_id,
                    self.path,
                    type(error).__name__,
                )
                return JSONResponse(
                    {'detail': 'Writing save is temporarily unavailable'},
                    status_code=500,
                    headers={'X-Request-ID': request_id, 'X-Writing-Error-Code': 'save_unavailable'},
                )

        return diagnosed
