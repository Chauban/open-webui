"""education: challenge follow-up on the teacher's return comment

Revision ID: d2b4f6a8c0e3
Revises: c1a3e5b7d9f2
Create Date: 2026-09-06 14:00:00.000000

退回重交的闭环此前止于教师写下退回意见:学生看不看、改不改全凭自觉,教师没有任何
抓手。质疑引擎恰好具备「盯住一个点反复追问」的能力,只是它的焦点此前只能来自
rubric 维度。

- `submission_review.challenge_followup` —— 教师退回时勾的那一下,是他的意图。
- `challenge_session.followup_comment` —— 发起下一轮质疑时把那句话冻进来。措辞
  跟评语一样可以事后被改,已经开始的这一轮不能跟着变。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2b4f6a8c0e3"
down_revision: Union[str, Sequence[str], None] = "c1a3e5b7d9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "submission_review",
        sa.Column(
            "challenge_followup",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "challenge_session",
        sa.Column("followup_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("challenge_session", "followup_comment")
    op.drop_column("submission_review", "challenge_followup")
