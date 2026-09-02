"""education: version profile snapshots and audit teacher notes

Revision ID: f3b9d6e8a2c4
Revises: e2a8c5d7f1b3
Create Date: 2026-09-01 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b9d6e8a2c4"
down_revision: Union[str, Sequence[str], None] = "e2a8c5d7f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty_profile_data() -> None:
    connection = op.get_bind()
    snapshot_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM student_profile_snapshot")
    ).scalar_one()
    if snapshot_count:
        raise RuntimeError(
            "Profile snapshot schema changed; clear education profile data before upgrading."
        )


def _create_snapshot_table() -> None:
    op.create_table(
        "student_profile_snapshot",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("round_no", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.BigInteger(), nullable=False),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "submission_id",
            "metric_version",
            name="student_profile_snapshot_submission_metric_idx",
        ),
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


def upgrade() -> None:
    _require_empty_profile_data()
    op.drop_index(
        "student_profile_snapshot_assignment_round_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_index(
        "student_profile_snapshot_student_metric_created_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_table("student_profile_snapshot")
    _create_snapshot_table()

    op.add_column(
        "teacher_student_note",
        sa.Column("edited_at", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "teacher_student_note",
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
    )
    op.create_table(
        "teacher_student_note_revision",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("note_id", sa.Text(), nullable=False),
        sa.Column("teacher_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "teacher_student_note_revision_note_created_idx",
        "teacher_student_note_revision",
        ["note_id", "created_at"],
    )


def downgrade() -> None:
    _require_empty_profile_data()
    op.drop_index(
        "teacher_student_note_revision_note_created_idx",
        table_name="teacher_student_note_revision",
    )
    op.drop_table("teacher_student_note_revision")
    op.drop_column("teacher_student_note", "deleted_at")
    op.drop_column("teacher_student_note", "edited_at")
    op.drop_index(
        "student_profile_snapshot_assignment_round_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_index(
        "student_profile_snapshot_student_metric_created_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_table("student_profile_snapshot")
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
