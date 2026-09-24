"""education: drop assignment archive

Revision ID: c5e7a9b1d3f4
Revises: b3d5f7a9c1e2
Create Date: 2026-09-24 12:00:00.000000

作业归档下线。截止时间一过学生就不能再交,已批改的提交也不能重交(只有教师
退回才开新轮),归档能做的事截止与批改已经全部覆盖,留着只是多一个状态。

删掉 `assignment.status`、`assignment.archived_at` 与 `assignment_status_check`。
曾被归档的作业随之变回普通作业:过了截止时间照样不能提交,提交与批改原样保留。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7a9b1d3f4"
down_revision: Union[str, Sequence[str], None] = "b3d5f7a9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 早期 SQLite 库的 assignment 表经过重建,CHECK 约束已不在表上;
    # 约束只在存在时删,列照删。
    check_names = {
        check["name"]
        for check in sa.inspect(op.get_bind()).get_check_constraints("assignment")
    }
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        if "assignment_status_check" in check_names:
            batch_op.drop_constraint("assignment_status_check", type_="check")
        batch_op.drop_column("status")
        batch_op.drop_column("archived_at")


def downgrade() -> None:
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column("status", sa.Text(), nullable=False, server_default="active")
        )
        batch_op.create_check_constraint(
            "assignment_status_check", "status IN ('active', 'archived')"
        )
