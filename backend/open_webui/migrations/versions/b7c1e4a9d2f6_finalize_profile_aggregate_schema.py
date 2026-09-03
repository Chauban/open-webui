"""education: finalize profile aggregate and event-time schema

Revision ID: b7c1e4a9d2f6
Revises: a4d8f2c6b1e9
Create Date: 2026-09-03 13:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c1e4a9d2f6"
down_revision: Union[str, Sequence[str], None] = "a4d8f2c6b1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty_education_evidence_data(connection) -> None:
    table_names = set(sa.inspect(connection).get_table_names())
    for table_name in (
        "student_profile_aggregate_projection",
        "student_profile_rollup_projection",
        "profile_projection_outbox",
        "profile_metric_projection",
        "profile_projection_run",
        "profile_algorithm_release",
        "profile_evidence_snapshot",
        "submission_review_event",
        "submission_review",
        "submission",
        "micro_reflection",
        "analysis_result",
        "editor_operation",
        "provenance_segment",
        "writing_version",
    ):
        if table_name not in table_names:
            continue
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Final profile schema is intentionally incompatible; clear education "
                "development data before upgrading."
            )


def _create_aggregate_table() -> None:
    op.create_table(
        "student_profile_aggregate_projection",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("scope_kind", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column("aggregate_revision", sa.BigInteger(), nullable=False),
        sa.Column("projection_count", sa.BigInteger(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("output_hash", sa.Text(), nullable=False),
        sa.Column("aggregate_json", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["metric_version"], ["profile_algorithm_release.metric_version"]
        ),
        sa.ForeignKeyConstraint(["run_id"], ["profile_projection_run.id"]),
        sa.UniqueConstraint(
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "input_hash",
            name="student_profile_aggregate_identity_idx",
        ),
        sa.UniqueConstraint(
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "aggregate_revision",
            name="student_profile_aggregate_revision_idx",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('global', 'classroom')",
            name="student_profile_aggregate_scope_check",
        ),
        sa.CheckConstraint(
            "length(input_hash) = 64 AND length(output_hash) = 64",
            name="student_profile_aggregate_hash_check",
        ),
        sa.CheckConstraint(
            "aggregate_revision >= 1",
            name="student_profile_aggregate_revision_check",
        ),
    )
    op.create_index(
        "student_profile_aggregate_latest_idx",
        "student_profile_aggregate_projection",
        [
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "aggregate_revision",
        ],
    )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())
    editor_columns = {
        column["name"] for column in inspector.get_columns("editor_operation")
    }
    analysis_columns = {
        column["name"]: column
        for column in inspector.get_columns("analysis_result")
    }
    analysis_foreign_keys = {
        tuple(item["constrained_columns"])
        for item in inspector.get_foreign_keys("analysis_result")
    }
    analysis_unique_constraints = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("analysis_result")
    }
    needs_change = (
        "occurred_at_ms" not in editor_columns
        or "client_sequence" not in editor_columns
        or analysis_columns["submission_id"]["nullable"]
        or ("submission_id",) not in analysis_foreign_keys
        or (
            "writing_session_id",
            "submission_id",
            "result_type",
        )
        not in analysis_unique_constraints
        or "student_profile_aggregate_projection" not in table_names
        or "student_profile_rollup_projection" in table_names
        or "profile_projection_outbox" in table_names
    )
    if not needs_change:
        return

    _require_empty_education_evidence_data(connection)

    if "student_profile_rollup_projection" in table_names:
        op.drop_table("student_profile_rollup_projection")
    if "profile_projection_outbox" in table_names:
        op.drop_table("profile_projection_outbox")

    if "occurred_at_ms" not in editor_columns or "client_sequence" not in editor_columns:
        with op.batch_alter_table("editor_operation") as batch:
            if "occurred_at_ms" not in editor_columns:
                batch.add_column(
                    sa.Column("occurred_at_ms", sa.BigInteger(), nullable=False)
                )
            if "client_sequence" not in editor_columns:
                batch.add_column(
                    sa.Column("client_sequence", sa.BigInteger(), nullable=False)
                )
            batch.create_check_constraint(
                "editor_operation_occurred_at_check", "occurred_at_ms >= 0"
            )
            batch.create_check_constraint(
                "editor_operation_client_sequence_check", "client_sequence >= 0"
            )
            batch.create_index(
                "editor_operation_session_occurred_idx",
                ["writing_session_id", "occurred_at_ms", "client_sequence"],
            )

    needs_analysis_rebuild = (
        analysis_columns["submission_id"]["nullable"]
        or ("submission_id",) not in analysis_foreign_keys
        or (
            "writing_session_id",
            "submission_id",
            "result_type",
        )
        not in analysis_unique_constraints
    )
    if needs_analysis_rebuild:
        with op.batch_alter_table("analysis_result") as batch:
            if analysis_columns["submission_id"]["nullable"]:
                batch.alter_column(
                    "submission_id", existing_type=sa.Text(), nullable=False
                )
            if ("submission_id",) not in analysis_foreign_keys:
                batch.create_foreign_key(
                    "analysis_result_submission_fk",
                    "submission",
                    ["submission_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
            if (
                "writing_session_id",
                "submission_id",
                "result_type",
            ) not in analysis_unique_constraints:
                batch.create_unique_constraint(
                    "analysis_result_scope_type_idx",
                    ["writing_session_id", "submission_id", "result_type"],
                )

    if "student_profile_aggregate_projection" not in table_names:
        _create_aggregate_table()


def downgrade() -> None:
    raise RuntimeError("The finalized profile schema is intentionally forward-only.")
