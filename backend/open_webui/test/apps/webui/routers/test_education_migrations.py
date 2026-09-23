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
    monkeypatch.setenv("ENABLE_DB_MIGRATIONS", "False")
    loaded_env = sys.modules.get("open_webui.env")
    if loaded_env is not None:
        monkeypatch.setattr(loaded_env, "DATABASE_URL", database_url)
        monkeypatch.setattr(loaded_env, "ENABLE_DB_MIGRATIONS", False)


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
        assert {"ai_used", "reflection_json"} <= reflection_columns
        assert "ai_help_types" not in reflection_columns
        assert "reflection_text" not in reflection_columns
        assignment_columns = {
            column["name"] for column in schema.get_columns("assignment")
        }
        assert {
            "score_max",
            "rubric_schema",
            "reflection_questions",
        } <= assignment_columns
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
        review_event_columns = {
            column["name"]: column
            for column in schema.get_columns("submission_review_event")
        }
        assert review_event_columns["evidence_snapshot_id"]["nullable"] is False
        assert {"evidence_snapshot_id"} in [
            set(item["constrained_columns"])
            for item in schema.get_foreign_keys("submission_review_event")
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


def test_challenge_profile_upgrade_requires_empty_evidence(tmp_path, monkeypatch):
    """证据载荷换了形状，旧快照必须先清掉——升级时拦住，而不是读的时候炸。"""

    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "challenge-profile-nonempty.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "a9f4c2e7b3d1")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO profile_evidence_snapshot "
                "(id, submission_id, evidence_revision, evidence_schema_version, "
                "student_id, assignment_id, round_no, submitted_at, evidence_json, "
                "evidence_hash, created_at) "
                "VALUES ('snapshot', 'submission', 1, '2026-09-03.1', 'student', "
                "'assignment', 1, 1, '{}', '" + "a" * 64 + "', 1)"
            )
        with pytest.raises(RuntimeError, match="intentionally incompatible"):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_challenge_profile_upgrade_passes_on_empty_evidence(tmp_path, monkeypatch):
    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "challenge-profile-empty.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        assert "challenge_session" in set(schema.get_table_names())

        # 修订判定的锚点：每一轮都要存它质疑的原文片段。
        turn_columns = {
            column["name"]: column for column in schema.get_columns("challenge_turn")
        }
        assert turn_columns["quoted_span"]["nullable"] is False

        # 契约页未开始就跳过时没有「被质疑的那一稿」，空是语义正确的状态。
        session_columns = {
            column["name"]: column
            for column in schema.get_columns("challenge_session")
        }
        assert session_columns["source_version_id"]["nullable"] is True
    finally:
        engine.dispose()


def test_quoted_span_upgrade_requires_empty_evidence(tmp_path, monkeypatch):
    """修订判定口径换了，证据载荷跟着换形状，旧快照同样必须先清掉。"""

    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "quoted-span-nonempty.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "b1e6d4a8c3f7")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO profile_evidence_snapshot "
                "(id, submission_id, evidence_revision, evidence_schema_version, "
                "student_id, assignment_id, round_no, submitted_at, evidence_json, "
                "evidence_hash, created_at) "
                "VALUES ('snapshot', 'submission', 1, '2026-09-06.1', 'student', "
                "'assignment', 1, 1, '{}', '" + "a" * 64 + "', 1)"
            )
        with pytest.raises(RuntimeError, match="2026-09-06.2"):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_fixed_reflection_converts_to_teacher_defined_questions(tmp_path, monkeypatch):
    """固定反思转写成题目快照:学生看到的题不变,已写的回答一个字不丢。"""

    import json

    from open_webui.models.education import ReflectionQuestion, ReflectionRecord

    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "reflection-questions.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "d4f6b8a0c2e3")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO assignment "
                "(id, title, teacher_id, status, score_max, coaching_style, "
                "challenge_enabled, challenge_rounds, challenge_focus_keys, "
                "rubric_schema, created_at, updated_at) "
                "VALUES ('assignment', 'Essay', 'teacher', 'active', 100, "
                "'balanced', 0, 3, '[]', '{\"criteria\": []}', 1, 1)"
            )
            legacy = {
                "action": "改写了论点",
                "location": "第二段",
                "judgement": "原来的论证太空泛",
                "next_step": "先核对证据",
                "other_ai_help": "查资料",
            }
            for reflection_id, ai_used, help_types in (
                ("with-ai", 1, ["Outline", "Other"]),
                ("no-ai", 0, []),
            ):
                connection.exec_driver_sql(
                    "INSERT INTO micro_reflection "
                    "(id, assignment_id, student_id, writing_session_id, ai_used, "
                    "ai_help_types, reflection_json, created_at) "
                    "VALUES (?, 'assignment', 'student', 'session', ?, ?, ?, 1)",
                    (
                        reflection_id,
                        ai_used,
                        json.dumps(help_types),
                        json.dumps(
                            legacy if ai_used else {**legacy, "other_ai_help": None},
                            ensure_ascii=False,
                        ),
                    ),
                )

        command.upgrade(config, "head")

        schema = inspect(engine)
        assert "ai_help_types" not in {
            column["name"] for column in schema.get_columns("micro_reflection")
        }
        with engine.connect() as connection:
            questions = json.loads(
                connection.exec_driver_sql(
                    "SELECT reflection_questions FROM assignment"
                ).scalar_one()
            )
            records = {
                row[0]: ReflectionRecord.model_validate(json.loads(row[1]))
                for row in connection.exec_driver_sql(
                    "SELECT id, reflection_json FROM micro_reflection"
                )
            }
        assert [ReflectionQuestion(**question).id for question in questions] == [
            "ai_help",
            "action",
            "location",
            "judgement",
            "next_step",
        ]
        with_ai = records["with-ai"].items
        assert with_ai[0].selected == ["列提纲"]
        assert with_ai[0].other_text == "查资料"
        assert [item.text for item in with_ai[1:]] == [
            "改写了论点",
            "第二段",
            "原来的论证太空泛",
            "先核对证据",
        ]
        # 没用 AI 的学生当时就没被问「AI 帮了什么」,快照里也不该有这道题。
        assert [item.id for item in records["no-ai"].items] == [
            "action",
            "location",
            "judgement",
            "next_step",
        ]
    finally:
        engine.dispose()


def test_single_classroom_per_student_keeps_earliest_membership(tmp_path, monkeypatch):
    """学生曾能同时在多个班:迁移只留最早加入的班,之后再插第二个班直接被索引拦下。"""
    from sqlalchemy.exc import IntegrityError

    backend_dir = Path(__file__).resolve().parents[5]
    database_path = tmp_path / "single-classroom.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config(backend_dir)

    command.upgrade(config, "e7b3d5f9a1c4")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for member_id, classroom_id, user_id, role, created_at in (
                ("late", "class-b", "student", "student", 2),
                ("early", "class-a", "student", "student", 1),
                ("teacher-a", "class-a", "teacher", "teacher", 1),
                ("teacher-b", "class-b", "teacher", "teacher", 1),
            ):
                connection.exec_driver_sql(
                    "INSERT INTO classroom_member "
                    "(id, classroom_id, user_id, member_role, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (member_id, classroom_id, user_id, role, created_at, created_at),
                )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id FROM classroom_member ORDER BY id"
            ).fetchall()
        # 教师带多个班不受影响
        assert [row[0] for row in rows] == ["early", "teacher-a", "teacher-b"]

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO classroom_member "
                    "(id, classroom_id, user_id, member_role, created_at, updated_at) "
                    "VALUES ('again', 'class-b', 'student', 'student', 3, 3)"
                )
    finally:
        engine.dispose()
