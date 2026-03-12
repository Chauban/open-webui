"""Peewee migrations -- 020_add_classroom_tables.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext

def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    class Classroom(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        name = pw.TextField()
        teacher_id = pw.TextField()
        invite_code = pw.TextField(unique=True)
        status = pw.TextField(default="active")
        created_at = pw.BigIntegerField()
        updated_at = pw.BigIntegerField()

        class Meta:
            table_name = "classroom"

    class ClassroomMember(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        classroom_id = pw.TextField()
        user_id = pw.TextField()
        member_role = pw.TextField()
        created_at = pw.BigIntegerField()
        updated_at = pw.BigIntegerField()

        class Meta:
            table_name = "classroom_member"

    for model in [Classroom, ClassroomMember]:
        model._meta.database = database
        migrator.orm.add(model)

    migrator.sql(
        "CREATE TABLE IF NOT EXISTS classroom ("
        "id TEXT PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "teacher_id TEXT NOT NULL, "
        "invite_code TEXT NOT NULL UNIQUE, "
        "status TEXT NOT NULL DEFAULT 'active', "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS classroom_member ("
        "id TEXT PRIMARY KEY, "
        "classroom_id TEXT NOT NULL, "
        "user_id TEXT NOT NULL, "
        "member_role TEXT NOT NULL, "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )

    def add_classroom_id_column():
        try:
            database.execute_sql("ALTER TABLE assignment ADD COLUMN classroom_id TEXT")
        except Exception:
            pass

    migrator.run(add_classroom_id_column)

    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_teacher_idx "
        "ON classroom (teacher_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_member_classroom_user_idx "
        "ON classroom_member (classroom_id, user_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_member_user_idx "
        "ON classroom_member (user_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS classroom_invite_code_idx "
        "ON classroom (invite_code)"
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    def drop_classroom_id_column():
        try:
            database.execute_sql("ALTER TABLE assignment DROP COLUMN classroom_id")
        except Exception:
            pass

    migrator.run(drop_classroom_id_column)
    for table_name in ["classroom_member", "classroom"]:
        migrator.sql(f"DROP TABLE IF EXISTS {table_name}")
