"""Separate photo transcription from reference image reading."""

import sqlalchemy as sa
from alembic import op

revision = 'b8d0f2a476c9'
down_revision = 'a7c9e1f365b8'
branch_labels = None
depends_on = None

config = sa.table('config', sa.column('key', sa.Text), sa.column('value', sa.JSON))


def upgrade():
    op.add_column(
        'assignment', sa.Column('photo_transcription_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    connection = op.get_bind()
    policy = connection.execute(sa.select(config.c.value).where(config.c.key == 'education.ai_steps')).scalar()
    if policy is not None:
        connection.execute(
            config.update()
            .where(config.c.key == 'education.ai_steps')
            .values(value={**policy, 'photo_transcription': {'model': None, 'thinking': 'off'}})
        )


def downgrade():
    connection = op.get_bind()
    policy = connection.execute(sa.select(config.c.value).where(config.c.key == 'education.ai_steps')).scalar()
    if policy is not None:
        connection.execute(
            config.update()
            .where(config.c.key == 'education.ai_steps')
            .values(value={key: value for key, value in policy.items() if key != 'photo_transcription'})
        )
    op.drop_column('assignment', 'photo_transcription_enabled')
