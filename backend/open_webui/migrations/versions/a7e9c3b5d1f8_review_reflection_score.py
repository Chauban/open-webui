"""education: teacher-scored reflection quality

Revision ID: a7e9c3b5d1f8
Revises: f4d6b8c0e2a5
Create Date: 2026-09-07 10:00:00.000000

反思质量原先由 `_score_reflection` 按四段字符数折算(action 60 字、location 20 字、
judgement 60 字、next_step 40 字,写满即满分),只数字数、内容不看。它同时是协作
指数的三分之一权重,没用 AI 的提交更是这一维的全部,凑字数就能刷满;而目标字数
又随 index_formula 一起返回给学生,等于把刷分路标一并给出。

现在这一维改由教师批改时给 1—5 分,`submission_review` 与只追加的
`submission_review_event` 各加一列 `reflection_score`。指标口径变了,
PROFILE_METRIC_VERSION 升到 2026-09-07.1,派生投影必须重算,因此沿用既有约定:
证据表非空即拒绝升级,由人显式清空,不做回填。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7e9c3b5d1f8"
down_revision: Union[str, Sequence[str], None] = "f4d6b8c0e2a5"
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
                "Profile metric version 2026-09-07.1 scores reflection quality from "
                "the teacher review instead of reflection character counts, so every "
                "existing projection is stale. Clear the profile evidence tables "
                "before upgrading: " + ", ".join(_EVIDENCE_TABLES)
            )


def upgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    with op.batch_alter_table("submission_review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reflection_score", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "submission_review_reflection_score_check",
            "reflection_score IS NULL OR reflection_score BETWEEN 1 AND 5",
        )

    with op.batch_alter_table("submission_review_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reflection_score", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "submission_review_event_reflection_score_check",
            "reflection_score IS NULL OR reflection_score BETWEEN 1 AND 5",
        )


def downgrade() -> None:
    _require_empty_profile_evidence(op.get_bind())

    with op.batch_alter_table("submission_review_event", schema=None) as batch_op:
        batch_op.drop_constraint(
            "submission_review_event_reflection_score_check", type_="check"
        )
        batch_op.drop_column("reflection_score")

    with op.batch_alter_table("submission_review", schema=None) as batch_op:
        batch_op.drop_constraint(
            "submission_review_reflection_score_check", type_="check"
        )
        batch_op.drop_column("reflection_score")
