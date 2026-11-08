"""Add teacher-controlled assignment visibility."""

from alembic import op
import sqlalchemy as sa

revision = 'e5a7c9d143f6'
down_revision = 'd4f6a8b032e5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assignment', sa.Column('hidden', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('assignment', 'hidden')
