"""merge upstream v0.9.6 and education heads

Revision ID: 9e7c2f4a8b1d
Revises: 461111b60977, f7a8b9c0d1e2
Create Date: 2026-07-07 12:00:00.000000

"""

from typing import Sequence, Union


revision: str = "9e7c2f4a8b1d"
down_revision: Union[str, Sequence[str], None] = ("461111b60977", "f7a8b9c0d1e2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
