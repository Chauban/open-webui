"""Preserve the scoring standard of each published review.

Existing valid reviews take their original standard from immutable evidence.
Missing evidence aborts the migration; no grades or submission facts are changed.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = 'c9e1a3b587d0'
down_revision = 'b8d0f2a476c9'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    events = []
    latest = {}
    for row in connection.execute(
        sa.text(
            'SELECT r.id, r.submission_id, r.review_revision, e.evidence_json '
            'FROM submission_review_event r LEFT JOIN profile_evidence_snapshot e '
            'ON e.id = r.evidence_snapshot_id ORDER BY r.review_revision'
        )
    ).mappings():
        if row['evidence_json'] is None:
            raise RuntimeError('Review scoring migration requires the original submission evidence')
        evidence = json.loads(row['evidence_json'])
        assignment = evidence['assignment']
        rubric = assignment['rubric_schema']
        maximum = assignment['score_max']
        if maximum <= 0 or (rubric['criteria'] and sum(c['max_score'] for c in rubric['criteria']) != maximum):
            raise RuntimeError('Review scoring migration found invalid original scoring settings')
        scoring = json.dumps(
            {
                'scoring_mode': 'dimensions' if rubric['criteria'] else 'total',
                'score_max': maximum,
                'rubric_schema': rubric,
            },
            ensure_ascii=False,
        )
        events.append({'id': row['id'], 'scoring': scoring})
        latest[row['submission_id']] = scoring
    reviews = []
    for row in connection.execute(sa.text('SELECT id, submission_id FROM submission_review')).mappings():
        if row['submission_id'] not in latest:
            raise RuntimeError('Review scoring migration requires a review event for every review')
        reviews.append({'id': row['id'], 'scoring': latest[row['submission_id']]})

    for name, rows in [('submission_review', reviews), ('submission_review_event', events)]:
        op.add_column(name, sa.Column('scoring_config', sa.Text(), nullable=True))
        if rows:
            connection.execute(sa.text(f'UPDATE {name} SET scoring_config=:scoring WHERE id=:id'), rows)
        with op.batch_alter_table(name) as batch:
            batch.alter_column('scoring_config', existing_type=sa.Text(), nullable=False)


def downgrade():
    for name in ('submission_review_event', 'submission_review'):
        with op.batch_alter_table(name) as batch:
            batch.drop_column('scoring_config')
