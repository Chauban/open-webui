"""Peewee migrations -- 019_add_education_tables.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    class Assignment(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        title = pw.TextField()
        description = pw.TextField(null=True)
        teacher_id = pw.TextField()
        status = pw.TextField(default="active")
        created_at = pw.BigIntegerField()
        updated_at = pw.BigIntegerField()

        class Meta:
            table_name = "assignment"

    class AssignmentMember(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        assignment_id = pw.TextField()
        user_id = pw.TextField()
        member_role = pw.TextField()
        created_at = pw.BigIntegerField()
        updated_at = pw.BigIntegerField()

        class Meta:
            table_name = "assignment_member"

    class WritingSession(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        assignment_id = pw.TextField()
        student_id = pw.TextField()
        note_id = pw.TextField()
        chat_id = pw.TextField()
        status = pw.TextField(default="draft")
        submitted_submission_id = pw.TextField(null=True)
        created_at = pw.BigIntegerField()
        updated_at = pw.BigIntegerField()

        class Meta:
            table_name = "writing_session"

    class WritingVersion(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        writing_session_id = pw.TextField()
        version_no = pw.BigIntegerField()
        note_snapshot_json = pw.TextField(null=True)
        note_snapshot_text = pw.TextField(null=True)
        trigger_type = pw.TextField()
        created_at = pw.BigIntegerField()

        class Meta:
            table_name = "writing_version"

    class ProvenanceSegment(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        writing_session_id = pw.TextField()
        version_id = pw.TextField(null=True)
        source_type = pw.TextField()
        source_message_id = pw.TextField(null=True)
        segment_id = pw.TextField()
        segment_text = pw.TextField()
        start_offset = pw.BigIntegerField(null=True)
        end_offset = pw.BigIntegerField(null=True)
        metadata_json = pw.TextField(null=True)
        created_at = pw.BigIntegerField()

        class Meta:
            table_name = "provenance_segment"

    class MicroReflection(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        assignment_id = pw.TextField()
        student_id = pw.TextField()
        writing_session_id = pw.TextField()
        ai_help_type = pw.TextField()
        reflection_text = pw.TextField()
        created_at = pw.BigIntegerField()

        class Meta:
            table_name = "micro_reflection"

    class Submission(pw.Model):
        id = pw.TextField(primary_key=True, unique=True)
        assignment_id = pw.TextField()
        student_id = pw.TextField()
        writing_session_id = pw.TextField()
        final_version_id = pw.TextField()
        stats_json = pw.TextField()
        micro_reflection_id = pw.TextField()
        submitted_at = pw.BigIntegerField()

        class Meta:
            table_name = "submission"

    for model in [
        Assignment,
        AssignmentMember,
        WritingSession,
        WritingVersion,
        ProvenanceSegment,
        MicroReflection,
        Submission,
    ]:
        model._meta.database = database
        migrator.orm.add(model)

    migrator.sql(
        "CREATE TABLE IF NOT EXISTS assignment ("
        "id TEXT PRIMARY KEY, "
        "title TEXT NOT NULL, "
        "description TEXT NULL, "
        "teacher_id TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'active', "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )
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
        "CREATE TABLE IF NOT EXISTS writing_session ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "note_id TEXT NOT NULL, "
        "chat_id TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'draft', "
        "submitted_submission_id TEXT NULL, "
        "created_at BIGINT NOT NULL, "
        "updated_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS writing_version ("
        "id TEXT PRIMARY KEY, "
        "writing_session_id TEXT NOT NULL, "
        "version_no BIGINT NOT NULL, "
        "note_snapshot_json TEXT NULL, "
        "note_snapshot_text TEXT NULL, "
        "trigger_type TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS provenance_segment ("
        "id TEXT PRIMARY KEY, "
        "writing_session_id TEXT NOT NULL, "
        "version_id TEXT NULL, "
        "source_type TEXT NOT NULL, "
        "source_message_id TEXT NULL, "
        "segment_id TEXT NOT NULL, "
        "segment_text TEXT NOT NULL, "
        "start_offset BIGINT NULL, "
        "end_offset BIGINT NULL, "
        "metadata_json TEXT NULL, "
        "created_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS micro_reflection ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "ai_help_type TEXT NOT NULL, "
        "reflection_text TEXT NOT NULL, "
        "created_at BIGINT NOT NULL)"
    )
    migrator.sql(
        "CREATE TABLE IF NOT EXISTS submission ("
        "id TEXT PRIMARY KEY, "
        "assignment_id TEXT NOT NULL, "
        "student_id TEXT NOT NULL, "
        "writing_session_id TEXT NOT NULL, "
        "final_version_id TEXT NOT NULL, "
        "stats_json TEXT NOT NULL, "
        "micro_reflection_id TEXT NOT NULL, "
        "submitted_at BIGINT NOT NULL)"
    )

    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS assignment_member_assignment_user_idx "
        "ON assignment_member (assignment_id, user_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS writing_session_assignment_student_idx "
        "ON writing_session (assignment_id, student_id)"
    )
    migrator.sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS provenance_segment_session_segment_idx "
        "ON provenance_segment (writing_session_id, segment_id)"
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    for table_name in [
        "submission",
        "micro_reflection",
        "provenance_segment",
        "writing_version",
        "writing_session",
        "assignment_member",
        "assignment",
    ]:
        migrator.sql(f"DROP TABLE IF EXISTS {table_name}")
