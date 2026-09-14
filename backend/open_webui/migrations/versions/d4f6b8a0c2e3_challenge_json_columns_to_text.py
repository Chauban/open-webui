"""education: store challenge JSON columns as TEXT

Revision ID: d4f6b8a0c2e3
Revises: b8e2d4f6a0c1
Create Date: 2026-09-14 11:00:00.000000

质疑环节的两份迁移把 5 个列建成了 sa.JSON(),但 ORM 用的是 JSONField——它以 TEXT
存取、读出时自己 json.loads。PostgreSQL 上 json 列会被驱动先解码成 list/dict,
JSONField 再 loads 一次就抛 TypeError,任何读到非空值的查询都 500(作业列表、学生
写作首页、新建作业全挂)。SQLite 不区分列类型,所以本地和测试都没暴露。

与其余教学 JSON 列保持一致,统一改成 TEXT。只有 PostgreSQL 需要动:SQLite 的声明
类型不影响存储,batch 重建 assignment 表反而会牵动一串外键。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6b8a0c2e3"
down_revision: Union[str, Sequence[str], None] = "b8e2d4f6a0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("assignment", "challenge_focus_keys"),
    ("challenge_session", "focus_keys"),
    ("challenge_session", "closing_summary_json"),
    ("challenge_session", "checklist_state_json"),
    ("challenge_insight", "categories_json"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table_name, column_name in _COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            type_=sa.Text(),
            existing_type=sa.JSON(),
            postgresql_using=f"{column_name}::text",
        )
    op.alter_column("assignment", "challenge_focus_keys", server_default="[]")


def downgrade() -> None:
    """不提供回退:改回 json 列就是把这个 500 请回来。"""

    raise NotImplementedError("Challenge JSON columns stay TEXT")
