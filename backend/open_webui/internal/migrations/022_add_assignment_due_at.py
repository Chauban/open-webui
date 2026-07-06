"""Peewee migrations -- 022_add_assignment_due_at.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    with suppress(Exception):
        database.execute_sql("ALTER TABLE assignment ADD COLUMN due_at BIGINT")


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    with suppress(Exception):
        database.execute_sql("ALTER TABLE assignment DROP COLUMN due_at")
