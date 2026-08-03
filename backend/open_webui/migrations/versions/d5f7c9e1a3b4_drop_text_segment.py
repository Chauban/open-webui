"""education: drop the write-only text_segment table

Revision ID: d5f7c9e1a3b4
Revises: c3e5a7b9d1f2
Create Date: 2026-08-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d5f7c9e1a3b4"
down_revision: Union[str, Sequence[str], None] = "c3e5a7b9d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 段落分析一直从 analysis_result.payload_json 读取,text_segment 只写不读;
    # 它按 writing_session 整表替换,还会在重算时抹掉同一会话其他轮次的行。
    op.execute("DROP TABLE IF EXISTS text_segment")


def downgrade() -> None:
    # 表内数据没有任何读取方,不做重建。
    pass
