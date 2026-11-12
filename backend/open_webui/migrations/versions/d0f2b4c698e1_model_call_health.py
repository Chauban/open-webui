"""Record model invocation outcomes and transport attempts without content."""

import sqlalchemy as sa
from alembic import op

revision = 'd0f2b4c698e1'
down_revision = 'c9e1a3b587d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'model_call',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=True),
        sa.Column('started_at', sa.BigInteger(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('fallback_used', sa.Boolean(), nullable=False),
        sa.CheckConstraint("outcome IN ('success','failed','cancelled')", name='model_call_outcome'),
    )
    op.create_index('ix_model_call_started_model', 'model_call', ['started_at', 'model_id'])
    op.create_table(
        'model_call_attempt',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('call_id', sa.Text(), sa.ForeignKey('model_call.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('route', sa.Text(), nullable=False),
        sa.Column('started_at', sa.BigInteger(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('fallback', sa.Boolean(), nullable=False),
        sa.CheckConstraint("outcome IN ('success','failed','cancelled')", name='model_attempt_outcome'),
    )
    op.create_index('ix_model_call_attempt_call', 'model_call_attempt', ['call_id'])
    op.create_index('ix_model_call_attempt_started', 'model_call_attempt', ['started_at'])


def downgrade():
    op.drop_table('model_call_attempt')
    op.drop_table('model_call')
