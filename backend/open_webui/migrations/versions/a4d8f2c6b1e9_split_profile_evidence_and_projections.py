"""education: split immutable profile evidence from metric projections

Revision ID: a4d8f2c6b1e9
Revises: f3b9d6e8a2c4
Create Date: 2026-09-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4d8f2c6b1e9"
down_revision: Union[str, Sequence[str], None] = "f3b9d6e8a2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty_education_evidence_data() -> None:
    connection = op.get_bind()
    for table_name in (
        "student_profile_snapshot",
        "submission_review",
        "submission",
        "micro_reflection",
        "analysis_result",
        "editor_operation",
        "provenance_segment",
        "writing_version",
    ):
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Profile evidence schema is intentionally incompatible; clear "
                "education profile data before upgrading."
            )


def upgrade() -> None:
    _require_empty_education_evidence_data()
    op.drop_index(
        "student_profile_snapshot_assignment_round_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_index(
        "student_profile_snapshot_student_metric_created_idx",
        table_name="student_profile_snapshot",
    )
    op.drop_table("student_profile_snapshot")

    with op.batch_alter_table("assignment") as batch:
        batch.create_check_constraint(
            "assignment_status_check", "status IN ('active', 'archived')"
        )
        batch.create_check_constraint("assignment_score_max_check", "score_max > 0")
    with op.batch_alter_table("writing_version") as batch:
        batch.create_unique_constraint(
            "writing_version_session_number_idx",
            ["writing_session_id", "version_no"],
        )
        batch.create_check_constraint("writing_version_number_check", "version_no >= 1")
        batch.create_check_constraint(
            "writing_version_trigger_check",
            "trigger_type IN ('autosave', 'manual', 'submit', 'submit_preflight')",
        )
    with op.batch_alter_table("provenance_segment") as batch:
        batch.create_unique_constraint(
            "provenance_session_segment_idx",
            ["writing_session_id", "segment_id"],
        )
    with op.batch_alter_table("analysis_result") as batch:
        batch.alter_column(
            "submission_id",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch.create_foreign_key(
            "analysis_result_submission_fk",
            "submission",
            ["submission_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint(
            "analysis_result_scope_type_idx",
            ["writing_session_id", "submission_id", "result_type"],
        )
    with op.batch_alter_table("editor_operation") as batch:
        batch.add_column(sa.Column("occurred_at_ms", sa.BigInteger(), nullable=False))
        batch.add_column(sa.Column("client_sequence", sa.BigInteger(), nullable=False))
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
    with op.batch_alter_table("submission") as batch:
        batch.create_check_constraint("submission_round_check", "round_no >= 1")
        batch.create_check_constraint(
            "submission_current_check", "is_current IN (0, 1)"
        )
    with op.batch_alter_table("submission_review") as batch:
        batch.create_check_constraint(
            "submission_review_status_check",
            "review_status IN ('pending', 'reviewed', 'returned')",
        )
        batch.create_check_constraint(
            "submission_review_score_check", "score IS NULL OR score >= 0"
        )

    op.create_table(
        "profile_evidence_snapshot",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("evidence_revision", sa.BigInteger(), nullable=False),
        sa.Column("evidence_schema_version", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("round_no", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.BigInteger(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submission.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "submission_id",
            "evidence_revision",
            name="profile_evidence_submission_revision_idx",
        ),
        sa.CheckConstraint(
            "evidence_revision >= 1", name="profile_evidence_revision_check"
        ),
        sa.CheckConstraint("round_no >= 1", name="profile_evidence_round_check"),
        sa.CheckConstraint(
            "length(evidence_hash) = 64", name="profile_evidence_hash_check"
        ),
    )
    op.create_index(
        "profile_evidence_student_submitted_idx",
        "profile_evidence_snapshot",
        ["student_id", "submitted_at"],
    )
    op.create_index(
        "profile_evidence_assignment_round_idx",
        "profile_evidence_snapshot",
        ["assignment_id", "round_no"],
    )

    op.create_table(
        "submission_review_event",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot_id", sa.Text(), nullable=False),
        sa.Column("review_revision", sa.BigInteger(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("score", sa.BigInteger(), nullable=True),
        sa.Column("rubric_scores", sa.Text(), nullable=True),
        sa.Column("overall_comment", sa.Text(), nullable=True),
        sa.Column("returned_comment", sa.Text(), nullable=True),
        sa.Column("resubmit_due_at", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submission.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["profile_evidence_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "submission_id",
            "review_revision",
            name="submission_review_event_revision_idx",
        ),
        sa.CheckConstraint(
            "review_revision >= 1", name="submission_review_event_revision_check"
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'returned')",
            name="submission_review_event_status_check",
        ),
        sa.CheckConstraint(
            "score IS NULL OR score >= 0",
            name="submission_review_event_score_check",
        ),
    )
    op.create_index(
        "submission_review_event_submission_created_idx",
        "submission_review_event",
        ["submission_id", "created_at"],
    )

    op.create_table(
        "profile_algorithm_release",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("metric_version", sa.Text(), nullable=False, unique=True),
        sa.Column("insight_version", sa.Text(), nullable=False),
        sa.Column("evidence_schema_versions", sa.Text(), nullable=False),
        sa.Column("formula_config_json", sa.Text(), nullable=False),
        sa.Column("code_commit_sha", sa.Text(), nullable=False),
        sa.Column("code_checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("activated_at", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="profile_algorithm_release_status_check",
        ),
    )

    op.create_table(
        "profile_projection_run",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("expected_count", sa.BigInteger(), nullable=False),
        sa.Column("succeeded_count", sa.BigInteger(), nullable=False),
        sa.Column("failed_count", sa.BigInteger(), nullable=False),
        sa.Column("error_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("code_commit_sha", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("finished_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["metric_version"], ["profile_algorithm_release.metric_version"]
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="profile_projection_run_status_check",
        ),
        sa.CheckConstraint(
            "expected_count >= 0 AND succeeded_count >= 0 AND failed_count >= 0",
            name="profile_projection_run_count_check",
        ),
    )

    op.create_table(
        "profile_metric_projection",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("evidence_snapshot_id", sa.Text(), nullable=False),
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("round_no", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.BigInteger(), nullable=False),
        sa.Column("review_revision", sa.BigInteger(), nullable=False),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column("projection_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("output_hash", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["profile_evidence_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submission.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["metric_version"], ["profile_algorithm_release.metric_version"]
        ),
        sa.ForeignKeyConstraint(["run_id"], ["profile_projection_run.id"]),
        sa.UniqueConstraint(
            "evidence_snapshot_id",
            "review_revision",
            "metric_version",
            name="profile_metric_projection_identity_idx",
        ),
        sa.CheckConstraint(
            "review_revision >= 0", name="profile_metric_projection_review_check"
        ),
        sa.CheckConstraint(
            "round_no >= 1", name="profile_metric_projection_round_check"
        ),
        sa.CheckConstraint(
            "length(input_hash) = 64 AND length(output_hash) = 64",
            name="profile_metric_projection_hash_check",
        ),
    )
    op.create_index(
        "profile_metric_student_version_submitted_idx",
        "profile_metric_projection",
        ["student_id", "metric_version", "submitted_at"],
    )
    op.create_index(
        "profile_metric_student_version_assignment_idx",
        "profile_metric_projection",
        ["student_id", "metric_version", "assignment_id", "round_no"],
    )

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


def downgrade() -> None:
    raise RuntimeError(
        "The profile evidence/projection split is intentionally forward-only."
    )
