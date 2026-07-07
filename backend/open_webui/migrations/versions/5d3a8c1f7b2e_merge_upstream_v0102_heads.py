"""merge upstream v0.10.2 and education heads

Revision ID: 5d3a8c1f7b2e
Revises: 42e2978c7933, 9e7c2f4a8b1d
Create Date: 2026-07-07 18:00:00.000000

"""

from typing import Sequence, Union


revision: str = "5d3a8c1f7b2e"
down_revision: Union[str, Sequence[str], None] = ("42e2978c7933", "9e7c2f4a8b1d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
