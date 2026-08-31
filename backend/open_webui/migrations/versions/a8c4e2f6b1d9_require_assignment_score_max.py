"""education: require an explicit assignment score scale

Revision ID: a8c4e2f6b1d9
Revises: e9a3c7b5d1f4
Create Date: 2026-08-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8c4e2f6b1d9"
down_revision: Union[str, Sequence[str], None] = "e9a3c7b5d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    assignment_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM assignment")
    ).scalar_one()
    if assignment_count:
        raise RuntimeError(
            "Existing assignments have no trustworthy score scale; clear education "
            "development data before applying this migration."
        )
    op.add_column(
        "assignment",
        sa.Column("score_max", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("assignment", "score_max")
