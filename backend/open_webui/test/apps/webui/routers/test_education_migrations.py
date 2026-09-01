from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import open_webui.env as app_env

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
    "student_profile_snapshot",
    "writing_session",
    "writing_version",
}


def test_fresh_database_upgrades_to_head(tmp_path, monkeypatch):
    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "fresh-education.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(app_env, "DATABASE_URL", database_url)

    config = Config(str(backend_dir / "open_webui" / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "open_webui" / "migrations"))
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
        assert {"round_no", "is_current"} <= {column["name"] for column in schema.get_columns("submission")}
        assert "resubmit_due_at" in {column["name"] for column in schema.get_columns("submission_review")}
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
        snapshot_columns = {
            column["name"]
            for column in schema.get_columns("student_profile_snapshot")
        }
        assert {
            "submission_id",
            "student_id",
            "assignment_id",
            "round_no",
            "submitted_at",
            "metric_version",
            "snapshot_json",
        } <= snapshot_columns
    finally:
        engine.dispose()
