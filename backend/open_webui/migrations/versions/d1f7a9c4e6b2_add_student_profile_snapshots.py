"""education: add versioned student profile snapshots

Revision ID: d1f7a9c4e6b2
Revises: c0e6a4b8d3f2
Create Date: 2026-09-01 02:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1f7a9c4e6b2"
down_revision: Union[str, Sequence[str], None] = "c0e6a4b8d3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_profile_snapshot",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("submission_id", sa.Text(), nullable=False, unique=True),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("round_no", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.BigInteger(), nullable=False),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "student_profile_snapshot_student_metric_created_idx",
        "student_profile_snapshot",
        ["student_id", "metric_version", "submitted_at"],
    )
    op.create_index(
        "student_profile_snapshot_assignment_round_idx",
        "student_profile_snapshot",
        ["assignment_id", "round_no"],
    )


def downgrade() -> None:
    op.drop_index(
        "student_profile_snapshot_assignment_round_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_index(
        "student_profile_snapshot_student_metric_created_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_table("student_profile_snapshot")
