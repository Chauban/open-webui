"""education: pre-writing critique round

Revision ID: f4d6b8c0e2a5
Revises: e3c5a7b9d1f4
Create Date: 2026-09-06 16:00:00.000000

提交前质疑的对偶。质疑受时机所限——正文为空时没有可质疑的东西;但空白页阶段可以
评析别人的文章。两个环节因此在时间轴上互补:

    写作前：评析靶文（建立判断标准） -> 写作 -> 提交前：接受质疑（把标准用于自己）

这是教学环节里唯一具备标准答案、因而唯一可自动判定的一环——也就是唯一不增加教师
批改负担的一环,这是它能进产品的前提。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4d6b8c0e2a5"
down_revision: Union[str, Sequence[str], None] = "e3c5a7b9d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 顺序即安全删除顺序：派生在前，证据在后。
_EVIDENCE_TABLES = (
    "student_profile_rollup_projection",
    "student_profile_aggregate_projection",
    "profile_projection_outbox",
    "profile_metric_projection",
    "submission_review_event",
    "profile_evidence_snapshot",
)


def _require_empty_profile_evidence(connection) -> None:
    """证据载荷加了 critique 段，与既有几版同一机制。"""

    table_names = set(sa.inspect(connection).get_table_names())
    for table_name in _EVIDENCE_TABLES:
        if table_name not in table_names:
            continue
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Profile evidence schema 2026-09-06.3 is intentionally incompatible "
                "with snapshots captured under 2026-09-06.2. Clear the profile "
                "evidence tables before upgrading: " + ", ".join(_EVIDENCE_TABLES)
            )


def upgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    op.add_column(
        "assignment",
        sa.Column(
            "critique_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("assignment", sa.Column("critique_text", sa.Text(), nullable=True))
    op.add_column(
        "assignment",
        sa.Column(
            "critique_flaws",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )

    op.create_table(
        "critique_attempt",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Text(), nullable=False),
        sa.Column("student_id", sa.Text(), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("matches_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignment.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # 一个学生一次作业至多一条:这是写作前的一道门,不是可以反复刷的练习。
        sa.UniqueConstraint(
            "assignment_id", "student_id", name="critique_attempt_student_idx"
        ),
    )


def downgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    op.drop_table("critique_attempt")
    op.drop_column("assignment", "critique_flaws")
    op.drop_column("assignment", "critique_text")
    op.drop_column("assignment", "critique_enabled")
