"""Add private teaching preparations, trials and immutable assignment AI revisions.

No frozen student evidence is rewritten. Existing argument assignments require
an explicit, complete configuration map; absent mappings abort before DDL.
"""

import json
import os
import time
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from open_webui.internal.db import JSONField

revision = 'a1c3e5f709b2'
down_revision = 'f9a1b3c5d7e0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = (
        bind.execute(
            sa.text(
                'SELECT id, teacher_id, title, description, description_version '
                "FROM assignment WHERE task_mode='revise_argument'"
            )
        )
        .mappings()
        .all()
    )
    mapping = {}
    if existing:
        path = os.environ.get('TEACHING_AI_MIGRATION_MAP')
        if not path:
            raise RuntimeError(
                'Existing argument assignments require an explicit TEACHING_AI_MIGRATION_MAP before upgrade; '
                'no student data was changed.'
            )
        mapping = json.loads(Path(path).read_text(encoding='utf-8'))
        if set(mapping) != {row['id'] for row in existing}:
            raise RuntimeError(
                'Teaching migration mapping must cover every existing argument assignment, without extra IDs.'
            )
        from open_webui.models.teaching_trials import AiRuntimeConfig

        for row in existing:
            config = AiRuntimeConfig.model_validate(mapping[row['id']])
            if (
                config.title != row['title']
                or config.description != (row['description'] or '')
                or config.description_version != row['description_version']
            ):
                raise RuntimeError('Teaching migration mapping does not match the current assignment requirements.')
            mapping[row['id']] = config.model_dump(exclude_none=True)
    op.add_column('assignment', sa.Column('current_ai_revision_id', sa.Text(), nullable=True))
    op.create_table(
        'teaching_preparation',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner_id', sa.Text(), nullable=False),
        sa.Column('assignment_id', sa.Text()),
        sa.Column('base_config_revision', sa.Integer()),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('payload', JSONField(), nullable=False),
        sa.Column('adopted_binding', JSONField()),
        sa.Column('published', JSONField()),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('revision > 0', name='teaching_preparation_revision_positive'),
    )
    op.create_index('ix_teaching_preparation_owner_id', 'teaching_preparation', ['owner_id'])
    op.create_table(
        'assignment_ai_revision',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('assignment_id', sa.Text(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('config', JSONField(), nullable=False),
        sa.Column('author_id', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=False),
        sa.Column('preparation_id', sa.Text(), nullable=False),
        sa.Column('evidence', JSONField(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('assignment_id', 'revision', name='assignment_ai_revision_unique'),
        sa.CheckConstraint('revision > 0', name='assignment_ai_revision_positive'),
    )
    op.create_index('ix_assignment_ai_revision_assignment_id', 'assignment_ai_revision', ['assignment_id'])
    op.create_table(
        'teaching_trial_session',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner_id', sa.Text(), nullable=False),
        sa.Column('preparation_id', sa.Text(), nullable=False),
        sa.Column('config', JSONField(), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('source_trial_id', sa.Text()),
        sa.Column('source_sequence', sa.Integer()),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('state', JSONField(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_teaching_trial_session_owner_id', 'teaching_trial_session', ['owner_id'])
    op.create_index('ix_teaching_trial_session_preparation_id', 'teaching_trial_session', ['preparation_id'])
    op.create_table(
        'teaching_trial_event',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('trial_id', sa.Text(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('request_hash', sa.Text(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('state', JSONField(), nullable=False),
        sa.Column('call', JSONField()),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('trial_id', 'sequence', name='trial_event_sequence_unique'),
        sa.UniqueConstraint('trial_id', 'idempotency_key', name='trial_event_request_unique'),
    )
    op.create_index('ix_teaching_trial_event_trial_id', 'teaching_trial_event', ['trial_id'])
    op.create_table(
        'teaching_call',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('assignment_id', sa.Text(), nullable=False),
        sa.Column('revision_id', sa.Text(), nullable=False),
        sa.Column('request_key', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('context', JSONField(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('completed_at', sa.BigInteger()),
        sa.UniqueConstraint('session_id', 'request_key', name='teaching_call_request_unique'),
        sa.CheckConstraint("status IN ('running', 'ready', 'failed', 'stopped')", name='teaching_call_status_check'),
    )
    op.create_index('ix_teaching_call_session_id', 'teaching_call', ['session_id'])
    for row in existing:
        revision_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                'INSERT INTO assignment_ai_revision '
                '(id, assignment_id, revision, config, author_id, change_summary, '
                'preparation_id, evidence, created_at) '
                'VALUES (:id, :assignment, 1, :config, :author, :summary, :preparation, :evidence, :created)'
            ),
            {
                'id': revision_id,
                'assignment': row['id'],
                'config': json.dumps(mapping[row['id']], ensure_ascii=False),
                'author': row['teacher_id'],
                'summary': 'Explicit teaching configuration cutover; earlier calls retain their original evidence',
                'preparation': 'migration:a1c3e5f709b2',
                'evidence': json.dumps({'stages': [], 'event_ids': []}),
                'created': int(time.time()),
            },
        )
        bind.execute(
            sa.text('UPDATE assignment SET current_ai_revision_id=:revision WHERE id=:id'),
            {'revision': revision_id, 'id': row['id']},
        )


def downgrade():
    for name in (
        'teaching_call',
        'teaching_trial_event',
        'teaching_trial_session',
        'assignment_ai_revision',
        'teaching_preparation',
    ):
        op.drop_table(name)
    op.drop_column('assignment', 'current_ai_revision_id')
