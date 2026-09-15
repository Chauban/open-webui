"""education: teacher-defined reflection questions

Revision ID: e7b3d5f9a1c4
Revises: d4f6b8a0c2e3
Create Date: 2026-09-14 16:00:00.000000

提交前反思从「一套全站固定的题」改成「教师按作业自定」。只有「这次用了 AI 吗」
仍由系统固定询问(micro_reflection.ai_used),其余题目——包括原来固定的「AI 帮了你
什么」多选——都存进 assignment.reflection_questions,由教师增删改。

随之变化的数据:
- assignment 加 reflection_questions(TEXT,JSON 数组)。已有作业回填成原来那套固定
  题,学生看到的题目不变,教师之后可以自己改。
- micro_reflection.reflection_json 改成 {"items": [...]}:每项是提交当时的题目快照
  加学生的回答。已有反思按原来那套题原样转写;ai_help_types 列并入快照后删除。
- 「AI 帮助类型」不再是全站统一的枚举,画像里的帮助类型分布、生成/打磨比例和
  help_type_shift_refining 洞察随之下线。证据载荷 evidence_schema_version 升到
  2026-09-14.1,PROFILE_METRIC_VERSION 同步升级。沿用既有约定:画像证据表非空即
  拒绝升级,由人显式清空,不做回填。
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3d5f9a1c4"
down_revision: Union[str, Sequence[str], None] = "d4f6b8a0c2e3"
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

# 原来那套固定题的中文措辞与选项,冻结在迁移里,不随前端默认题变动。
_LEGACY_HELP_TYPE_LABELS = {
    "Understand Assignment": "理解题目",
    "Outline": "列提纲",
    "Examples": "举例子",
    "Explain Concepts": "解释概念",
    "Revise Structure": "修改结构",
    "Polish": "润色表达",
    "Check Errors": "检查错别字或语病",
    "Help Break Through Writer's Block": "帮助突破卡壳",
    "Strengthen Reasoning": "梳理论证",
}

_LEGACY_QUESTIONS = [
    {
        "id": "ai_help",
        "kind": "multi_choice",
        "prompt": "AI 在哪些方面帮助了你？",
        "options": list(_LEGACY_HELP_TYPE_LABELS.values()),
        "allow_other": True,
        "placeholder": None,
        "required": True,
        "show_when": "ai_used",
    },
    {
        "id": "action",
        "kind": "text",
        "prompt": "你具体修改了什么？",
        "options": [],
        "allow_other": False,
        "placeholder": "请描述一次具体的删改、补充或重组。",
        "required": True,
        "show_when": "always",
    },
    {
        "id": "location",
        "kind": "text",
        "prompt": "你修改了哪个位置？",
        "options": [],
        "allow_other": False,
        "placeholder": "例如：第二段、结论或论据部分。",
        "required": True,
        "show_when": "always",
    },
    {
        "id": "judgement",
        "kind": "text",
        "prompt": "你为什么做出这个判断？",
        "options": [],
        "allow_other": False,
        "placeholder": "说明你为什么接受、拒绝或调整了建议与反馈。",
        "required": True,
        "show_when": "always",
    },
    {
        "id": "next_step",
        "kind": "text",
        "prompt": "下一次你准备怎么做？",
        "options": [],
        "allow_other": False,
        "placeholder": "为下一次作业写下一项具体行动。",
        "required": True,
        "show_when": "always",
    },
]


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
                "Profile evidence schema 2026-09-14.1 replaces the fixed reflection "
                "with teacher-defined questions, so snapshots captured under "
                "2026-09-08.1 no longer validate. Clear the profile evidence tables "
                "before upgrading: " + ", ".join(_EVIDENCE_TABLES)
            )


def _convert_legacy_reflection(ai_used: bool, help_types: list, legacy: dict) -> dict:
    items = []
    for question in _LEGACY_QUESTIONS:
        if question["show_when"] == "ai_used" and not ai_used:
            continue
        item = {**question, "selected": [], "other_text": None, "text": None}
        if question["id"] == "ai_help":
            item["selected"] = [
                _LEGACY_HELP_TYPE_LABELS[help_type]
                for help_type in help_types
                if help_type in _LEGACY_HELP_TYPE_LABELS
            ]
            if "Other" in help_types:
                item["other_text"] = legacy.get("other_ai_help") or None
        else:
            item["text"] = legacy.get(question["id"]) or None
        items.append(item)
    return {"items": items}


def upgrade() -> None:
    connection = op.get_bind()
    _require_empty_profile_evidence(connection)

    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "reflection_questions",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
    connection.execute(
        sa.text("UPDATE assignment SET reflection_questions = :questions"),
        {"questions": json.dumps(_LEGACY_QUESTIONS, ensure_ascii=False)},
    )

    rows = connection.execute(
        sa.text(
            "SELECT id, ai_used, ai_help_types, reflection_json FROM micro_reflection"
        )
    ).fetchall()
    for row in rows:
        converted = _convert_legacy_reflection(
            bool(row.ai_used),
            json.loads(row.ai_help_types or "[]"),
            json.loads(row.reflection_json or "{}"),
        )
        connection.execute(
            sa.text("UPDATE micro_reflection SET reflection_json = :value WHERE id = :id"),
            {"value": json.dumps(converted, ensure_ascii=False), "id": row.id},
        )

    with op.batch_alter_table("micro_reflection", schema=None) as batch_op:
        batch_op.drop_column("ai_help_types")


def downgrade() -> None:
    """不提供回退。

    教师自定义的题目没法无损压回四个固定字段,回退只会丢学生写过的回答。
    """

    raise NotImplementedError("Teacher-defined reflection questions stay")
