"""education: first read-through diagnosis for revise-draft assignments

Revision ID: a7c9e1b3d5f8
Revises: e8a0c2d4f6b7
Create Date: 2026-10-02 18:00:00.000000

修订初稿作业的「第一次通读」。学生交了初稿后,服务端先让模型对作业的每一个评分维度
逐项下结论(要改 / 可改进 / 达标 / 暂缓),再按这张结论表写首轮回复。结论表就是
修改清单:学生提交时对「要改」的几项交代怎么处理的,老师按维度核对。

- `revision_item`:一个写作会话里每个评分维度一条,`(writing_session_id, criterion_key)`
  唯一,`item_no` 是维度在作业评分标准里的顺序。`status` 只允许四个取值;
  `finding` 是给学生看的一句话结论(暂缓时为空);`quoted_span` 是原句
  (锚不住或不需要时为空)。`decision` 是学生的处理,只允许三个取值或为空。
- 暂缓与补看:某一项(`is_blocking`,如综述定位)出问题时,另几项先暂缓;学生改好后
  点「接着看」,平台确认那一项改到位了,再给暂缓的几项补上结论。`follow_up_at`:
  暂缓项是补看时补上结论的时间;那一项是补看确认改到位的时间。
- `writing_session.revision_items_generated_at`:通读完成的时间,有值即不再通读。
  `revision_items_claimed_at`:通读进行中的占位,防止并发重复调模型。

只加表和列,不动现有数据。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1b3d5f8"
down_revision: Union[str, Sequence[str], None] = "e8a0c2d4f6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revision_item",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("writing_session_id", sa.Text(), nullable=False),
        sa.Column("item_no", sa.Integer(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("finding", sa.Text(), nullable=True),
        sa.Column("quoted_span", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.BigInteger(), nullable=True),
        sa.Column(
            "is_blocking", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("follow_up_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "writing_session_id", "item_no", name="revision_item_order_idx"
        ),
        sa.UniqueConstraint(
            "writing_session_id",
            "criterion_key",
            name="revision_item_criterion_idx",
        ),
        sa.CheckConstraint(
            "status IN ('problem', 'minor', 'ok', 'deferred')",
            name="revision_item_status_check",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('revised', 'partly', 'kept')",
            name="revision_item_decision_check",
        ),
    )

    with op.batch_alter_table("writing_session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("revision_items_generated_at", sa.BigInteger(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("revision_items_claimed_at", sa.BigInteger(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("writing_session", schema=None) as batch_op:
        batch_op.drop_column("revision_items_claimed_at")
        batch_op.drop_column("revision_items_generated_at")

    op.drop_table("revision_item")
