"""Peewee migrations -- 023_add_assignment_archived_at.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    with suppress(Exception):
        database.execute_sql("ALTER TABLE assignment ADD COLUMN archived_at BIGINT")


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    with suppress(Exception):
        database.execute_sql("ALTER TABLE assignment DROP COLUMN archived_at")
