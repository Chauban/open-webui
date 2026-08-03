"""education: own the classroom/writing_session indexes in schema

Revision ID: e7b9d1f3a5c7
Revises: d5f7c9e1a3b4
Create Date: 2026-08-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e7b9d1f3a5c7"
down_revision: Union[str, Sequence[str], None] = "d5f7c9e1a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 这些索引此前由 models 里的 _ensure_* 在每次调用时 drop/create,
    # 现在交给 schema:早期过严的唯一索引删掉,当前需要的建出来。
    op.execute("DROP INDEX IF EXISTS classroom_teacher_idx")
    op.execute("DROP INDEX IF EXISTS classroom_member_user_idx")
    op.execute("DROP INDEX IF EXISTS writing_session_assignment_student_idx")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_member_classroom_user_idx "
        "ON classroom_member (classroom_id, user_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_invite_code_idx "
        "ON classroom (invite_code)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS writing_session_assignment_owner_scope_idx "
        "ON writing_session (assignment_id, owner_user_id, scope)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS writing_session_assignment_owner_scope_idx")
    op.execute("DROP INDEX IF EXISTS classroom_invite_code_idx")
    op.execute("DROP INDEX IF EXISTS classroom_member_classroom_user_idx")
