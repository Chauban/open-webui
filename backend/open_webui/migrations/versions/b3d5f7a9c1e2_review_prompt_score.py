"""education: teacher-scored prompt quality

Revision ID: b3d5f7a9c1e2
Revises: a9c2e4f6b8d0
Create Date: 2026-09-23 12:00:00.000000

协作指数原先是消化度、提问投入、反思质量三项平均。提问投入按提问条数折算
(问满 10 条即满分),只奖励多问:刷几条「继续」就能拿满,问一个准问题的反而
只有 10 分。消化度按 AI 片段改写比例平均,删掉的 AI 片段会被算成深度改写,
测的也只是改写程度而不是理解。

现在提问质量改由教师批改时给 1—5 分,`submission_review` 与只追加的
`submission_review_event` 各加一列 `prompt_score`;协作指数只由提问质量与
反思质量组成,没有 AI 对话的提交只看反思质量。消化度(及批改侧的平均改写率)
整个下线,不在库里,无需迁移。

只是加可空列,证据快照结构不变,所以不要求清空画像证据表。指标口径变了,
PROFILE_METRIC_VERSION 升到 2026-09-23.1;升级后用 profile_recompute --activate
重算并启用新版本。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d5f7a9c1e2"
down_revision: Union[str, Sequence[str], None] = "a9c2e4f6b8d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("submission_review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prompt_score", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "submission_review_prompt_score_check",
            "prompt_score IS NULL OR prompt_score BETWEEN 1 AND 5",
        )

    with op.batch_alter_table("submission_review_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prompt_score", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "submission_review_event_prompt_score_check",
            "prompt_score IS NULL OR prompt_score BETWEEN 1 AND 5",
        )


def downgrade() -> None:
    with op.batch_alter_table("submission_review_event", schema=None) as batch_op:
        batch_op.drop_constraint(
            "submission_review_event_prompt_score_check", type_="check"
        )
        batch_op.drop_column("prompt_score")

    with op.batch_alter_table("submission_review", schema=None) as batch_op:
        batch_op.drop_constraint("submission_review_prompt_score_check", type_="check")
        batch_op.drop_column("prompt_score")
