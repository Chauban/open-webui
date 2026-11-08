"""Private draft lifecycle and atomic, optimistic publication."""

import copy
import logging
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import func, update
from starlette.concurrency import run_in_threadpool

from open_webui.models.education import Assignment, AssignmentModel, Education, EducationNotification
from open_webui.models.teaching_trials import (
    AssignmentAiRevision,
    PreparationPayload,
    TeachingPreparation,
    TeachingTrialEvent,
    TeachingTrialSession,
)
from open_webui.services.education.teaching_config import latest_teaching_config, lock_assignment, teacher_access
from open_webui.services.education.teaching_runtime import (
    config_fingerprint,
    execution_version,
    fingerprint,
    resolve_binding,
)


def owned(model, row_id, user, db, lock=False):
    if lock:
        db.execute(update(model).where(model.id == row_id, model.owner_id == user.id).values(id=row_id))
        db.expire_all()
    row = db.get(model, row_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, 'Private teaching resource not found')
    return row


def check_revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, 'Preparation changed; reload before saving. Your input has not been applied')
    if row.published:
        raise HTTPException(409, 'This preparation has already been published; create a new preparation')


def authorize_preparation(user, assignment_id, db):
    from open_webui.routers.education import _ensure_assignment_access, _get_assignment_or_404

    if assignment_id:
        assignment = _get_assignment_or_404(assignment_id, db)
        _ensure_assignment_access(user, assignment, db, require_teacher=True)
        if assignment.task_mode != 'revise_argument':
            raise HTTPException(400, 'Teaching preparations support argument revision only')
        return assignment
    if user.role != 'admin' and 'revise_argument' not in teacher_access(user.id, db).allowed_task_modes:
        raise HTTPException(403, 'This assignment type is not authorized for your account')
    return None


def serialize_preparation(row):
    return {
        key: copy.deepcopy(getattr(row, key))
        for key in (
            'id',
            'assignment_id',
            'base_config_revision',
            'revision',
            'payload',
            'published',
            'created_at',
            'updated_at',
        )
    }


def preparation_payload(payload, assignment):
    if assignment is None:
        return payload.model_dump()
    # Updating AI cannot stage an alternative set of grading/deadline/requirements.
    # Keep only the authoritative assignment as preview source; publication writes AI only.
    from open_webui.models.education import AssignmentCreateForm

    fields = set(AssignmentCreateForm.model_fields) - {'classroom_ids'}
    source = assignment.model_dump(include=fields)
    source['classroom_ids'] = [assignment.classroom_id]
    return {'assignment': AssignmentCreateForm.model_validate(source).model_dump(), 'ai': payload.ai.model_dump()}


def create_preparation(user, form, db):
    assignment = authorize_preparation(user, form.assignment_id, db)
    row = TeachingPreparation(
        id=str(uuid.uuid4()),
        owner_id=user.id,
        assignment_id=form.assignment_id,
        base_config_revision=assignment.config_revision if assignment else None,
        revision=1,
        payload=preparation_payload(form.payload, assignment),
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    db.add(row)
    db.commit()
    return serialize_preparation(row)


def save_preparation(user, preparation_id, form, db):
    row = owned(TeachingPreparation, preparation_id, user, db, lock=True)
    assignment = authorize_preparation(user, row.assignment_id, db)
    if assignment and assignment.config_revision != row.base_config_revision:
        raise HTTPException(409, 'Assignment settings changed; create a preparation from the current assignment')
    check_revision(row, form.expected_revision)
    if row.payload['ai'] != form.payload.ai.model_dump():
        row.adopted_binding = None
    row.payload = preparation_payload(form.payload, assignment)
    row.revision += 1
    row.updated_at = int(time.time())
    db.commit()
    return serialize_preparation(row)


async def resolve_preparation(request, user, row, db):
    payload = PreparationPayload.model_validate(row.payload)
    if payload.ai.web_search:
        from open_webui.services.education.teaching_search import ensure_available

        await ensure_available()
    assignment = authorize_preparation(user, row.assignment_id, db)
    binding = await resolve_binding(request, user, payload.ai)
    validation_environment = fingerprint(binding)
    # Adoption copies the tested non-secret parameters, not the later defaults.
    if row.adopted_binding:
        binding = copy.deepcopy(row.adopted_binding)
    return {
        'ai': payload.ai.model_dump(),
        'binding': binding,
        'title': assignment.title if assignment else payload.assignment.title,
        'description': (assignment.description if assignment else payload.assignment.description) or '',
        'description_version': assignment.description_version if assignment else 1,
        'execution_version': execution_version(),
        'validation_environment': validation_environment,
    }


def coverage(row, config, db):
    target = config_fingerprint(config)
    sessions = db.query(TeachingTrialSession).filter_by(owner_id=row.owner_id, fingerprint=target).all()
    stages = set()
    ids = []
    for session in sessions:
        for event in db.query(TeachingTrialEvent).filter_by(trial_id=session.id).all():
            if event.call and event.call.get('status') == 'ready':
                stages.add(event.call['purpose'])
                ids.append(event.id)
    return {'fingerprint': target, 'stages': sorted(stages), 'event_ids': ids}


async def publish(request, user, preparation_id, form, db):  # noqa: C901 -- one atomic publication transaction
    initial = owned(TeachingPreparation, preparation_id, user, db)
    # Lock order is always assignment -> preparation -> session.
    if initial.assignment_id:
        await run_in_threadpool(lock_assignment, initial.assignment_id, db)
    row = await run_in_threadpool(owned, TeachingPreparation, preparation_id, user, db, lock=True)
    request_payload = form.model_dump()
    if row.published:
        if row.published['request'] != request_payload:
            raise HTTPException(409, 'Preparation has already been published with another request')
        return [Education.get_assignment_by_id(aid, db=db) for aid in row.published['assignment_ids']]
    check_revision(row, form.expected_revision)
    assignment = authorize_preparation(user, row.assignment_id, db)
    config = await resolve_preparation(request, user, row, db)
    from open_webui.services.education.teaching_runtime import validate_binding

    await validate_binding(request, user, config)
    evidence = coverage(row, config, db)
    payload = PreparationPayload.model_validate(row.payload).assignment
    now = int(time.time())
    rows = []
    notifications = []
    if assignment:
        if (
            form.expected_config_revision != assignment.config_revision
            or row.base_config_revision != assignment.config_revision
        ):
            raise HTTPException(409, 'Assignment settings changed; create a preparation from the current assignment')
        if not form.change_summary.strip():
            raise HTTPException(400, 'Describe the teaching change')
        rows = [db.get(Assignment, assignment.id)]
        rows[0].config_revision += 1
    else:
        from open_webui.routers.education import _ensure_classroom_access, _get_classroom_or_404

        classroom_ids = list(dict.fromkeys(payload.classroom_ids))
        if not classroom_ids or not payload.due_at or payload.due_at <= 0 or not payload.title.strip():
            raise HTTPException(400, 'Title, classroom and due time are required to publish')
        for classroom_id in classroom_ids:
            _ensure_classroom_access(user, _get_classroom_or_404(classroom_id, db), db, require_teacher=True)
        template = latest_teaching_config('revise_argument', db)
        for classroom_id in classroom_ids:
            item = Assignment(
                id=str(uuid.uuid4()),
                teacher_id=user.id,
                classroom_id=classroom_id,
                **payload.model_dump(exclude={'classroom_ids'}),
                teaching_config=template,
                config_revision=1,
                description_version=1,
                reflection_version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            rows.append(item)
    for item in rows:
        revision = (
            db.query(func.max(AssignmentAiRevision.revision)).filter_by(assignment_id=item.id).scalar() or 0
        ) + 1
        published = AssignmentAiRevision(
            id=str(uuid.uuid4()),
            assignment_id=item.id,
            revision=revision,
            config=copy.deepcopy(config),
            author_id=user.id,
            change_summary=form.change_summary.strip(),
            preparation_id=row.id,
            evidence=evidence,
            created_at=now,
        )
        db.add(published)
        item.current_ai_revision_id = published.id
        item.updated_at = now
        if not assignment:
            recipients = []
            for member in Education.get_classroom_members(item.classroom_id, member_role='student', db=db):
                recipients.append(member.user_id)
                db.add(
                    EducationNotification(
                        id=str(uuid.uuid4()),
                        user_id=member.user_id,
                        type='assignment_published',
                        payload_json={'assignment_id': item.id, 'assignment_title': item.title, 'due_at': item.due_at},
                        created_at=now,
                    )
                )
            notifications.append(
                (recipients, {'assignment_id': item.id, 'assignment_title': item.title, 'due_at': item.due_at})
            )
    row.published = {'request': request_payload, 'assignment_ids': [item.id for item in rows]}
    db.flush()
    result = [AssignmentModel.model_validate(item) for item in rows]
    db.commit()
    # The durable notifications and all assignments already committed together.
    # A socket outage must not turn a successful publication into a failed one.
    from open_webui.routers.education import _refresh_profile_aggregates_after_scope_change, emit_to_users

    for recipients, notification in notifications:
        if recipients:
            try:
                await emit_to_users(
                    'education:notification', {'type': 'assignment_published', 'payload': notification}, recipients
                )
            except Exception:
                logging.getLogger(__name__).exception('Could not emit a committed assignment notification')
    affected = list({uid for recipients, _ in notifications for uid in recipients})
    if affected:
        _refresh_profile_aggregates_after_scope_change(affected, db)
    return result


def adopt(user, preparation_id, form, db):
    row = owned(TeachingPreparation, preparation_id, user, db, lock=True)
    authorize_preparation(user, row.assignment_id, db)
    check_revision(row, form.expected_revision)
    trial = owned(TeachingTrialSession, form.trial_id, user, db)
    payload = copy.deepcopy(row.payload)
    payload['ai'] = copy.deepcopy(trial.config['ai'])
    row.payload = payload
    row.adopted_binding = copy.deepcopy(trial.config['binding'])
    row.revision += 1
    row.updated_at = int(time.time())
    db.commit()
    return serialize_preparation(row)


def adopt_revision(user, preparation_id, form, db):
    row = owned(TeachingPreparation, preparation_id, user, db, lock=True)
    authorize_preparation(user, row.assignment_id, db)
    check_revision(row, form.expected_revision)
    revision = db.get(AssignmentAiRevision, form.revision_id)
    if revision is None or revision.assignment_id != row.assignment_id:
        raise HTTPException(404, 'Coaching version not found in this assignment')
    row.payload = {**row.payload, 'ai': copy.deepcopy(revision.config['ai'])}
    row.adopted_binding = copy.deepcopy(revision.config['binding'])
    row.revision += 1
    row.updated_at = int(time.time())
    db.commit()
    return serialize_preparation(row)
