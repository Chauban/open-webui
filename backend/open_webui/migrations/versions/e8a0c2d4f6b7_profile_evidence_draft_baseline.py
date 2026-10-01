"""education: profile evidence carries the draft baseline

Revision ID: e8a0c2d4f6b7
Revises: d6f8a0b2c4e5
Create Date: 2026-10-01 18:00:00.000000

修订初稿作业的过程指标要从学生声明的初稿算起:第一轮的版本差异、大段写入与
修订深度都以初稿基线为起点,否则整篇初稿会被当成一次「大段写入」。证据载荷因此
新增 `draft_baseline_text`(提交时冻结),evidence_schema_version 升到 2026-10-01.1,
PROFILE_METRIC_VERSION 同步升级。

表结构不变。沿用既有约定:画像证据表非空即拒绝升级,由人显式清空,不做回填。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a0c2d4f6b7"
down_revision: Union[str, Sequence[str], None] = "d6f8a0b2c4e5"
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


def upgrade() -> None:
    connection = op.get_bind()
    table_names = set(sa.inspect(connection).get_table_names())
    for table_name in _EVIDENCE_TABLES:
        if table_name not in table_names:
            continue
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Profile evidence schema 2026-10-01.1 adds the draft baseline, so "
                "snapshots captured under 2026-09-14.1 no longer validate. Clear the "
                "profile evidence tables before upgrading: " + ", ".join(_EVIDENCE_TABLES)
            )


def downgrade() -> None:
    pass
