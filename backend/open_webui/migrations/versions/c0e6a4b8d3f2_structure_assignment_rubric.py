"""education: require assignment rubric schema and strict scores

Revision ID: c0e6a4b8d3f2
Revises: b9d5f3a7c2e1
Create Date: 2026-09-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0e6a4b8d3f2"
down_revision: Union[str, Sequence[str], None] = "b9d5f3a7c2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty_scoring_data() -> None:
    connection = op.get_bind()
    assignments = connection.execute(sa.text("SELECT COUNT(*) FROM assignment")).scalar_one()
    reviews = connection.execute(sa.text("SELECT COUNT(*) FROM submission_review")).scalar_one()
    if assignments or reviews:
        raise RuntimeError(
            "Assignment scoring uses a different strict schema; clear education "
            "development data before changing this migration state."
        )


def upgrade() -> None:
    _require_empty_scoring_data()
    op.add_column(
        "assignment",
        sa.Column("rubric_schema", sa.Text(), nullable=False),
    )
    op.execute("DROP TABLE submission_review")
    op.execute(
        "CREATE TABLE submission_review ("
        "id TEXT PRIMARY KEY, "
        "submission_id TEXT NOT NULL UNIQUE, "
        "assignment_id TEXT NOT NULL, "
        "reviewer_id TEXT NOT NULL, "
        "review_status TEXT NOT NULL, "
        "score BIGINT, "
        "overall_comment TEXT, "
        "rubric_scores TEXT, "
        "returned_comment TEXT, "
        "resubmit_due_at BIGINT, "
        "reviewed_at BIGINT, "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )


def downgrade() -> None:
    _require_empty_scoring_data()
    op.drop_column("assignment", "rubric_schema")
    op.execute("DROP TABLE submission_review")
    op.execute(
        "CREATE TABLE submission_review ("
        "id TEXT PRIMARY KEY, "
        "submission_id TEXT NOT NULL UNIQUE, "
        "assignment_id TEXT NOT NULL, "
        "reviewer_id TEXT NOT NULL, "
        "review_status TEXT NOT NULL, "
        "score BIGINT, "
        "overall_comment TEXT, "
        "rubric_json TEXT, "
        "returned_comment TEXT, "
        "resubmit_due_at BIGINT, "
        "reviewed_at BIGINT, "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )
