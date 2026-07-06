"""refine micro reflection AI help types

Revision ID: e6a1b2c3d4f5
Revises: d4f5e6a7b8c9
Create Date: 2026-05-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e6a1b2c3d4f5"
down_revision: Union[str, Sequence[str], None] = "d4f5e6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS micro_reflection")
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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS micro_reflection")
    op.execute(
        "CREATE TABLE micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_help_type TEXT NOT NULL, "
        "reflection_text TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )
