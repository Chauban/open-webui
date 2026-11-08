"""Private comparison workbenches and retained teaching plans."""

import sqlalchemy as sa
from alembic import op
from open_webui.internal.db import JSONField

revision = 'c3e5f7a921d4'
down_revision = 'b2d4f6a810c3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'teaching_workbench',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner_id', sa.Text(), nullable=False),
        sa.Column('preparation_id', sa.Text(), nullable=False),
        sa.Column('seed_trial_id', sa.Text(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('payload', JSONField(), nullable=False),
        sa.UniqueConstraint('owner_id', 'preparation_id', 'seed_trial_id', name='teaching_workbench_source_unique'),
    )
    op.create_table(
        'teaching_comparison',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner_id', sa.Text(), nullable=False),
        sa.Column('workbench_id', sa.Text(), nullable=False),
        sa.Column('request_key', sa.Text(), nullable=False),
        sa.Column('request_hash', sa.Text(), nullable=False),
        sa.Column('payload', JSONField(), nullable=False),
        sa.Column('trial_ids', JSONField(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('workbench_id', 'request_key', name='teaching_comparison_request_unique'),
    )
    op.create_table(
        'saved_teaching_plan',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner_id', sa.Text(), nullable=False),
        sa.Column('trial_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('config', JSONField(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('owner_id', 'trial_id', name='saved_teaching_plan_source_unique'),
    )


def downgrade():
    op.drop_table('saved_teaching_plan')
    op.drop_table('teaching_comparison')
    op.drop_table('teaching_workbench')
