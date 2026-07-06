"""merge upstream v0.9.0 and education heads

Revision ID: f7a8b9c0d1e2
Revises: 56359461a091, e6a1b2c3d4f5
Create Date: 2026-07-07 01:00:00.000000

"""

from typing import Sequence, Union


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = ("56359461a091", "e6a1b2c3d4f5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
