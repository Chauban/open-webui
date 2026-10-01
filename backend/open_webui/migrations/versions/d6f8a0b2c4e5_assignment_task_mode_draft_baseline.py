"""education: assignment task mode and draft baseline

Revision ID: d6f8a0b2c4e5
Revises: c5e7a9b1d3f4
Create Date: 2026-10-01 12:00:00.000000

作业新增「作业形式」`task_mode`:从零写作(`from_scratch`,默认)或修订初稿
(`revise_draft`)。两者的差别在于作业开始时初稿是否已经存在:修订初稿作业里
学生先在写作区显式提交课外写好的初稿,冻结为修改的起点,再和 AI 对话修改。

- `assignment.task_mode`:Text,默认 `from_scratch`,CHECK 只允许两个取值。
- 修订初稿作业结构上没有质疑式读者(左侧对话本身就是按维度诊断与追问),
  CHECK `NOT (task_mode = 'revise_draft' AND challenge_enabled)` 兜住这条。
- `writing_session.draft_baseline_text` / `draft_baseline_at`:初稿基线。一个
  会话只有一份,确认后不可改;退回重交时基线仍是最初那份。不用 writing_version
  存基线,因为基线不是一次保存。

只加列,现有作业落到 `from_scratch`,行为不变。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6f8a0b2c4e5"
down_revision: Union[str, Sequence[str], None] = "c5e7a9b1d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "task_mode", sa.Text(), nullable=False, server_default="from_scratch"
            )
        )
        batch_op.create_check_constraint(
            "assignment_task_mode_check",
            "task_mode IN ('from_scratch', 'revise_draft')",
        )
        batch_op.create_check_constraint(
            "assignment_revise_draft_no_challenge_check",
            "NOT (task_mode = 'revise_draft' AND challenge_enabled)",
        )

    with op.batch_alter_table("writing_session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("draft_baseline_text", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("draft_baseline_at", sa.BigInteger(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("writing_session", schema=None) as batch_op:
        batch_op.drop_column("draft_baseline_at")
        batch_op.drop_column("draft_baseline_text")

    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.drop_constraint(
            "assignment_revise_draft_no_challenge_check", type_="check"
        )
        batch_op.drop_constraint("assignment_task_mode_check", type_="check")
        batch_op.drop_column("task_mode")
