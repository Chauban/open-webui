"""education: per-student assignment due date extension

Revision ID: e4c7a1d9b3f5
Revises: d6f2a8c4e910
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4c7a1d9b3f5"
down_revision: Union[str, Sequence[str], None] = "d6f2a8c4e910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignment_extension",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("due_at", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("granted_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id", "student_id", name="assignment_extension_identity_idx"
        ),
    )


def downgrade() -> None:
    op.drop_table("assignment_extension")
