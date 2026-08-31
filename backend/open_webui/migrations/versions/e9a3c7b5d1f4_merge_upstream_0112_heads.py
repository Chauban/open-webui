"""merge upstream v0.11.2 heads with the education chain

Revision ID: e9a3c7b5d1f4
Revises: d7f1b3c5e9a2, d4c1a8e37b62
Create Date: 2026-08-31 00:00:00.000000

"""

from typing import Sequence, Union

revision: str = "e9a3c7b5d1f4"
down_revision: Union[str, Sequence[str], None] = ("d7f1b3c5e9a2", "d4c1a8e37b62")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
