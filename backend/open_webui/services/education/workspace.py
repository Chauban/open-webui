"""Initial workspace reads, after the route has checked identity and ownership.

Reads are sequential on the caller's Session. This is a bounded read assembly,
not a transaction-wide snapshot of concurrent model activity. Existing revision,
baseline and chat identifiers remain the authority for subsequent writes.
"""

from sqlalchemy import select

from open_webui.models.education import Education, WorkspaceInitialState
from open_webui.models.models import Model
from open_webui.services.education.document_workflow import pending_draft
from open_webui.services.education.task_types import is_revision


def student_teaching_summary(assignment, db, models):
    from open_webui.services.education.teaching_runtime import assignment_config

    if not assignment or assignment.task_mode != 'revise_argument':
        return None
    config = assignment_config(assignment, db)
    model_id = config['ai']['model_id']
    name = db.scalar(select(Model.name).where(Model.id == model_id))
    if not name:
        name = (models.get(model_id) or {}).get('name') or model_id
    # Only the same student-visible fields as the independent summary endpoint.
    return {
        'id': model_id,
        'name': name,
        'owned_by': 'openai',
        'revision': config['ai_revision'],
        'change_summary': config['change_summary'],
        'thinking': config['ai']['thinking'],
        'info': {'meta': {'capabilities': config['binding']['capabilities']}},
    }


def current_challenge(assignment, session, db):
    from open_webui.models.education import ChallengeSessionDetail

    round_no = Education.resolve_next_submission_round_no(assignment.id, session.owner_user_id, db=db)
    challenge = Education.get_challenge_session_for_round(session.id, round_no, db=db)
    if challenge is None:
        return None
    return ChallengeSessionDetail(session=challenge, turns=Education.get_challenge_turns(challenge.id, db=db))


def initial_workspace_state(assignment, session, db, models):
    from open_webui.services.education.revision_reading import reading_records

    revision = assignment is not None and is_revision(assignment.task_mode)
    return WorkspaceInitialState(
        teaching_summary=student_teaching_summary(assignment, db, models),
        pending_draft=pending_draft(session, db) if revision and not session.draft_baseline_at else None,
        readings=reading_records(session.id, db) if revision and session.draft_baseline_at else [],
        challenge=current_challenge(assignment, session, db)
        if assignment and assignment.challenge_enabled and not revision
        else None,
    )
