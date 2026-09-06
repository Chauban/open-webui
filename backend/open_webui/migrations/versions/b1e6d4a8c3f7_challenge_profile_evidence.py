"""education: challenge facts enter the growth profile evidence

Revision ID: b1e6d4a8c3f7
Revises: a9f4c2e7b3d1
Create Date: 2026-09-06 00:00:00.000000

证据载荷加了 challenge 段，evidence_schema_version 随之升到 2026-09-06.1。
载荷模型是 extra="forbid" 的严格模型且版本号是 Literal，旧快照读出来会直接
校验失败——这是有意的前向不兼容：同一个版本号必须对应同一种形状，否则
「相同证据 + 相同算法版本得到相同输出哈希」这条保证就不成立了。

所以这一版不改表结构，只在升级时拦一道：画像证据及其派生表必须为空。
清理范围只到画像侧，班级 / 作业 / 提交 / 写作版本都不受影响。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1e6d4a8c3f7"
down_revision: Union[str, Sequence[str], None] = "a9f4c2e7b3d1"
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
    table_names = set(sa.inspect(connection).get_table_names())
    for table_name in _EVIDENCE_TABLES:
        if table_name not in table_names:
            continue
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Profile evidence schema 2026-09-06.1 is intentionally incompatible "
                "with snapshots captured under 2026-09-03.1. Clear the profile "
                "evidence tables before upgrading: "
                + ", ".join(_EVIDENCE_TABLES)
            )


def upgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())


def downgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())
