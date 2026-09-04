"""education: give each assignment an AI coaching style

Revision ID: c5a9e3f1b7d4
Revises: b7c1e4a9d2f6
Create Date: 2026-09-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5a9e3f1b7d4"
down_revision: Union[str, Sequence[str], None] = "b7c1e4a9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assignment",
        sa.Column(
            "coaching_style",
            sa.Text(),
            nullable=False,
            server_default="balanced",
        ),
    )


def downgrade() -> None:
    op.drop_column("assignment", "coaching_style")
