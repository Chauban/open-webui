"""education: remove the pre-writing critique round

Revision ID: b8e2d4f6a0c1
Revises: a7e9c3b5d1f8
Create Date: 2026-09-08 10:00:00.000000

写作前评析(靶文 + 预设漏洞)整个环节下线。它不增加教师批改负担,却把负担挪到了
备课上:每份作业都要教师自己挑靶文、逐条写漏洞并绑评分维度,且刻意不提供「一键
生成靶文并启用」——AI 标的漏洞未必成立,直接挂上去就是教错。这份每次重来的手工
成本决定了它不会被常态使用,所以连同数据一并删除,而不是留个关着的开关。

证据载荷去掉了 critique 段,evidence_schema_version 落到 2026-09-08.1;投影少了
critique_hit_ratio 一列,PROFILE_METRIC_VERSION 同步落到 2026-09-08.1,派生投影必须
重算。沿用既有约定:证据表非空即拒绝升级,由人显式清空,不做回填。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2d4f6a0c1"
down_revision: Union[str, Sequence[str], None] = "a7e9c3b5d1f8"
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
                "Profile evidence schema 2026-09-08.1 drops the critique section, so "
                "snapshots captured under 2026-09-06.3 no longer validate. Clear the "
                "profile evidence tables before upgrading: "
                + ", ".join(_EVIDENCE_TABLES)
            )


def upgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    op.drop_table("critique_attempt")

    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.drop_column("critique_flaws")
        batch_op.drop_column("critique_text")
        batch_op.drop_column("critique_enabled")


def downgrade() -> None:
    """不提供回退。

    评析环节的代码已经删干净,把列和表加回来也没有任何东西会去写它们。
    """

    raise NotImplementedError("The pre-writing critique round is gone for good")
