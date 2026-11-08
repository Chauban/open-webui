"""Durable idempotency receipts for adopting a retained plan."""

import sqlalchemy as sa
from alembic import op
from open_webui.internal.db import JSONField

revision = 'd4f6a8b032e5'
down_revision = 'c3e5f7a921d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'teaching_plan_adoption',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('preparation_id', sa.Text(), nullable=False),
        sa.Column('request_key', sa.Text(), nullable=False),
        sa.Column('request_hash', sa.Text(), nullable=False),
        sa.Column('result', JSONField(), nullable=False),
        sa.UniqueConstraint('preparation_id', 'request_key', name='teaching_plan_adoption_request_unique'),
    )


def downgrade():
    op.drop_table('teaching_plan_adoption')
