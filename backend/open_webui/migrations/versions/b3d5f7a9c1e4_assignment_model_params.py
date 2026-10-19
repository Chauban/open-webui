"""education: per-assignment model params for the coaching chat

Revision ID: b3d5f7a9c1e4
Revises: a7c9e1b3d5f8
Create Date: 2026-10-18 10:00:00.000000

`assignment.model_params`:教师按作业设的辅导对话参数,目前只有思考档位
(`{"thinking": null | 档位, "students_choose_thinking": bool}`)。只有管理员把辅导对话的
思考档位下放给教师后才能设;空对象即沿用管理员的默认。通读与补看、读者试读等平台步骤
不读这一列。与其余教学 JSON 列一样存 TEXT。

只加列,不动现有数据。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d5f7a9c1e4"
down_revision: Union[str, Sequence[str], None] = "a7c9e1b3d5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("model_params", sa.Text(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.drop_column("model_params")
