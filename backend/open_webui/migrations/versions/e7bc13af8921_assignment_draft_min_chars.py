"""Configure the minimum first draft length per assignment."""
from alembic import op
import sqlalchemy as sa

revision = 'e7bc13af8921'
down_revision = 'd0f2b4c698e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assignment', sa.Column('draft_min_chars', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('assignment', 'draft_min_chars')
