"""education: a student belongs to at most one classroom

Revision ID: a9c2e4f6b8d0
Revises: e7b3d5f9a1c4
Create Date: 2026-09-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a9c2e4f6b8d0"
down_revision: Union[str, Sequence[str], None] = "e7b3d5f9a1c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 学生曾能凭多个邀请码同时进多个班。每人只留最早加入的那个班,其余关系直接删;
    # 提交记录挂在作业上,不随班级关系删除。
    op.execute(
        "WITH ranked AS ("
        "  SELECT id, ROW_NUMBER() OVER ("
        "    PARTITION BY user_id"
        "    ORDER BY created_at ASC, id ASC"
        "  ) AS rn FROM classroom_member WHERE member_role = 'student'"
        ") "
        "DELETE FROM classroom_member WHERE id IN (SELECT id FROM ranked WHERE rn > 1)"
    )
    # 教师可以带多个班,唯一性只约束学生行。SQLite 与 PostgreSQL 都支持部分索引。
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_member_single_student_idx "
        "ON classroom_member (user_id) WHERE member_role = 'student'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS classroom_member_single_student_idx")
