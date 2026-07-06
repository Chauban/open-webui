"""Update writing session for assignment projects

Revision ID: 7f3c2e1a9b4d
Revises: 018012973d35
Create Date: 2026-03-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "7f3c2e1a9b4d"
down_revision = "018012973d35"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("writing_session")}

    if "folder_id" not in columns:
        op.add_column("writing_session", sa.Column("folder_id", sa.Text(), nullable=True))

    if "active_chat_id" not in columns:
        op.add_column("writing_session", sa.Column("active_chat_id", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("writing_session")}

    if "active_chat_id" in columns:
        op.drop_column("writing_session", "active_chat_id")

    if "folder_id" in columns:
        op.drop_column("writing_session", "folder_id")
