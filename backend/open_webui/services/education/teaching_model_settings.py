"""Preview and atomically replace the models used by published argument assignments."""

import time
import uuid

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from starlette.concurrency import run_in_threadpool

from open_webui.models.config import Config
from open_webui.models.education import Assignment, Classroom
from open_webui.models.teaching_trials import AssignmentAiRevision, TeachingModelPolicy
from open_webui.services.education.teaching_config import lock_assignment
from open_webui.services.education.teaching_runtime import execution_version, fingerprint, resolve_model_binding

POLICY_KEY = 'education.teaching_models'


def lock_policy(db):
    # Serialize administrator changes and teacher publications, including the first publication.
    insert = sqlite_insert if db.get_bind().dialect.name == 'sqlite' else pg_insert
    db.execute(
        insert(Config)
        .values(key=POLICY_KEY, value=TeachingModelPolicy().model_dump())
        .on_conflict_do_nothing(index_elements=[Config.key])
    )
    db.execute(update(Config).where(Config.key == POLICY_KEY).values(key=POLICY_KEY))
    db.expire_all()


def settings_snapshot(db):
    row = db.get(Config, POLICY_KEY)
    policy = TeachingModelPolicy.model_validate(row.value if row else {}).model_dump()
    published = (
        db.query(Assignment.id, Assignment.title, Classroom.name, AssignmentAiRevision)
        .join(AssignmentAiRevision, AssignmentAiRevision.id == Assignment.current_ai_revision_id)
        .outerjoin(Classroom, Classroom.id == Assignment.classroom_id)
        .filter(Assignment.task_mode == 'revise_argument')
        .order_by(Assignment.id)
        .all()
    )
    assignments = [
        dict(id=aid, title=title, classroom=name, model_id=revision.config['ai']['model_id'], revision_id=revision.id)
        for aid, title, name, revision in published
    ]
    return dict(policy=policy, assignments=assignments, snapshot=fingerprint([policy, assignments]))


async def save_settings(request, user, form, db):
    policy = TeachingModelPolicy(model_ids=form.model_ids, recommended_model_id=form.recommended_model_id)
    replacements = form.replacements
    if any(
        target == source or target not in policy.model_ids or target in replacements
        for source, target in replacements.items()
    ):
        raise HTTPException(400, 'Choose an authorized replacement model for each affected assignment.')
    bindings = {
        target: await resolve_model_binding(request, user, target, policy)
        for target in sorted(set(replacements.values()))
    }
    return await run_in_threadpool(_apply, user.id, form.expected_snapshot, policy, replacements, bindings, db)


def _apply(admin_id, expected, policy, replacements, bindings, db):
    lock_policy(db)
    snapshot = settings_snapshot(db)
    if snapshot['snapshot'] != expected:
        raise HTTPException(409, 'Teaching settings changed. Reload and review the affected assignments.')
    in_use = {item['model_id'] for item in snapshot['assignments']}
    if in_use - set(policy.model_ids) - replacements.keys() or replacements.keys() - in_use:
        raise HTTPException(400, 'Choose an authorized replacement model for each affected assignment.')
    now = int(time.time())
    for item in snapshot['assignments']:
        source = item['model_id']
        if source not in replacements:
            continue
        target = replacements[source]
        lock_assignment(item['id'], db)
        assignment = db.get(Assignment, item['id'])
        previous = db.get(AssignmentAiRevision, item['revision_id'])
        binding = bindings[target]
        summary = f'教学模型调整：{source} → {target}'
        config = {
            **previous.config,
            'ai': {**previous.config['ai'], 'model_id': target},
            'title': assignment.title,
            'description': assignment.description or '',
            'description_version': assignment.description_version,
            'binding': binding,
            'execution_version': execution_version(),
            'validation_environment': fingerprint(binding),
        }
        revision = AssignmentAiRevision(
            id=str(uuid.uuid4()),
            assignment_id=assignment.id,
            revision=previous.revision + 1,
            config=config,
            author_id=admin_id,
            change_summary=summary,
            preparation_id=previous.preparation_id,
            evidence={'source_revision_id': previous.id, 'stages': [], 'event_ids': []},
            created_at=now,
        )
        db.add(revision)
        assignment.current_ai_revision_id = revision.id
        assignment.config_revision += 1
        assignment.change_summary = summary
        assignment.updated_at = now
        db.flush()
    row = db.get(Config, POLICY_KEY)
    row.value = policy.model_dump()
    row.updated_at = now
    db.flush()
    result = settings_snapshot(db)
    db.commit()
    return result
