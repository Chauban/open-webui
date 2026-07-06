"""make writing_session chat_id nullable

Revision ID: d4f5e6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "d4f5e6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"]: column for column in inspect(bind).get_columns("writing_session")}
    chat_id = columns.get("chat_id")

    if chat_id and not chat_id.get("nullable", True):
        with op.batch_alter_table("writing_session", recreate="always") as batch_op:
            batch_op.alter_column(
                "chat_id",
                existing_type=sa.Text(),
                nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"]: column for column in inspect(bind).get_columns("writing_session")}
    chat_id = columns.get("chat_id")

    if chat_id and chat_id.get("nullable", False):
        with op.batch_alter_table("writing_session", recreate="always") as batch_op:
            batch_op.alter_column(
                "chat_id",
                existing_type=sa.Text(),
                nullable=False,
            )
