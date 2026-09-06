"""education: challenge quoted span and pre-start skip

Revision ID: c1a3e5b7d9f2
Revises: b1e6d4a8c3f7
Create Date: 2026-09-06 12:00:00.000000

两件事:

1. `challenge_turn.quoted_span` —— 每一轮质疑必须引用它质疑的原文片段。修订判定
   从「全文改了多少字」换成「被质疑的那处变没变」,片段就是那个锚点。已有回合没有
   片段,按脏数据直接删,不做回填。
2. `challenge_session.source_version_id` 放开为可空 —— 学生在契约页尚未开始就跳过
   时,确实不存在「被质疑的那一稿」。空在这里是语义正确的状态,不是兜底。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a3e5b7d9f2"
down_revision: Union[str, Sequence[str], None] = "b1e6d4a8c3f7"
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
    """修订判定口径换了,证据载荷形状随之改变,与 b1e6d4a8c3f7 同一机制。"""

    table_names = set(sa.inspect(connection).get_table_names())
    for table_name in _EVIDENCE_TABLES:
        if table_name not in table_names:
            continue
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Profile evidence schema 2026-09-06.2 is intentionally incompatible "
                "with snapshots captured under 2026-09-06.1. Clear the profile "
                "evidence tables before upgrading: " + ", ".join(_EVIDENCE_TABLES)
            )


def upgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    # 没有片段的历史回合无法参与新的修订判定,留着只会让教师看到半套证据。
    # 级联会带走 challenge_turn。
    op.execute(sa.text("DELETE FROM challenge_session"))

    op.add_column(
        "challenge_turn",
        sa.Column(
            "quoted_span",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )

    with op.batch_alter_table("challenge_session", schema=None) as batch_op:
        batch_op.alter_column(
            "source_version_id", existing_type=sa.Text(), nullable=True
        )


def downgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    op.execute(sa.text("DELETE FROM challenge_session"))

    with op.batch_alter_table("challenge_session", schema=None) as batch_op:
        batch_op.alter_column(
            "source_version_id", existing_type=sa.Text(), nullable=False
        )

    op.drop_column("challenge_turn", "quoted_span")
