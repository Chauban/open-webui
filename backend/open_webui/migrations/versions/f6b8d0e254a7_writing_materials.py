"""Retain original imports and separately addressable reading evidence."""

import sqlalchemy as sa
from alembic import op
from open_webui.internal.db import JSONField

revision = 'f6b8d0e254a7'
down_revision = 'e5a7c9d143f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'writing_material',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column(
            'writing_session_id', sa.Text(), sa.ForeignKey('writing_session.id', ondelete='CASCADE'), nullable=False
        ),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('bundle_path', sa.Text(), nullable=False),
        sa.Column('data', JSONField(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('confirmed_at', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_writing_material_writing_session_id', 'writing_material', ['writing_session_id'])


def downgrade():
    op.drop_table('writing_material')
