"""Let teachers explicitly enable image reading per assignment."""

import sqlalchemy as sa
from alembic import op

revision = 'a7c9e1f365b8'
down_revision = 'f6b8d0e254a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assignment', sa.Column('image_reading_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade():
    op.drop_column('assignment', 'image_reading_enabled')
