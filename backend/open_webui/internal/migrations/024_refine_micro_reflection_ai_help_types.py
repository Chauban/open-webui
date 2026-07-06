"""Peewee migrations -- 024_refine_micro_reflection_ai_help_types.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    migrator.sql("DROP TABLE IF EXISTS micro_reflection")
    migrator.sql(
        "CREATE TABLE micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_help_types TEXT NOT NULL, "
        "reflection_text TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    migrator.sql("DROP TABLE IF EXISTS micro_reflection")
    migrator.sql(
        "CREATE TABLE micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_help_type TEXT NOT NULL, "
        "reflection_text TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )
