"""Explicit, backed-up maintenance for revision conversations. Never runs on startup."""

import argparse
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan', type=Path, required=True, help='JSON plan to write, or to verify and apply')
parser.add_argument('--apply', action='store_true')
parser.add_argument('--backup', type=Path, help='Verified database backup; required with --apply')
args = parser.parse_args()
if not os.environ.get('DATABASE_URL'):
    parser.error('Set DATABASE_URL explicitly; the default local database is never selected.')
if args.apply and (not args.backup or not args.backup.is_file()):
    parser.error('--apply requires an existing verified --backup file. Stop the instance first.')
os.environ['ENABLE_DB_MIGRATIONS'] = 'False'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from open_webui.internal.db import get_db_context
from open_webui.services.education.single_conversation import consolidation_plan, apply_consolidation

with get_db_context() as db:
    if args.apply:
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        removed = apply_consolidation(db, plan)
        db.commit()
        print(json.dumps({'deleted_conversations': removed, 'workspaces': len(plan)}))
    else:
        plan = consolidation_plan(db)
        args.plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'workspaces': len(plan), 'would_delete': sum(len(row['delete']) for row in plan)}))
