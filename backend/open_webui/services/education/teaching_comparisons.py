"""Comparison orchestration; generation stays in the shared trial runtime."""

import copy
import time
import uuid

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from open_webui.models.teaching_comparisons import (
    SavedTeachingPlan,
    TeachingComparison,
    TeachingPlanAdoption,
    TeachingWorkbench,
    WorkInput,
)
from open_webui.models.teaching_trials import TeachingPreparation, TeachingTrialEvent, TeachingTrialSession
from open_webui.services.education.teaching_preparations import (
    authorize_preparation,
    check_revision,
    owned,
    serialize_preparation,
)
from open_webui.services.education.teaching_runtime import (
    config_fingerprint,
    execution_version,
    fingerprint,
    resolve_binding,
    validate_binding,
)
from open_webui.services.education.teaching_trials import serialize_trial


def record(row):
    return {c.name: copy.deepcopy(getattr(row, c.name)) for c in row.__table__.columns if c.name != 'owner_id'}


def authorized_work(user, work_id, db, lock=False):
    row = owned(TeachingWorkbench, work_id, user, db, lock=lock)
    prep = owned(TeachingPreparation, row.preparation_id, user, db)
    authorize_preparation(user, prep.assignment_id, db)
    return row


def open_work(user, form, db):
    prep = owned(TeachingPreparation, form.preparation_id, user, db, lock=True)
    authorize_preparation(user, prep.assignment_id, db)
    seed = owned(TeachingTrialSession, form.trial_id, user, db)
    row = db.query(TeachingWorkbench).filter_by(owner_id=user.id, preparation_id=prep.id, seed_trial_id=seed.id).first()
    if not row:
        row = TeachingWorkbench(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            preparation_id=prep.id,
            seed_trial_id=seed.id,
            revision=1,
            payload=WorkInput(
                title=seed.config['title'],
                description=seed.config['description'],
                candidates=[seed.config['ai']],
                sample=seed.state['draft'],
            ).model_dump(),
        )
        db.add(row)
    db.commit()
    return record(row)


def save_work(user, work_id, form, db):
    row = authorized_work(user, work_id, db, lock=True)
    if row.revision != form.expected_revision:
        raise HTTPException(409, 'Trial draft changed; reload before saving')
    row.payload = form.payload.model_dump()
    row.revision += 1
    db.commit()
    return record(row)


def comparison_view(row, user, db):
    return {
        **record(row),
        'trials': [serialize_trial(owned(TeachingTrialSession, tid, user, db), db) for tid in row.trial_ids],
    }


async def run_comparison(request, user, work_id, form, db):
    work = await run_in_threadpool(authorized_work, user, work_id, db, lock=True)
    digest = fingerprint(form.model_dump())
    previous = db.query(TeachingComparison).filter_by(workbench_id=work.id, request_key=form.idempotency_key).first()
    if previous:
        if previous.request_hash != digest:
            raise HTTPException(409, 'Request key already used')
        return comparison_view(previous, user, db)
    if work.revision != form.expected_revision:
        raise HTTPException(409, 'Trial draft changed; reload before running')
    payload = WorkInput.model_validate(work.payload)
    preparation = owned(TeachingPreparation, work.preparation_id, user, db)
    assignment = authorize_preparation(user, preparation.assignment_id, db)
    state = dict(
        baseline=None, draft=payload.sample, dialogue=[], previous_text='', status='draft', running_event_id=None
    )
    if form.source_trial_id:
        source = owned(TeachingTrialSession, form.source_trial_id, user, db)
        event = db.query(TeachingTrialEvent).filter_by(trial_id=source.id, sequence=form.source_sequence).first()
        if not event or event.state.get('running_event_id'):
            raise HTTPException(409, 'Choose a completed node')
        state = copy.deepcopy(event.state)
        state.update(status='active' if state['baseline'] is not None else 'draft', running_event_id=None)
        state.pop('submission_preview', None)
    configs = []
    for candidate in payload.candidates:
        if candidate.web_search:
            from open_webui.services.education.teaching_search import ensure_available

            await ensure_available()
        binding = await resolve_binding(request, user, candidate)
        config = dict(
            ai=candidate.model_dump(),
            binding=binding,
            title=payload.title,
            description=payload.description,
            description_version=assignment.description_version if assignment else 1,
            execution_version=execution_version(),
            validation_environment=fingerprint(binding),
        )
        await validate_binding(request, user, config)
        configs.append(config)
    ids = []
    for config in configs:
        tid = str(uuid.uuid4())
        ids.append(tid)
        db.add(
            TeachingTrialSession(
                id=tid,
                owner_id=user.id,
                preparation_id=work.preparation_id,
                config=config,
                fingerprint=config_fingerprint(config),
                sequence=0,
                state=copy.deepcopy(state),
                source_trial_id=form.source_trial_id,
                source_sequence=form.source_sequence,
                created_at=int(time.time()),
            )
        )
    row = TeachingComparison(
        id=str(uuid.uuid4()),
        owner_id=user.id,
        workbench_id=work.id,
        request_key=form.idempotency_key,
        request_hash=digest,
        payload=payload.model_dump(),
        trial_ids=ids,
        created_at=int(time.time()),
    )
    db.add(row)
    db.commit()
    return comparison_view(row, user, db)


def save_plan(user, form, db):
    trial = owned(TeachingTrialSession, form.trial_id, user, db, lock=True)
    prep = owned(TeachingPreparation, trial.preparation_id, user, db)
    authorize_preparation(user, prep.assignment_id, db)
    events = db.query(TeachingTrialEvent).filter_by(trial_id=trial.id).all()
    if not any(e.call and e.call.get('status') == 'ready' for e in events):
        raise HTTPException(409, 'Complete a response before retaining this plan')
    row = db.query(SavedTeachingPlan).filter_by(owner_id=user.id, trial_id=trial.id).first()
    if not row:
        row = SavedTeachingPlan(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            trial_id=trial.id,
            name=form.name,
            config=copy.deepcopy(trial.config),
            created_at=int(time.time()),
        )
        db.add(row)
    db.commit()
    return record(row)


async def adopt_plan(request, user, plan_id, preparation_id, form, db):
    plan = owned(SavedTeachingPlan, plan_id, user, db)
    row = await run_in_threadpool(owned, TeachingPreparation, preparation_id, user, db, lock=True)
    assignment = authorize_preparation(user, row.assignment_id, db)
    digest = fingerprint({'plan_id': plan_id, **form.model_dump()})
    old = db.query(TeachingPlanAdoption).filter_by(preparation_id=row.id, request_key=form.idempotency_key).first()
    if old:
        if old.request_hash != digest:
            raise HTTPException(409, 'Request key already used')
        return copy.deepcopy(old.result)
    check_revision(row, form.expected_revision)
    if assignment and assignment.config_revision != row.base_config_revision:
        raise HTTPException(409, 'Assignment changed; refresh the preparation')
    if assignment and form.include_task:
        raise HTTPException(400, 'Update assignment requirements in assignment settings')
    await validate_binding(request, user, plan.config, check_execution=False)
    payload = copy.deepcopy(row.payload)
    payload['ai'] = copy.deepcopy(plan.config['ai'])
    if form.include_task:
        payload['assignment'].update(title=plan.config['title'], description=plan.config['description'])
    row.payload = payload
    row.adopted_binding = copy.deepcopy(plan.config['binding'])
    row.revision += 1
    row.updated_at = int(time.time())
    result = serialize_preparation(row)
    db.add(
        TeachingPlanAdoption(
            id=str(uuid.uuid4()),
            preparation_id=row.id,
            request_key=form.idempotency_key,
            request_hash=digest,
            result=result,
        )
    )
    db.commit()
    return result
