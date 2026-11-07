import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from sqlalchemy import MetaData, Table, create_engine, text
from open_webui.test.util.database import migration_database_at, _run_migrations


def test_populated_upgrade_preserves_facts_authorizes_existing_types_and_keeps_return_off():
    """Runs on SQLite and the dedicated PostgreSQL service via TEST_DATABASE_URL."""
    with migration_database_at('c6e8a0b2d4f7') as url:
        engine = create_engine(url)
        metadata = MetaData()
        assignment = Table('assignment', metadata, autoload_with=engine)
        submission = Table('submission', metadata, autoload_with=engine)
        config = Table('config', metadata, autoload_with=engine)
        historic = '{"coaching":{"task_prompt":"actual old prompt"},"revision_items":{"status":"ready","items":[]}}'
        with engine.begin() as connection:
            connection.execute(
                assignment.insert(),
                dict(
                    id='existing',
                    title='Old review',
                    teacher_id='teacher-old',
                    classroom_id='class-old',
                    due_at=2000000000,
                    score_max=100,
                    coaching_style='socratic',
                    task_mode='revise_draft',
                    challenge_enabled=False,
                    challenge_rounds=3,
                    challenge_focus_keys='[]',
                    reflection_questions='[]',
                    rubric_schema='{"criteria":[{"key":"one","label":"old rubric","max_score":100}]}',
                    model_params='{}',
                    created_at=1,
                    updated_at=1,
                ),
            )
            connection.execute(
                submission.insert(),
                dict(
                    id='submitted',
                    assignment_id='existing',
                    student_id='student-old',
                    writing_session_id='session-old',
                    final_version_id='version-old',
                    stats_json=historic,
                    micro_reflection_id='reflection-old',
                    submitted_at=2,
                    round_no=1,
                    is_current=1,
                ),
            )
            connection.execute(
                config.insert(),
                [
                    dict(key='education.enable_return', value=False, updated_at=1),
                    dict(
                        key='education.task_prompts',
                        value={'revise_draft': 'Existing literature standards【第一次通读】old checklist instructions'},
                        updated_at=1,
                    ),
                ],
            )
        _run_migrations(url)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT stats_json FROM submission WHERE id='submitted'")).scalar() == historic
            )
            row = connection.execute(
                text("SELECT task_mode,scoring_mode,teaching_config FROM assignment WHERE id='existing'")
            ).one()
            assert row.task_mode == 'revise_draft' and row.scoring_mode == 'dimensions'
            snapshot = json.loads(row.teaching_config)
            assert snapshot['standards'] == 'Existing literature standards'
            assert snapshot['version'] == 1
            access = connection.execute(
                text(
                    "SELECT from_scratch,revise_draft,revise_argument,default_task_mode FROM teacher_task_access WHERE user_id='teacher-old'"
                )
            ).one()
            assert bool(access.from_scratch) and bool(access.revise_draft) and not access.revise_argument
            assert access.default_task_mode == 'revise_draft'
            value = connection.execute(config.select().where(config.c.key == 'education.enable_return')).one().value
            assert value is False
        engine.dispose()
