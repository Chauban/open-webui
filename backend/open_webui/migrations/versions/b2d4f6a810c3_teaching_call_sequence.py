"""Require a serialized operation sequence for assignment AI calls."""

import sqlalchemy as sa
from alembic import op

revision = 'b2d4f6a810c3'
down_revision = 'a1c3e5f709b2'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM teaching_call')).scalar():
        raise RuntimeError(
            'Unsequenced development teaching calls cannot be upgraded by guessing their order. '
            'Export and explicitly resolve this development-only data before upgrading.'
        )
    with op.batch_alter_table('teaching_call') as batch:
        batch.add_column(sa.Column('sequence', sa.Integer(), nullable=False))
        batch.create_unique_constraint('teaching_call_sequence_unique', ['session_id', 'sequence'])


def downgrade():
    with op.batch_alter_table('teaching_call') as batch:
        batch.drop_constraint('teaching_call_sequence_unique', type_='unique')
        batch.drop_column('sequence')
