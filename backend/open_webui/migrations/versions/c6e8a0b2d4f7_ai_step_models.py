"""education: per-step AI models; image parsing model moves into the AI step settings

Revision ID: c6e8a0b2d4f7
Revises: b3d5f7a9c1e4
Create Date: 2026-10-18 14:00:00.000000

管理员在「AI 步骤设置」里给每个平台步骤选模型（通读与补看、读者试读、图片识别、班级论证
归纳），配置集中到 `education.ai_steps`。

- 配置:原来单独的 `education.draft_image_model` 并入 `education.ai_steps.image_parsing.model`,
  旧键删除。`education.thinking`(只在开发库里出现过的上一版结构)直接删掉,按默认重新设定。
  原来没选识图模型(空串)的,新结构里也是空,仍表示不提供图片导入。
- 记录每一步实际用的模型(按设置解析之后的),提交时冻进本轮记录:
  `writing_session.revision_items_model_id` / `revision_follow_up_model_id`、
  `challenge_turn.model_id`、`challenge_session.closing_model_id`、`challenge_insight.model_id`。
  已有记录没有这项信息,留空。
"""

import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6e8a0b2d4f7"
down_revision: Union[str, Sequence[str], None] = "b3d5f7a9c1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MODEL_COLUMNS = (
    ("writing_session", "revision_items_model_id"),
    ("writing_session", "revision_follow_up_model_id"),
    ("challenge_turn", "model_id"),
    ("challenge_session", "closing_model_id"),
    ("challenge_insight", "model_id"),
)

# 与 open_webui.config.DEFAULT_EDUCATION_AI_STEPS 一致;迁移里写死,不随代码默认值变化。
_DEFAULT_AI_STEPS = {
    "coaching_chat": {"control": "admin", "default": "model_default"},
    "first_read": {"model": None, "thinking": "model_default"},
    "reader_check": {"model": None, "thinking": "model_default"},
    "image_parsing": {"model": None, "thinking": "off"},
    "class_insight": {"model": None, "thinking": "model_default"},
}

_config = sa.table(
    "config",
    sa.column("key", sa.Text),
    sa.column("value", sa.JSON),
    sa.column("updated_at", sa.BigInteger),
)


def upgrade() -> None:
    for table_name, column_name in _MODEL_COLUMNS:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column(column_name, sa.Text(), nullable=True))

    connection = op.get_bind()
    image_model = connection.execute(
        sa.select(_config.c.value).where(_config.c.key == "education.draft_image_model")
    ).scalar()
    connection.execute(
        _config.delete().where(_config.c.key.in_(("education.draft_image_model", "education.thinking")))
    )
    if isinstance(image_model, str) and image_model.strip():
        steps = {
            **_DEFAULT_AI_STEPS,
            "image_parsing": {"model": image_model.strip(), "thinking": "off"},
        }
        connection.execute(
            _config.insert().values(key="education.ai_steps", value=steps, updated_at=int(time.time()))
        )


def downgrade() -> None:
    """不提供回退:识图模型已并入 AI 步骤设置,回退要把它拆回去还要丢掉其余步骤的模型。"""

    raise NotImplementedError("AI step models stay in education.ai_steps")
