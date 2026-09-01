"""education: add growth goals and teacher notes

Revision ID: e2a8c5d7f1b3
Revises: d1f7a9c4e6b2
Create Date: 2026-09-01 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2a8c5d7f1b3"
down_revision: Union[str, Sequence[str], None] = "d1f7a9c4e6b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_growth_goal",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("classroom_id", sa.Text(), nullable=True),
        sa.Column("assignment_id", sa.Text(), nullable=True),
        sa.Column("goal_text", sa.Text(), nullable=False),
        sa.Column("target_at", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "student_growth_goal_student_status_idx",
        "student_growth_goal",
        ["student_id", "status", "updated_at"],
    )
    op.create_table(
        "teacher_student_note",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("teacher_id", sa.Text(), nullable=False),
        sa.Column("classroom_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "teacher_student_note_scope_observed_idx",
        "teacher_student_note",
        ["teacher_id", "classroom_id", "student_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "teacher_student_note_scope_observed_idx",
        table_name="teacher_student_note",
    )
    op.drop_table("teacher_student_note")
    op.drop_index(
        "student_growth_goal_student_status_idx",
        table_name="student_growth_goal",
    )
    op.drop_table("student_growth_goal")
