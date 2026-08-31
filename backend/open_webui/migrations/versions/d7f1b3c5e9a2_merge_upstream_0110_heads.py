"""merge upstream v0.11.0 heads with the education chain

Revision ID: d7f1b3c5e9a2
Revises: e7b9d1f3a5c7, f0bd01a18a3d
Create Date: 2026-08-31 00:00:00.000000

"""

from typing import Sequence, Union

revision: str = "d7f1b3c5e9a2"
down_revision: Union[str, Sequence[str], None] = ("e7b9d1f3a5c7", "f0bd01a18a3d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
