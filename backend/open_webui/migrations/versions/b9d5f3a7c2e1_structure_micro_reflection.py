"""education: structure submission reflection evidence

Revision ID: b9d5f3a7c2e1
Revises: a8c4e2f6b1d9
Create Date: 2026-08-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9d5f3a7c2e1"
down_revision: Union[str, Sequence[str], None] = "a8c4e2f6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty_reflections() -> None:
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM micro_reflection")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Micro reflections use a different strict schema; clear education "
            "development data before changing this migration state."
        )


def upgrade() -> None:
    _require_empty_reflections()
    op.execute("DROP TABLE micro_reflection")
    op.execute(
        "CREATE TABLE micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_used BOOLEAN NOT NULL, "
        "ai_help_types TEXT NOT NULL, "
        "reflection_json TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )


def downgrade() -> None:
    _require_empty_reflections()
    op.execute("DROP TABLE micro_reflection")
    op.execute(
        "CREATE TABLE micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_help_types TEXT NOT NULL, "
        "reflection_text TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )
