"""education: pre-submission challenge rounds

Revision ID: a9f4c2e7b3d1
Revises: e4c7a1d9b3f5
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9f4c2e7b3d1"
down_revision: Union[str, Sequence[str], None] = "e4c7a1d9b3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assignment",
        sa.Column(
            "challenge_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "assignment",
        sa.Column(
            "challenge_rounds",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "assignment",
        sa.Column(
            "challenge_focus_keys",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )

    op.create_table(
        "challenge_session",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("submission_round_no", sa.Integer(), nullable=False),
        sa.Column("source_version_id", sa.Text(), nullable=False),
        sa.Column("focus_keys", sa.JSON(), nullable=False),
        sa.Column("planned_rounds", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("closing_summary_json", sa.JSON(), nullable=True),
        sa.Column("checklist_state_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["writing_session_id"], ["writing_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "writing_session_id",
            "submission_round_no",
            name="challenge_session_round_idx",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'skipped')",
            name="challenge_session_status_check",
        ),
    )
    op.create_index(
        "challenge_session_student_idx",
        "challenge_session",
        ["assignment_id", "student_id"],
    )

    op.create_table(
        "challenge_turn",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("challenge_session_id", sa.Text(), nullable=False),
        sa.Column("turn_no", sa.Integer(), nullable=False),
        sa.Column("focus_key", sa.Text(), nullable=False),
        sa.Column("challenge_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["challenge_session_id"], ["challenge_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "challenge_session_id", "turn_no", name="challenge_turn_order_idx"
        ),
    )


def downgrade() -> None:
    op.drop_table("challenge_turn")
    op.drop_index("challenge_session_student_idx", table_name="challenge_session")
    op.drop_table("challenge_session")
    op.drop_column("assignment", "challenge_focus_keys")
    op.drop_column("assignment", "challenge_rounds")
    op.drop_column("assignment", "challenge_enabled")
