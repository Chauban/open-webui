"""education: unique (assignment_id, student_id, round_no) on submission

Revision ID: c3e5a7b9d1f2
Revises: b2c4d6e8f0a1
Create Date: 2026-08-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3e5a7b9d1f2"
down_revision: Union[str, Sequence[str], None] = "b2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 并发/重复点击提交曾能插出同一轮次的多条记录,先清掉重复行再建约束:
    # 每组只保留最后一次提交,其余连同挂在上面的批改一并删除。
    op.execute(
        "WITH ranked AS ("
        "  SELECT id, ROW_NUMBER() OVER ("
        "    PARTITION BY assignment_id, student_id, round_no"
        "    ORDER BY submitted_at DESC, id DESC"
        "  ) AS rn FROM submission"
        ") "
        "DELETE FROM submission WHERE id IN (SELECT id FROM ranked WHERE rn > 1)"
    )
    op.execute(
        "DELETE FROM submission_review "
        "WHERE submission_id NOT IN (SELECT id FROM submission)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS submission_assignment_student_round_idx "
        "ON submission (assignment_id, student_id, round_no)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS submission_assignment_student_round_idx")
