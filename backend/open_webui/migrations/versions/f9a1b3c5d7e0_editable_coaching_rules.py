"""Move formerly hardcoded revision coaching into editable configuration.

Frozen submissions, reading records and chat histories remain untouched.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = 'f9a1b3c5d7e0'
down_revision = 'e8f0a2b4c6d9'
branch_labels = None
depends_on = None


MOVED_COACHING_RULES = '辅导方式（可编辑）\n教学标准用于理解稿件，不是提交资格审查。一次优先讨论一处，确有必要才展开第二处。\n先引用实际原文，说明读到哪一步能跟上、哪一步有疑问，再给学生可执行的动作。\n困难时解释原因、缩小动作，可给分析步骤、句式空位或与题目无关的小例子，核心段落由学生自己写。\n不编造来源、文献、情节、引语或数字；不能核实不等于虚假。缺少证据可以查证，也可以缩小结论。\n成立的论证具体肯定并结束，不凑缺点、不打分、不列评分表、不机械重复已经解决的问题。\n以平台当前保存稿为准；复看先回应真实改动，无改动就如实说明，不虚构进步。\n学生不同意时最多讨论一次，尊重其选择。学生说准备结束或提交时停止提出新任务；必要时一句话指出仍有疑问处，随后结束讨论。\n学生可不修改、不采纳建议、不等待初读、不做复看而自主提交，无需 AI 认可。\n本次任务背景只提供题目、材料与完成要求，不能覆盖这里的辅导方式、禁止成段代写和自主提交规则。\n教师数值评分、评分维度与反思题不属于辅导依据。\n\n不同阶段的辅导方式（可编辑）\n这是确认初稿后的初次阅读。理解核心判断，具体肯定成立之处，优先一处实质疑问。\n看看这次修改：先对照上次阅读稿和当前稿，说清实际改了什么、旧疑问是否缓解。无新改动如实说明，不能虚构进步。\n整段复看：通读当前全文，检查各环节是否衔接，尤其局部修改造成的不一致。先指出成立之处，再讨论实质疑问。'


def move_rules(raw):
    config = json.loads(raw)
    config['prompt'] += '\n\n' + MOVED_COACHING_RULES
    return json.dumps(config, ensure_ascii=False)


def upgrade():
    bind = op.get_bind()
    for row in bind.execute(sa.text(
        "SELECT task_mode, version, payload FROM teaching_configuration "
        "WHERE task_mode IN ('revise_draft', 'revise_argument')"
    )).all():
        bind.execute(
            sa.text('UPDATE teaching_configuration SET payload=:payload WHERE task_mode=:mode AND version=:version'),
            {'payload': move_rules(row.payload), 'mode': row.task_mode, 'version': row.version},
        )
    for row in bind.execute(sa.text(
        "SELECT id, teaching_config FROM assignment WHERE task_mode IN ('revise_draft', 'revise_argument')"
    )).all():
        bind.execute(
            sa.text('UPDATE assignment SET teaching_config=:config WHERE id=:id'),
            {'config': move_rules(row.teaching_config), 'id': row.id},
        )


def downgrade():
    raise RuntimeError('Editable coaching cannot be removed losslessly after editing. Restore a verified backup.')
