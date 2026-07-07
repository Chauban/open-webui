"""education feedback loop: submission rounds, resubmit due, notifications

Revision ID: b2c4d6e8f0a1
Revises: 5d3a8c1f7b2e
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, Sequence[str], None] = "5d3a8c1f7b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(inspector, table: str) -> set:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "submission" in tables:
        columns = _existing_columns(inspector, "submission")
        if "round_no" not in columns:
            op.execute(
                "ALTER TABLE submission ADD COLUMN round_no BIGINT NOT NULL DEFAULT 1"
            )
        if "is_current" not in columns:
            op.execute(
                "ALTER TABLE submission ADD COLUMN is_current BIGINT NOT NULL DEFAULT 1"
            )

    if "submission_review" in tables:
        columns = _existing_columns(inspector, "submission_review")
        if "resubmit_due_at" not in columns:
            op.execute(
                "ALTER TABLE submission_review ADD COLUMN resubmit_due_at BIGINT"
            )

    op.execute(
        "CREATE TABLE IF NOT EXISTS education_notification ("
        "id TEXT PRIMARY KEY, "
        "user_id TEXT NOT NULL, "
        "type TEXT NOT NULL, "
        "payload_json TEXT NOT NULL DEFAULT '{}', "
        "created_at BIGINT NOT NULL, "
        "read_at BIGINT)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS education_notification_user_idx "
        "ON education_notification (user_id, read_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS education_notification")
    # SQLite 不支持 DROP COLUMN(旧版),轮次列保留无害,不回退
