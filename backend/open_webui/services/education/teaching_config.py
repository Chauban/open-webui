"""Teaching configuration, permission checks and serialized assignment mutations."""

import time

from sqlalchemy import update

from open_webui.models.education import Assignment, AssignmentModel, get_db_context
from open_webui.models.education_types import (
    TeacherTaskAccess,
    TeacherTaskAccessForm,
    TeachingConfiguration,
    TeachingConfigSnapshot,
    TeachingConfigUpdate,
)
from open_webui.services.education.task_types import TASK_MODES


class EducationConflict(ValueError):
    pass


def lock_assignment(assignment_id, db):
    # A no-op UPDATE acquires a write lock on both SQLite and PostgreSQL. All
    # baseline/submit/review/config writes take it first, in the same lock order.
    db.execute(update(Assignment).where(Assignment.id == assignment_id).values(id=assignment_id))
    db.expire_all()
    row = db.get(Assignment, assignment_id)
    return AssignmentModel.model_validate(row) if row is not None else None


def teacher_access(user_id, db):
    row = db.get(TeacherTaskAccess, user_id)
    if row is None:
        # Missing authorization is closed, never silently provisioned on a GET.
        return TeacherTaskAccessForm(allowed_task_modes=[], default_task_mode=None)
    return TeacherTaskAccessForm(
        allowed_task_modes=[mode for mode in TASK_MODES if getattr(row, mode)],
        default_task_mode=row.default_task_mode,
    )


def set_teacher_access(user_id, form, db):
    row = db.get(TeacherTaskAccess, user_id)
    if row is None:
        row = TeacherTaskAccess(user_id=user_id)
        db.add(row)
    for mode in TASK_MODES:
        setattr(row, mode, mode in form.allowed_task_modes)
    row.default_task_mode = form.default_task_mode
    db.flush()


def initialize_teacher_access(user_id):
    """Called only when explicitly assigning the teacher identity, never on reads."""
    with get_db_context() as db:
        if db.get(TeacherTaskAccess, user_id) is None:
            set_teacher_access(
                user_id,
                TeacherTaskAccessForm(allowed_task_modes=['from_scratch'], default_task_mode='from_scratch'),
                db,
            )
            db.commit()


def latest_teaching_config(task_mode, db):
    row = (
        db.query(TeachingConfiguration)
        .filter_by(task_mode=task_mode)
        .order_by(TeachingConfiguration.version.desc())
        .first()
    )
    if row is None:
        raise EducationConflict('Teaching configuration is missing; run the database migration')
    return TeachingConfigSnapshot(
        **row.payload, task_mode=row.task_mode, version=row.version, created_at=row.created_at
    ).model_dump()


def publish_teaching_config(task_mode, form: TeachingConfigUpdate, db):
    # Serialize concurrent edits of the same type; the previous payload is immutable.
    db.execute(
        update(TeachingConfiguration)
        .where(
            TeachingConfiguration.task_mode == task_mode,
            TeachingConfiguration.version == form.expected_version,
        )
        .values(version=form.expected_version)
    )
    current = latest_teaching_config(task_mode, db)
    if current['version'] != form.expected_version:
        raise EducationConflict('Teaching configuration changed; reload before publishing')
    db.add(
        TeachingConfiguration(
            task_mode=task_mode,
            version=current['version'] + 1,
            payload=form.model_dump(exclude={'expected_version'}),
            created_at=int(time.time()),
        )
    )
    db.commit()
    return latest_teaching_config(task_mode, db)


def revision_system_context(assignment):
    """Explicit allowlist: no rubric, score, reflection or generic coaching style."""
    config = assignment.teaching_config
    return '\n\n'.join(
        [
            f'【教学配置】{assignment.task_mode} / v{config["version"]}',
            f'【本类型辅导提示词】\n{config["prompt"]}',
            '【本次作业信息】',
            f'标题：{assignment.title}\n{assignment.description or ""}',
        ]
    )
