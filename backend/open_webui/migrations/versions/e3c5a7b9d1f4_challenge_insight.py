"""education: cached class-level challenge insight

Revision ID: e3c5a7b9d1f4
Revises: d2b4f6a8c0e3
Create Date: 2026-09-06 15:00:00.000000

按维度的命中率是纯内存聚合,不落表。这张表只缓存第二层——把全班的未解决条目交给
模型归纳出的「本班普遍站不住的论证类型」。

必须缓存:不缓存的话教师每刷新一次看板就烧一次模型调用。缓存键是参与归纳的条目
集合的规范化哈希,内容没变就不重算。

不复用 analysis_result:那张表按 writing_session + submission 建唯一键,是逐份提交的
缓存;这里的输入是整个作业的全部提交,粒度对不上。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3c5a7b9d1f4"
down_revision: Union[str, Sequence[str], None] = "d2b4f6a8c0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "challenge_insight",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("categories_json", sa.JSON(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # 一个作业只留一条：输入变了就整条覆盖，不攒历史版本。教师要的是「现在这批
        # 提交归纳出什么」，不是归纳结果的编年史。
        sa.UniqueConstraint("assignment_id", name="challenge_insight_assignment_idx"),
    )


def downgrade() -> None:
    op.drop_table("challenge_insight")
