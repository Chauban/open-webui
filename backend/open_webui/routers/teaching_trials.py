"""Teacher-only preparation and trial API; imported after education dependencies."""

from fastapi import APIRouter, Depends, HTTPException, Request
from open_webui.internal.db import get_session
from open_webui.models.config import Config
from open_webui.models.teaching_comparisons import (
    AdoptPlan,
    OpenWorkbench,
    RunComparison,
    SavedTeachingPlan,
    SavePlan,
    SaveWorkbench,
    TeachingComparison,
)
from open_webui.models.teaching_trials import (
    AdoptRevision,
    AdoptTrial,
    AssignmentAiRevision,
    PreparationCreate,
    PreparationUpdate,
    PublishPreparation,
    TeachingModelPolicy,
    TeachingPreparation,
    TeachingTrialSession,
    TrialAction,
    TrialCreate,
)
from open_webui.routers.education import (
    _ensure_teacher_identity,
    require_owned_writing_session,
    require_teacher_assignment,
)
from open_webui.services.education import teaching_comparisons as comparisons
from open_webui.services.education import teaching_preparations as preparations
from open_webui.services.education import teaching_trials as trials
from open_webui.services.education.ai_steps import available_models, get_ai_step_policy
from open_webui.services.education.teaching_runtime import model_policy, validate_binding
from open_webui.utils.auth import get_admin_user, get_verified_user
from sqlalchemy.orm import Session

router = APIRouter()


@router.get('/writing-sessions/{session_id}/teaching-summary')
def teaching_summary(session=Depends(require_owned_writing_session), db: Session = Depends(get_session)):
    from open_webui.models.education import Education
    from open_webui.services.education.teaching_runtime import assignment_config

    assignment = Education.get_assignment_by_id(session.assignment_id, db=db)
    if not assignment or assignment.task_mode != 'revise_argument':
        return None
    config = assignment_config(assignment, db)
    return {
        'id': config['ai']['model_id'],
        'name': config['ai']['model_id'],
        'owned_by': 'openai',
        'revision': config['ai_revision'],
        'change_summary': config['change_summary'],
        'thinking': config['ai']['thinking'],
        'info': {'meta': {'capabilities': config['binding']['capabilities']}},
    }


async def teacher(user=Depends(get_verified_user)):
    await _ensure_teacher_identity(user)
    return user


@router.get('/teacher/teaching-models')
async def teaching_models(request: Request, user=Depends(teacher)):
    policy = await model_policy()
    models = await available_models(request, user)
    return {
        'policy': policy.model_dump(),
        'recommended_thinking': (await get_ai_step_policy()).coaching_chat.default,
        'models': [
            {
                'id': model_id,
                'name': models[model_id].get('name', model_id),
                'thinking_support': models[model_id].get('thinking_support') or {},
                'capabilities': ((models[model_id].get('info') or {}).get('meta') or {}).get('capabilities') or {},
            }
            for model_id in policy.model_ids
            if model_id in models
        ],
    }


@router.put('/admin/teaching-models')
async def set_teaching_models(request: Request, form: TeachingModelPolicy, user=Depends(get_admin_user)):
    models = await available_models(request, user)
    if any(
        mid not in models
        or models[mid].get('pipe')
        or models[mid].get('pipeline')
        or models[mid].get('owned_by') == 'arena'
        for mid in form.model_ids
    ):
        raise HTTPException(400, 'Choose available non-arena teaching models')
    await Config.upsert({'education.teaching_models': form.model_dump()})
    return form


@router.get('/teacher/teaching-preparations')
def list_preparations(user=Depends(teacher), db: Session = Depends(get_session)):
    return [
        preparations.serialize_preparation(row)
        for row in db.query(TeachingPreparation)
        .filter_by(owner_id=user.id)
        .order_by(TeachingPreparation.updated_at.desc())
        .all()
    ]


@router.post('/teacher/teaching-preparations')
def create_preparation(form: PreparationCreate, user=Depends(teacher), db: Session = Depends(get_session)):
    return preparations.create_preparation(user, form, db)


@router.get('/teacher/teaching-preparations/{preparation_id}')
async def get_preparation(
    preparation_id: str, request: Request, user=Depends(teacher), db: Session = Depends(get_session)
):
    row = preparations.owned(TeachingPreparation, preparation_id, user, db)
    result = preparations.serialize_preparation(row)
    try:
        config = await preparations.resolve_preparation(request, user, row, db)
        await validate_binding(request, user, config)
        result['coverage'] = preparations.coverage(row, config, db)
    except HTTPException as error:
        result['coverage'] = {'stages': [], 'unavailable': error.detail}
    result['trials'] = [
        {'id': trial.id, 'created_at': trial.created_at, 'sequence': trial.sequence}
        for trial in db.query(TeachingTrialSession).filter_by(preparation_id=row.id, owner_id=user.id).all()
    ]
    return result


@router.put('/teacher/teaching-preparations/{preparation_id}')
def save_preparation(
    preparation_id: str, form: PreparationUpdate, user=Depends(teacher), db: Session = Depends(get_session)
):
    return preparations.save_preparation(user, preparation_id, form, db)


@router.delete('/teacher/teaching-preparations/{preparation_id}')
def delete_preparation(
    preparation_id: str, expected_revision: int, user=Depends(teacher), db: Session = Depends(get_session)
):
    row = preparations.owned(TeachingPreparation, preparation_id, user, db, lock=True)
    preparations.check_revision(row, expected_revision)
    if db.query(TeachingTrialSession).filter_by(preparation_id=row.id).first():
        raise HTTPException(409, 'Preparations with trial evidence must be retained')
    db.delete(row)
    db.commit()
    return {'deleted': True}


@router.post('/teacher/teaching-preparations/{preparation_id}/publish')
async def publish_preparation(
    preparation_id: str,
    form: PublishPreparation,
    request: Request,
    user=Depends(teacher),
    db: Session = Depends(get_session),
):
    return await preparations.publish(request, user, preparation_id, form, db)


@router.post('/teacher/teaching-preparations/{preparation_id}/adopt')
def adopt_trial(preparation_id: str, form: AdoptTrial, user=Depends(teacher), db: Session = Depends(get_session)):
    return preparations.adopt(user, preparation_id, form, db)


@router.get('/assignments/{assignment_id}/ai-revisions')
def ai_revisions(assignment=Depends(require_teacher_assignment), db: Session = Depends(get_session)):
    return [
        {k: getattr(row, k) for k in ('id', 'revision', 'config', 'change_summary', 'created_at', 'evidence')}
        for row in db.query(AssignmentAiRevision)
        .filter_by(assignment_id=assignment.id)
        .order_by(AssignmentAiRevision.revision.desc())
        .all()
    ]


@router.get('/assignments/{assignment_id}/teaching-trials')
def assignment_trials(
    assignment=Depends(require_teacher_assignment), user=Depends(teacher), db: Session = Depends(get_session)
):
    return trials.assignment_trial_summaries(assignment.id, user, db)


@router.post('/teacher/teaching-preparations/{preparation_id}/adopt-revision')
def adopt_revision(preparation_id: str, form: AdoptRevision, user=Depends(teacher), db: Session = Depends(get_session)):
    return preparations.adopt_revision(user, preparation_id, form, db)


@router.post('/teacher/teaching-trials')
async def create_trial(form: TrialCreate, request: Request, user=Depends(teacher), db: Session = Depends(get_session)):
    return await trials.create_trial(request, user, form, db)


@router.get('/teacher/teaching-trials/{trial_id}')
def get_trial(trial_id: str, user=Depends(teacher), db: Session = Depends(get_session)):
    return trials.serialize_trial(preparations.owned(TeachingTrialSession, trial_id, user, db), db)


@router.post('/teacher/teaching-trials/{trial_id}/actions')
async def act_trial(
    trial_id: str, form: TrialAction, request: Request, user=Depends(teacher), db: Session = Depends(get_session)
):
    return await trials.trial_action(request, user, trial_id, form, db)


@router.post('/teacher/teaching-workbenches')
def open_workbench(form: OpenWorkbench, user=Depends(teacher), db: Session = Depends(get_session)):
    return comparisons.open_work(user, form, db)


@router.put('/teacher/teaching-workbenches/{work_id}')
def save_workbench(work_id: str, form: SaveWorkbench, user=Depends(teacher), db: Session = Depends(get_session)):
    return comparisons.save_work(user, work_id, form, db)


@router.get('/teacher/teaching-workbenches/{work_id}/comparisons')
def list_comparisons(work_id: str, user=Depends(teacher), db: Session = Depends(get_session)):
    comparisons.authorized_work(user, work_id, db)
    return [
        comparisons.comparison_view(row, user, db)
        for row in db.query(TeachingComparison)
        .filter_by(workbench_id=work_id, owner_id=user.id)
        .order_by(TeachingComparison.created_at.desc())
        .all()
    ]


@router.post('/teacher/teaching-workbenches/{work_id}/comparisons')
async def run_comparison(
    work_id: str, form: RunComparison, request: Request, user=Depends(teacher), db: Session = Depends(get_session)
):
    return await comparisons.run_comparison(request, user, work_id, form, db)


@router.get('/teacher/saved-teaching-plans')
def list_saved_plans(user=Depends(teacher), db: Session = Depends(get_session)):
    return [
        comparisons.record(row)
        for row in db.query(SavedTeachingPlan)
        .filter_by(owner_id=user.id)
        .order_by(SavedTeachingPlan.created_at.desc())
        .all()
    ]


@router.post('/teacher/saved-teaching-plans')
def save_teaching_plan(form: SavePlan, user=Depends(teacher), db: Session = Depends(get_session)):
    return comparisons.save_plan(user, form, db)


@router.post('/teacher/saved-teaching-plans/{plan_id}/adopt/{preparation_id}')
async def adopt_saved_plan(
    plan_id: str,
    preparation_id: str,
    form: AdoptPlan,
    request: Request,
    user=Depends(teacher),
    db: Session = Depends(get_session),
):
    return await comparisons.adopt_plan(request, user, plan_id, preparation_id, form, db)
