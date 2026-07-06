"""merge alembic heads

Revision ID: c3d4e5f6a7b8
Revises: 7f3c2e1a9b4d, b2c3d4e5f6a7
Create Date: 2026-03-17 10:20:00.000000

"""

from typing import Sequence, Union


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = ("7f3c2e1a9b4d", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
