from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect

EDUCATION_TABLES = {
    "analysis_result",
    "assignment",
    "classroom",
    "classroom_member",
    "editor_operation",
    "education_notification",
    "micro_reflection",
    "provenance_segment",
    "submission",
    "submission_review",
    "profile_algorithm_release",
    "profile_evidence_snapshot",
    "profile_metric_projection",
    "profile_projection_run",
    "student_growth_goal",
    "student_profile_aggregate_projection",
    "submission_review_event",
    "teacher_student_note",
    "teacher_student_note_revision",
    "writing_session",
    "writing_version",
}


def _set_database_url(monkeypatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    loaded_env = sys.modules.get("open_webui.env")
    if loaded_env is not None:
        monkeypatch.setattr(loaded_env, "DATABASE_URL", database_url)


def _alembic_config(backend_dir: Path) -> Config:
    config = Config(str(backend_dir / "open_webui" / "alembic.ini"))
    config.set_main_option(
        "script_location", str(backend_dir / "open_webui" / "migrations")
    )
    return config


def test_fresh_database_upgrades_to_head(tmp_path, monkeypatch):
    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "fresh-education.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)

    config = _alembic_config(backend_dir)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        assert EDUCATION_TABLES <= set(schema.get_table_names())
        assert {
            "assignment_id",
            "owner_user_id",
            "scope",
            "folder_id",
            "chat_id",
            "active_chat_id",
        } <= {column["name"] for column in schema.get_columns("writing_session")}
        assert {"round_no", "is_current"} <= {
            column["name"] for column in schema.get_columns("submission")
        }
        assert {"occurred_at_ms", "client_sequence"} <= {
            column["name"] for column in schema.get_columns("editor_operation")
        }
        assert "resubmit_due_at" in {
            column["name"] for column in schema.get_columns("submission_review")
        }
        reflection_columns = {
            column["name"] for column in schema.get_columns("micro_reflection")
        }
        assert {"ai_used", "ai_help_types", "reflection_json"} <= reflection_columns
        assert "reflection_text" not in reflection_columns
        assignment_columns = {
            column["name"] for column in schema.get_columns("assignment")
        }
        assert {"score_max", "rubric_schema"} <= assignment_columns
        review_columns = {
            column["name"] for column in schema.get_columns("submission_review")
        }
        assert "rubric_scores" in review_columns
        assert "rubric_json" not in review_columns
        evidence_columns = {
            column["name"] for column in schema.get_columns("profile_evidence_snapshot")
        }
        assert {
            "submission_id",
            "evidence_revision",
            "evidence_schema_version",
            "student_id",
            "assignment_id",
            "round_no",
            "submitted_at",
            "evidence_json",
            "evidence_hash",
        } <= evidence_columns
        evidence_unique_constraints = schema.get_unique_constraints(
            "profile_evidence_snapshot"
        )
        assert {"submission_id", "evidence_revision"} in [
            set(item["column_names"]) for item in evidence_unique_constraints
        ]
        assert "student_profile_snapshot" not in schema.get_table_names()
        assert {
            "student_id",
            "scope_kind",
            "scope_id",
            "metric_version",
            "aggregate_revision",
            "input_hash",
            "output_hash",
            "aggregate_json",
        } <= {
            column["name"]
            for column in schema.get_columns(
                "student_profile_aggregate_projection"
            )
        }
        analysis_submission_column = next(
            column
            for column in schema.get_columns("analysis_result")
            if column["name"] == "submission_id"
        )
        assert analysis_submission_column["nullable"] is False
        assert {"submission_id"} in [
            set(item["constrained_columns"])
            for item in schema.get_foreign_keys("analysis_result")
        ]
        assert {"student_id", "goal_text", "status", "target_at"} <= {
            column["name"] for column in schema.get_columns("student_growth_goal")
        }
        assert {"teacher_id", "classroom_id", "student_id", "content"} <= {
            column["name"] for column in schema.get_columns("teacher_student_note")
        }
        assert {"note_id", "teacher_id", "content", "action"} <= {
            column["name"]
            for column in schema.get_columns("teacher_student_note_revision")
        }
    finally:
        engine.dispose()


def test_empty_f3_profile_schema_upgrades_without_backfill(tmp_path, monkeypatch):
    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "f3-empty.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "f3b9d6e8a2c4")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        assert "student_profile_snapshot" not in schema.get_table_names()
        assert "profile_evidence_snapshot" in schema.get_table_names()
        assert "profile_metric_projection" in schema.get_table_names()
    finally:
        engine.dispose()


def test_nonempty_legacy_profile_schema_requires_explicit_cleanup(
    tmp_path, monkeypatch
):
    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "f3-nonempty.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "f3b9d6e8a2c4")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO student_profile_snapshot "
                "(id, submission_id, student_id, assignment_id, round_no, "
                "submitted_at, metric_version, snapshot_json, created_at, updated_at) "
                "VALUES ('snapshot', 'submission', 'student', 'assignment', 1, "
                "1, 'legacy', '{}', 1, 1)"
            )
        with pytest.raises(RuntimeError, match="clear education profile data"):
            command.upgrade(config, "head")
    finally:
        engine.dispose()
