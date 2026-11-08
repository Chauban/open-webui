"""Isolated trial storage adapter. Never creates students, assignments or submissions."""

import copy
import json
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import update
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from open_webui.models.education import DRAFT_BASELINE_MIN_CHARS, get_db_context
from open_webui.models.teaching_trials import TeachingPreparation, TeachingTrialEvent, TeachingTrialSession
from open_webui.services.education.reading_conversation import reading_reply
from open_webui.services.education.teaching_preparations import (
    authorize_preparation,
    check_revision,
    owned,
    resolve_preparation,
)
from open_webui.services.education.teaching_runtime import (
    actual_thinking,
    build_messages,
    config_fingerprint,
    execute,
    execute_first_read,
    fingerprint,
    validate_binding,
)
from open_webui.services.education.writing_context import normalize_draft_paragraphs


def serialize_trial(row, db):
    events = db.query(TeachingTrialEvent).filter_by(trial_id=row.id).order_by(TeachingTrialEvent.sequence).all()
    return {
        **{
            k: copy.deepcopy(getattr(row, k))
            for k in (
                'id',
                'preparation_id',
                'config',
                'fingerprint',
                'sequence',
                'state',
                'source_trial_id',
                'source_sequence',
                'created_at',
            )
        },
        'events': [
            {k: copy.deepcopy(getattr(event, k)) for k in ('id', 'sequence', 'action', 'state', 'call', 'created_at')}
            for event in events
        ],
    }


def assignment_trial_summaries(assignment_id, user, db):
    from open_webui.models.teaching_trials import AssignmentAiRevision

    preparation_ids = {
        row.preparation_id for row in db.query(AssignmentAiRevision).filter_by(assignment_id=assignment_id).all()
    }
    preparation_ids.update(
        row.id for row in db.query(TeachingPreparation).filter_by(assignment_id=assignment_id, owner_id=user.id).all()
    )
    if not preparation_ids:
        return []
    rows = (
        db.query(TeachingTrialSession)
        .filter(
            TeachingTrialSession.owner_id == user.id,
            TeachingTrialSession.preparation_id.in_(preparation_ids),
        )
        .order_by(TeachingTrialSession.created_at.desc())
        .all()
    )
    return [{'id': row.id, 'created_at': row.created_at, 'model_id': row.config['ai']['model_id']} for row in rows]


async def create_trial(request, user, form, db):
    preparation = await run_in_threadpool(owned, TeachingPreparation, form.preparation_id, user, db, lock=True)
    check_revision(preparation, form.expected_revision)
    config = await resolve_preparation(request, user, preparation, db)
    await validate_binding(request, user, config)
    if not config['title'].strip() or not config['description'].strip():
        raise HTTPException(400, 'Title and assignment requirements are required for a trial')
    state = {
        'baseline': None,
        'draft': '',
        'dialogue': [],
        'previous_text': '',
        'status': 'draft',
        'running_event_id': None,
    }
    if form.reuse_sample_from_trial_id:
        source = owned(TeachingTrialSession, form.reuse_sample_from_trial_id, user, db)
        state['draft'] = source.state['draft']
    if form.source_trial_id:
        source = owned(TeachingTrialSession, form.source_trial_id, user, db)
        event = db.query(TeachingTrialEvent).filter_by(trial_id=source.id, sequence=form.source_sequence).first()
        if not event or event.state.get('running_event_id'):
            raise HTTPException(409, 'Choose a completed trial node')
        state = copy.deepcopy(event.state)
        state['status'] = 'active' if state['baseline'] is not None else 'draft'
        state['running_event_id'] = None
    trial = TeachingTrialSession(
        id=str(uuid.uuid4()),
        owner_id=user.id,
        preparation_id=preparation.id,
        config=config,
        fingerprint=config_fingerprint(config),
        sequence=0,
        state=state,
        source_trial_id=form.source_trial_id,
        source_sequence=form.source_sequence,
        created_at=int(time.time()),
    )
    db.add(trial)
    db.commit()
    return serialize_trial(trial, db)


def finish_trial(trial_id, event_id, context, reply, feedback=None):
    with get_db_context() as db:
        db.execute(update(TeachingTrialSession).where(TeachingTrialSession.id == trial_id).values(id=trial_id))
        db.expire_all()
        trial = db.get(TeachingTrialSession, trial_id)
        event = db.get(TeachingTrialEvent, event_id)
        if not trial or not event:
            return
        if trial.state.get('running_event_id') != event_id:
            return  # Explicitly stopped; a late response cannot append a message.
        state = copy.deepcopy(trial.state)
        state['running_event_id'] = None
        if context['status'] == 'ready':
            state['dialogue'].append({'role': 'assistant', 'content': reply, 'call_id': context['call_id']})
            state['previous_text'] = context['source_text']
        trial.state = state
        event.state = copy.deepcopy(state)
        event.call = {**copy.deepcopy(context), 'reply': reply, 'feedback': feedback, 'completed_at': int(time.time())}
        db.commit()


async def trial_action(request, user, trial_id, form, db):  # noqa: C901 -- explicit serialized trial state machine
    trial = await run_in_threadpool(owned, TeachingTrialSession, trial_id, user, db, lock=True)
    preparation = owned(TeachingPreparation, trial.preparation_id, user, db)
    authorize_preparation(user, preparation.assignment_id, db)
    request_hash = fingerprint(form.model_dump())
    old = db.query(TeachingTrialEvent).filter_by(trial_id=trial.id, idempotency_key=form.idempotency_key).first()
    if old:
        if old.request_hash != request_hash:
            raise HTTPException(409, 'Idempotency key was already used with different input')
        return serialize_trial(trial, db)
    if trial.sequence != form.expected_sequence:
        raise HTTPException(409, 'Trial changed; reload before continuing')
    state = copy.deepcopy(trial.state)
    if state['running_event_id'] and form.action != 'stop':
        raise HTTPException(409, 'An AI request is already running')
    if state['status'] == 'finished':
        raise HTTPException(409, 'Trial has ended; create a new trial to continue')
    stage = None
    if form.action == 'retry':
        failed = db.query(TeachingTrialEvent).filter_by(trial_id=trial.id, sequence=trial.sequence).first()
        if not failed or not failed.call or failed.call.get('status') != 'failed':
            raise HTTPException(409, 'Only the latest failed response can be retried')
        state = copy.deepcopy(failed.state)
        stage = failed.call['purpose']
    if form.action == 'confirm':
        if state['baseline'] is not None:
            raise HTTPException(409, 'First draft has already been confirmed')
        paragraphs = normalize_draft_paragraphs(form.text)
        if sum(len(''.join(p.split())) for p in paragraphs) < DRAFT_BASELINE_MIN_CHARS:
            raise HTTPException(400, 'First draft is too short')
        state.update(baseline='\n'.join(paragraphs), draft='\n'.join(paragraphs), status='active')
        stage = 'first_read'
    elif form.action == 'first_read':
        if state['baseline'] is None:
            raise HTTPException(409, 'Confirm the first draft before reading')
        stage = 'first_read'
    elif form.action == 'save':
        if state['baseline'] is None:
            raise HTTPException(409, 'Confirm the first draft before editing')
        state['draft'] = form.text
    elif form.action == 'coaching_chat':
        if state['baseline'] is None or not form.text.strip():
            raise HTTPException(400, 'Confirm the first draft and enter a message')
        stage = form.action
        state['dialogue'].append({'role': 'user', 'content': form.text})
    elif form.action == 'stop':
        running = db.get(TeachingTrialEvent, state['running_event_id']) if state['running_event_id'] else None
        if running:
            running.call = {**running.call, 'status': 'stopped', 'completed_at': int(time.time())}
        state['running_event_id'] = None
    event_id = str(uuid.uuid4())
    context = None
    if stage:
        await validate_binding(request, user, trial.config)
        state['running_event_id'] = event_id
        context = {
            'call_id': event_id,
            'config': copy.deepcopy(trial.config),
            'purpose': stage,
            'source_text': state['baseline'] if stage == 'first_read' else state['draft'],
            'previous_text': state['previous_text'] or state['baseline'],
            'dialogue': [{'role': m['role'], 'content': m['content']} for m in state['dialogue']],
            'fingerprint': trial.fingerprint,
            'sample_fingerprint': fingerprint([state['draft'], state['previous_text'], state['dialogue'], stage]),
            'status': 'running',
            'called_at': int(time.time()),
            'attempts': [],
        }
        context.update(requested_thinking=trial.config['ai']['thinking'], actual_thinking=actual_thinking(trial.config))
    trial.sequence += 1
    trial.state = state
    event = TeachingTrialEvent(
        id=event_id,
        trial_id=trial.id,
        sequence=trial.sequence,
        idempotency_key=form.idempotency_key,
        request_hash=request_hash,
        action=form.action,
        state=copy.deepcopy(state),
        call=context,
        created_at=int(time.time()),
    )
    db.add(event)
    config = copy.deepcopy(trial.config)
    db.commit()
    if not stage:
        return serialize_trial(trial, db)
    if stage == 'first_read':
        reply, feedback = '', None
        try:
            feedback = await execute_first_read(request, user, config, context, [])
            reply = reading_reply(feedback)
            context['status'] = 'ready'
        except Exception as error:
            context.update(status='failed', error_type=type(error).__name__)
        await run_in_threadpool(finish_trial, trial_id, event_id, context, reply, feedback)
        db.expire_all()
        return serialize_trial(db.get(TeachingTrialSession, trial_id), db)

    async def stream():  # noqa: C901 -- SSE parsing, cancellation and persistence share one lifetime
        reply = ''
        pending = ''
        try:
            messages = build_messages(config, stage, context['source_text'], state['dialogue'])
            response = await execute(request, user, config, context, messages, stream=True)
            if not isinstance(response, StreamingResponse):
                raise ValueError('Model did not return a streaming response')
            try:
                async for chunk in response.body_iterator:
                    pending += chunk.decode() if isinstance(chunk, bytes) else chunk
                    while '\n' in pending:
                        line, pending = pending.split('\n', 1)
                        if not line.startswith('data:') or line[5:].strip() == '[DONE]':
                            continue
                        data = json.loads(line[5:])
                        if data.get('error'):
                            raise ValueError('Model generation failed')
                        delta = ((data.get('choices') or [{}])[0].get('delta') or {}).get('content') or ''
                        reply += delta
                        if delta:
                            yield 'data: ' + json.dumps({'delta': delta}, ensure_ascii=False) + '\n\n'
                        if data.get('usage'):
                            context['usage'] = data['usage']
                        if data.get('id'):
                            context['provider_id'] = data['id']
            finally:
                if response.background:
                    await response.background()
            context['status'] = 'ready'
        except BaseException as error:
            context.update(status='failed', error_type=type(error).__name__)
            raise
        finally:
            await run_in_threadpool(finish_trial, trial_id, event_id, context, reply)
        yield 'data: ' + json.dumps({'done': True}) + '\n\n'

    return StreamingResponse(stream(), media_type='text/event-stream')
