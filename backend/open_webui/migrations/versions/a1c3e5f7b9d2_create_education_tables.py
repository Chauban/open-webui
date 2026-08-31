"""create education base tables

Revision ID: a1c3e5f7b9d2
Revises: 018012973d35
Create Date: 2026-08-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "018012973d35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignment",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("teacher_id", sa.Text(), nullable=False),
        sa.Column("classroom_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at", sa.BigInteger(), nullable=True),
        sa.Column("archived_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "classroom",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("teacher_id", sa.Text(), nullable=False),
        sa.Column("invite_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "classroom_member",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("classroom_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("member_role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "writing_session",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("assignment_id", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("note_id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("submitted_submission_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "writing_version",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("version_no", sa.BigInteger(), nullable=False),
        sa.Column("note_snapshot_json", sa.Text(), nullable=True),
        sa.Column("note_snapshot_text", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "provenance_segment",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("segment_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.BigInteger(), nullable=True),
        sa.Column("end_offset", sa.BigInteger(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "editor_operation",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("op_type", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.BigInteger(), nullable=True),
        sa.Column("end_offset", sa.BigInteger(), nullable=True),
        sa.Column("inserted_text", sa.Text(), nullable=True),
        sa.Column("deleted_text", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "analysis_result",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("submission_id", sa.Text(), nullable=True),
        sa.Column("result_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "micro_reflection",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("ai_help_type", sa.Text(), nullable=False),
        sa.Column("reflection_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "submission",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("final_version_id", sa.Text(), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("micro_reflection_id", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "submission_review",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("submission_id", sa.Text(), nullable=False, unique=True),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("score", sa.BigInteger(), nullable=True),
        sa.Column("overall_comment", sa.Text(), nullable=True),
        sa.Column("rubric_json", sa.Text(), nullable=True),
        sa.Column("returned_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    for table_name in (
        "submission_review",
        "submission",
        "micro_reflection",
        "analysis_result",
        "editor_operation",
        "provenance_segment",
        "writing_version",
        "writing_session",
        "classroom_member",
        "classroom",
        "assignment",
    ):
        op.drop_table(table_name)
