"""One captured configuration and request builder for formal and trial teaching.

Only trusted resource adapters may install a binding on request.state. Nothing
in the client request (including metadata) grants model access.
"""

import copy
import hashlib
import json
import time
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from open_webui.models.config import Config
from open_webui.models.education import Education, get_db_context
from open_webui.models.models import Models
from open_webui.models.notes import Note
from open_webui.models.teaching_trials import AssignmentAiRevision, TeachingCall, TeachingModelPolicy
from open_webui.services.education.ai_steps import available_models
from open_webui.services.education.teaching_config import lock_assignment
from open_webui.services.education.materials import material_context, material_rules, snapshot_materials

EXECUTION_VERSION = 'argument-teaching-2026-11-08.materials-1'
# Explicit public generation fields; credentials and arbitrary headers cannot be frozen.
GENERATION_KEYS = frozenset(
    (
        'temperature',
        'top_p',
        'top_k',
        'min_p',
        'seed',
        'max_tokens',
        'max_completion_tokens',
        'frequency_penalty',
        'presence_penalty',
        'stop',
    )
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()


@lru_cache(maxsize=1)
def execution_version():
    """Version of this worker's implementation, fixed for its request lifetime."""
    root = Path(__file__).resolve().parents[2]
    paths = (
        'services/education/teaching_runtime.py',
        'services/education/materials.py',
        'services/education/teaching_filters.py',
        'services/education/teaching_search.py',
        'services/education/revision_reading.py',
        'services/education/ai_steps.py',
        'utils/thinking.py',
        'utils/model_fallback.py',
        'utils/middleware.py',
        'utils/chat.py',
        'routers/openai.py',
    )
    digest = hashlib.sha256(b''.join((root / path).read_bytes() for path in paths)).hexdigest()[:16]
    return f'{EXECUTION_VERSION}:{digest}'


async def model_policy():
    return TeachingModelPolicy.model_validate(await Config.get('education.teaching_models', {}))


async def resolve_binding(request, user, candidate):
    policy = await model_policy()
    model_id = candidate.model_id
    if model_id not in policy.model_ids:
        raise HTTPException(409, 'This model is not authorized for teaching')
    models = await available_models(request, user)
    model = models.get(model_id)
    if not model or model.get('pipe') or model.get('pipeline') or model.get('owned_by') == 'arena':
        raise HTTPException(409, 'Teaching model is unavailable; choose and publish another model')
    info = await Models.get_model_by_id(model_id)
    if info is not None and not info.is_active:
        raise HTTPException(409, 'Teaching model is unavailable; choose and publish another model')
    meta = info.meta.model_dump() if info is not None else (model.get('info') or {}).get('meta') or {}
    base_id = info.base_model_id if info and info.base_model_id else model_id
    base = models.get(base_id)
    if not base:
        raise HTTPException(409, 'Teaching base model is unavailable')
    params = {
        **(await Config.get('models.default_params', {}) or {}),
        **(info.params.model_dump() if info and info.params else {}),
    }
    params = {k: v for k, v in params.items() if k in GENERATION_KEYS and v is not None}
    # Hash routing configuration, never store URL, credentials, auth headers or keys.
    connection = (getattr(request.app.state, 'OPENAI_MODELS', {}) or {}).get(base_id, base)
    idx = connection.get('urlIdx')
    route = {'base_model_id': base_id, 'url_index': idx}
    if idx is not None:
        from open_webui.routers.openai import get_openai_connection

        url, _, api_config = await get_openai_connection(idx)
        route['connection_hash'] = fingerprint(
            {
                'url': url,
                **{
                    k: api_config.get(k)
                    for k in ('prefix_id', 'api_type', 'api_version', 'provider', 'connection_type', 'thinking_format')
                },
            }
        )
    from open_webui.env import ENABLE_PLUGINS
    from open_webui.models.functions import Functions
    from open_webui.routers.pipelines import get_sorted_filters

    functions = await Functions.get_global_filter_functions() if ENABLE_PLUGINS else []
    valves = await Functions.get_function_valves_by_ids([f.id for f in functions]) if functions else {}
    filter_fingerprint = fingerprint(
        {
            'functions': [f.model_dump() for f in functions],
            'valves': valves,
            'pipelines': get_sorted_filters(model_id, models),
        }
    )
    from open_webui.utils.model_fallback import resolve_fallback
    fallback = await resolve_fallback(request, info)
    return {
        **({'fallback': fallback} if fallback else {}),
        'model_id': model_id,
        'base_model_id': base_id,
        'workspace_model': info is not None,
        'route': route,
        'params': params,
        'filter_fingerprint': filter_fingerprint,
        'thinking_support': model.get('thinking_support') or {},
        'thinking_format': model.get('thinking_format'),
        'capabilities': {k: v for k, v in (meta.get('capabilities') or {}).items() if k in ('reasoning', 'vision')},
    }


async def validate_binding(request, user, config, *, check_execution=True):
    if check_execution and config['execution_version'] != execution_version():
        raise HTTPException(409, 'Teaching execution rules changed; start a new teaching trial')
    from open_webui.models.teaching_trials import AiCandidate

    current = await resolve_binding(request, user, AiCandidate.model_validate(config['ai']))
    binding = config['binding']
    # Global sampling changes invalidate trial coverage but do not overwrite a
    # published generation snapshot. Routing/capability changes require republishing.
    if current.get('fallback') != binding.get('fallback') or any(
        current[k] != binding[k]
        for k in (
            'route',
            'workspace_model',
            'thinking_support',
            'thinking_format',
            'capabilities',
            'filter_fingerprint',
        )
    ):
        raise HTTPException(409, 'Teaching model configuration changed; publish a new teaching version')
    return current


def config_fingerprint(config):
    return fingerprint(
        {k: config[k] for k in ('ai', 'binding', 'title', 'description', 'description_version', 'execution_version')}
        | {'validation_environment': config.get('validation_environment')}
    )


def actual_thinking(config):
    from open_webui.utils.thinking import ThinkingSupport, effective_thinking_level

    if not config['binding']['capabilities'].get('reasoning'):
        return 'model_default'
    return effective_thinking_level(config['ai']['thinking'], ThinkingSupport(**config['binding']['thinking_support']))


def assignment_config(assignment, db):
    revision = (
        db.get(AssignmentAiRevision, assignment.current_ai_revision_id) if assignment.current_ai_revision_id else None
    )
    if revision is None or revision.assignment_id != assignment.id:
        raise HTTPException(409, 'The teacher must publish an AI teaching configuration for this assignment')
    return {
        **copy.deepcopy(revision.config),
        'ai_revision_id': revision.id,
        'ai_revision': revision.revision,
        'title': assignment.title,
        'description': assignment.description or '',
        'description_version': assignment.description_version,
        'change_summary': revision.change_summary,
        # The business revision freezes prompt/model settings, not server code.
        # New formal calls record the actual worker version without rewriting v1.
        'execution_version': execution_version(),
    }


def system_context(config):
    return '\n\n'.join(
        (
            config['ai']['prompt'],
            '【本次作业信息】',
            f'标题：{config["title"]}\n{config["description"]}',
        )
    )


def build_messages(config, stage, source, dialogue, materials=None):
    from open_webui.services.education.revision_reading import (
        FORMAT,
        PURPOSES,
        attach_current_revision_draft,
    )

    history = [
        {'role': m['role'], 'content': m.get('content') or ''}
        for m in dialogue
        if m.get('role') in ('user', 'assistant')
    ]
    system = system_context(config) + material_rules(materials)
    if stage == 'first_read':
        return [
            {'role': 'system', 'content': system + '\n' + PURPOSES[stage] + '\n' + FORMAT},
            {
                'role': 'user',
                'content': json.dumps({'当前保存稿': source, '相关讨论': history}, ensure_ascii=False) + material_context(materials),
            },
        ]
    return [{'role': 'system', 'content': system}, *attach_current_revision_draft(history, source, materials)]


def install_binding(request, config, evidence):
    request.state.teaching_binding = copy.deepcopy(config)
    request.state.teaching_evidence = evidence
    request.state.education_revision_context = True


def authorized_binding(request, model_id):
    config = getattr(request.state, 'teaching_binding', None)
    return config if config and config['ai']['model_id'] == model_id else None


def record_provider_request(request, payload):
    evidence = getattr(request.state, 'teaching_evidence', None)
    if evidence is not None:
        # Provider payload contains no connection secrets; allowlist nevertheless.
        attempt = {
            'request': copy.deepcopy(
                {
                    k: v
                    for k, v in payload.items()
                    if k
                    in GENERATION_KEYS
                    | {
                        'model',
                        'messages',
                        'input',
                        'instructions',
                        'stream',
                        'reasoning',
                        'reasoning_effort',
                        'thinking',
                        'enable_thinking',
                        'max_output_tokens',
                        'response_format',
                        'tools',
                        'tool_choice',
                    }
                }
            ),
            'started_at': int(time.time()),
        }
        evidence.setdefault('attempts', []).append(attempt)
        return attempt


def saved_dialogue(session, db):
    """Capture the real conversation chain, never client-supplied assistant history."""
    from open_webui.models.chat_messages import ChatMessage
    from open_webui.models.chats import Chat

    chat = db.query(Chat).filter_by(folder_id=session.folder_id, user_id=session.owner_user_id).one_or_none()
    if chat is None or not chat.current_message_id:
        return []
    prefix = f'{chat.id}-'
    messages = {row.id.removeprefix(prefix): row for row in db.query(ChatMessage).filter_by(chat_id=chat.id).all()}
    current = chat.current_message_id.removeprefix(prefix)
    seen, result = set(), []
    while current:
        if current in seen or current not in messages:
            raise HTTPException(409, 'The saved conversation chain is incomplete')
        seen.add(current)
        row = messages[current]
        if row.role == 'user' or row.role == 'assistant' and row.done and not row.error:
            result.append({'role': row.role, 'content': row.content or ''})
        current = row.parent_id.removeprefix(prefix) if row.parent_id else None
    return list(reversed(result))


def capture_formal(session, request_key, stage, db, *, user, user_text=None):
    assignment = lock_assignment(session.assignment_id, db)
    from open_webui.routers.education import _ensure_assignment_access

    if session.owner_user_id != user.id or _ensure_assignment_access(user, assignment, db) not in ('student', 'admin'):
        raise HTTPException(403, 'Student access to this writing session is required')
    from open_webui.services.education.writing_access import ensure_writing_session_writable

    ensure_writing_session_writable(session, db)
    session = Education.get_writing_session_by_id(session.id, db=db)
    if session.draft_baseline_at is None:
        raise HTTPException(409, 'Confirm your draft before chatting with the AI')
    old = db.query(TeachingCall).filter_by(session_id=session.id, request_key=request_key).first()
    if old:
        raise HTTPException(409, 'This request has already been accepted; reload the conversation')
    running = db.query(TeachingCall).filter_by(session_id=session.id, status='running').first()
    if running:
        raise HTTPException(409, 'An AI request is already running in this writing session')
    config = assignment_config(assignment, db)
    note = db.get(Note, session.note_id)
    source = (
        session.draft_baseline_text if stage == 'first_read' else ((note.data or {}).get('content') or {}).get('md', '')
    )
    version = Education.get_latest_version(session.id, db=db)
    previous = (
        db.query(TeachingCall)
        .filter_by(session_id=session.id, status='ready')
        .order_by(TeachingCall.sequence.desc())
        .first()
    )
    sequence = (db.query(func.max(TeachingCall.sequence)).filter_by(session_id=session.id).scalar() or 0) + 1
    context = {
        'config': config,
        'materials': snapshot_materials(session.id, db),
        'ai_revision_id': config['ai_revision_id'],
        'ai_revision': config['ai_revision'],
        'source_text': source,
        'source_version_id': version.id if version and version.note_snapshot_text == source else None,
        'previous_text': previous.context['source_text'] if previous else session.draft_baseline_text,
        'purpose': stage,
        'description_version': assignment.description_version,
        'teaching_version': config['ai']['template_version'],
        'called_at': int(time.time()),
        'fingerprint': config_fingerprint(config),
        'attempts': [],
    }
    context.update(requested_thinking=config['ai']['thinking'], actual_thinking=actual_thinking(config))
    context['dialogue'] = [] if stage == 'first_read' else saved_dialogue(session, db)
    if user_text is not None:
        context['dialogue'].append({'role': 'user', 'content': user_text})
    context['sample_fingerprint'] = fingerprint([stage, source, context['materials'], context['previous_text'], context['dialogue']])
    context['sequence'] = sequence
    call = TeachingCall(
        id=str(uuid.uuid4()),
        session_id=session.id,
        assignment_id=assignment.id,
        revision_id=config['ai_revision_id'],
        request_key=request_key,
        status='running',
        context=context,
        sequence=sequence,
        created_at=int(time.time()),
    )
    context['call_id'] = call.id
    call.context = copy.deepcopy(context)
    db.add(call)
    db.commit()
    return config, context


def finish_formal(context, status):
    with get_db_context() as db:
        call = db.get(TeachingCall, context['call_id'])
        if call is None:
            return
        lock_assignment(call.assignment_id, db)
        call = db.get(TeachingCall, context['call_id'])
        if call.status == 'running':
            call.context = copy.deepcopy(context)
            call.status = status
            call.completed_at = int(time.time())
            db.commit()


async def observe_formal_response(response, context):
    from starlette.responses import StreamingResponse

    if not isinstance(response, StreamingResponse):
        if isinstance(response, dict):
            context['response'] = copy.deepcopy(response)
            context['generation_status'] = 'ready'
        else:
            context['generation_status'] = 'failed'
        return response

    async def observe():
        chunks = []
        status = 'failed'
        try:
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
                yield chunk
            status = 'ready'
        finally:
            context['response_stream'] = ''.join(chunks)
            context['generation_status'] = status

    return StreamingResponse(
        observe(),
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )


async def complete_formal_response(response, context):
    from starlette.responses import StreamingResponse

    if not isinstance(response, StreamingResponse):
        await run_in_threadpool(finish_formal, context, context.get('generation_status', 'failed'))
        return response

    async def completed_stream():
        try:
            async for chunk in response.body_iterator:
                yield chunk
        finally:
            await run_in_threadpool(finish_formal, context, context.get('generation_status', 'failed'))

    return StreamingResponse(
        completed_stream(),
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )


def frozen_evidence(session_id, db):
    from open_webui.models.teaching_trials import FrozenTeachingEvidence

    calls = (
        db.query(TeachingCall).filter_by(session_id=session_id, status='ready').order_by(TeachingCall.sequence).all()
    )
    revision_ids = {call.revision_id for call in calls}
    revisions = (
        db.query(AssignmentAiRevision).filter(AssignmentAiRevision.id.in_(revision_ids)).all() if revision_ids else []
    )
    return FrozenTeachingEvidence.model_validate(
        {
            'schema_version': '2026-11-07.1',
            'revisions': [
                {k: copy.deepcopy(getattr(r, k)) for k in ('id', 'revision', 'config', 'change_summary', 'created_at')}
                for r in revisions
            ],
            'calls': [
                {
                    k: copy.deepcopy(getattr(c, k))
                    for k in ('id', 'revision_id', 'status', 'sequence', 'context', 'created_at', 'completed_at')
                }
                for c in calls
            ],
        }
    ).model_dump(exclude_none=True)


async def execute(request, user, config, context, messages, stream=False):
    # Configuration was captured by an authorized adapter. An internal retry
    # keeps that snapshot; safety revocation and routing validity still apply.
    await validate_binding(request, user, config, check_execution=False)
    install_binding(request, config, context)
    from open_webui.services.education.ai_steps import call_captured_model

    return await call_captured_model(request, user, context['purpose'], config, messages, stream=stream)


async def execute_first_read(request, user, config, context, dialogue):
    from open_webui.models.teaching_trials import TeachingTextFeedback
    from open_webui.services.education.revision_reading import PURPOSES

    stage = context['purpose']
    context['output_contract'] = 'markdown-v1'
    messages = [
        {
            'role': 'system',
            'content': system_context(config)
            + material_rules(context.get('materials'))
            + '\n'
            + PURPOSES[stage]
            + '\n直接输出面向学生的反馈正文，可使用 Markdown 排版；无需为平台包裹 JSON 字段。',
        },
        {
            'role': 'user',
            'content': json.dumps(
                {
                    '当前保存稿': context['source_text'],
                    '相关讨论': [
                        {'role': m['role'], 'content': m.get('content') or ''}
                        for m in dialogue
                        if m.get('role') in ('user', 'assistant')
                    ],
                },
                ensure_ascii=False,
            ) + material_context(context.get('materials')),
        },
    ]
    response = await execute(request, user, config, context, messages)
    choice = (response.get('choices') or [{}])[0]
    raw = (choice.get('message') or {}).get('content')
    output = {
        'raw': raw,
        'usage': response.get('usage'),
        'provider_id': response.get('id'),
        'finish_reason': choice.get('finish_reason'),
        'valid': False,
    }
    context.setdefault('outputs', []).append(output)
    if choice.get('finish_reason') in ('length', 'content_filter', 'tool_calls', 'function_call'):
        context['error_code'] = 'incomplete_response'
        raise ValueError('Teaching model did not complete a visible reply')
    if not isinstance(raw, str) or not raw.strip():
        context['error_code'] = 'empty_response'
        raise ValueError('Teaching model returned no visible reply')
    # Preserve the full response verbatim; no JSON repair, extraction or quote rewriting.
    feedback = TeachingTextFeedback(overview=raw)
    output['valid'] = True
    return feedback.model_dump()


async def formal_first_read(request, user, session, assignment, form, db, dialogue):
    from sqlalchemy import func

    from open_webui.models.education_types import RevisionReading
    from open_webui.services.education.reading_conversation import append_reading_message
    from open_webui.services.education.revision_reading import serialize_reading

    # Existing successful reads deduplicate by full effective configuration and input.
    assignment = await run_in_threadpool(lock_assignment, assignment.id, db)
    config = assignment_config(assignment, db)
    from open_webui.services.education.writing_access import ensure_writing_session_writable

    ensure_writing_session_writable(session, db)
    note = db.get(Note, session.note_id)
    source = (
        session.draft_baseline_text
        if form.purpose == 'first_read'
        else ((note.data or {}).get('content') or {}).get('md', '')
    )
    # Initial reading remains the initial reading after it becomes a chat message.
    relevant_dialogue = [] if form.purpose == 'first_read' else saved_dialogue(session, db)
    request_key = fingerprint([config_fingerprint(config), form.purpose, source, snapshot_materials(session.id, db), relevant_dialogue])
    old = db.query(TeachingCall).filter_by(session_id=session.id, request_key=request_key).first()
    if old and old.status in ('ready', 'running'):
        reading = db.get(RevisionReading, old.id)
        if reading:
            result = serialize_reading(reading)
            db.commit()
            return result
    # A deliberate retry after failure is a new call; never overwrite failed evidence.
    if old:
        request_key += ':' + str(uuid.uuid4())
    await validate_binding(request, user, config)
    config, context = capture_formal(session, request_key, form.purpose, db, user=user)
    reading = RevisionReading(
        id=context['call_id'],
        writing_session_id=session.id,
        sequence_no=(
            db.query(func.max(RevisionReading.sequence_no)).filter_by(writing_session_id=session.id).scalar() or 0
        )
        + 1,
        purpose=form.purpose,
        source_hash=request_key,
        source_version_id=context['source_version_id'],
        source_text=context['source_text'],
        context=copy.deepcopy(context),
        status='running',
        model_id=config['ai']['model_id'],
        thinking=context['actual_thinking'],
        created_at=context['called_at'],
    )
    db.add(reading)
    db.commit()
    from open_webui.services.education.revision_reading import install_reading_retry_handler
    install_reading_retry_handler(request, reading.id, context)
    feedback = None
    try:
        feedback = await execute_first_read(request, user, config, context, relevant_dialogue)
        context['status'] = 'ready'
    except Exception as error:
        context['status'] = 'failed'
        context['error_type'] = type(error).__name__
    await run_in_threadpool(lock_assignment, assignment.id, db)
    reading = db.get(RevisionReading, context['call_id'])
    call = db.get(TeachingCall, context['call_id'])
    if reading and call and call.status == 'running':
        call.context = copy.deepcopy(context)
        call.status = context['status']
        call.completed_at = int(time.time())
        reading.context = copy.deepcopy(context)
        reading.status = context['status']
        reading.feedback = feedback
        reading.completed_at = call.completed_at
        if feedback:
            # Submission freezes independently; no writes to frozen submissions here.
            append_reading_message(db, session.id, assignment, reading)
        db.commit()
    return serialize_reading(reading) if reading else {'status': 'failed', 'id': context['call_id']}
