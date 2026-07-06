"""Peewee migrations -- 021_refine_education_classroom_model.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    with suppress(Exception):
        database.execute_sql("DROP INDEX IF EXISTS classroom_teacher_idx")
    with suppress(Exception):
        database.execute_sql("DROP INDEX IF EXISTS classroom_member_user_idx")

    migrator.sql("DROP TABLE IF EXISTS assignment_member")


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS assignment_member ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "user_id TEXT NOT NULL, "
        "member_role TEXT NOT NULL, "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS assignment_member_assignment_user_idx "
        "ON assignment_member (assignment_id, user_id)"
    )
    migrator.sql(
        "CREATE INDEX IF NOT EXISTS classroom_teacher_idx "
        "ON classroom (teacher_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_member_user_idx "
        "ON classroom_member (user_id)"
    )
