"""Merge teaching standards into the single editable coaching prompt.

Only configuration storage and assignment snapshots change representation.
Submitted evidence, reading records and chat histories remain untouched.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = 'e8f0a2b4c6d9'
down_revision = 'd7e9f1a3b5c8'
branch_labels = None
depends_on = None


def merge_prompt(raw):
    config = json.loads(raw)
    standards = config.pop('standards')
    config['prompt'] = '教学目标与判断标准\n' + standards + '\n\n' + config['prompt']
    return json.dumps(config, ensure_ascii=False)


def upgrade():
    bind = op.get_bind()
    for row in bind.execute(sa.text('SELECT task_mode, version, payload FROM teaching_configuration')).all():
        bind.execute(
            sa.text('UPDATE teaching_configuration SET payload=:payload WHERE task_mode=:mode AND version=:version'),
            {'payload': merge_prompt(row.payload), 'mode': row.task_mode, 'version': row.version},
        )
    for row in bind.execute(sa.text('SELECT id, teaching_config FROM assignment')).all():
        bind.execute(
            sa.text('UPDATE assignment SET teaching_config=:config WHERE id=:id'),
            {'config': merge_prompt(row.teaching_config), 'id': row.id},
        )


def downgrade():
    raise RuntimeError('A unified prompt cannot be split losslessly after editing. Restore a verified backup.')
