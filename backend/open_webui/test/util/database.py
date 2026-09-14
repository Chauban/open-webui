"""Throwaway databases for backend tests, built by the real Alembic migrations.

表结构一律由迁移生成，不用 ORM 的 create_all/table.create：生产库是迁移建的，
测试库也必须是，否则迁移与模型的类型不一致（如 2026-09-14 质疑列建成 json
导致生产 500）永远测不出来。

默认用 SQLite。设置 TEST_DATABASE_URL 指向一个 PostgreSQL 服务器（需有建库
权限，库名部分任意）即切到 PostgreSQL，与生产同方言：

    docker run -d --name rightwrite-test-pg -e POSTGRES_PASSWORD=postgres \
        -p 127.0.0.1:5433:5432 --tmpfs /var/lib/postgresql/data postgres:16 -c fsync=off
    $env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5433/postgres"

每个进程只迁移一次到模板库，之后每个测试从模板复制一份（SQLite 复制文件，
PostgreSQL 用 CREATE DATABASE ... TEMPLATE），测试结束即删。
"""

import atexit
import os
import asyncio
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[3]

_template: str | None = None


def _server_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or None


# psycopg 异步模式不支持 Windows 默认的 ProactorEventLoop（生产是 Linux，无此问题）
if sys.platform == "win32" and _server_url():
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _run_migrations(database_url: str) -> None:
    import open_webui.env as env

    config = Config(str(BACKEND_ROOT / "open_webui" / "alembic.ini"))
    config.set_main_option(
        "script_location", str(BACKEND_ROOT / "open_webui" / "migrations")
    )
    # migrations/env.py 每次运行都从 open_webui.env 读 DATABASE_URL
    original = env.DATABASE_URL
    env.DATABASE_URL = database_url
    try:
        command.upgrade(config, "head")
    finally:
        env.DATABASE_URL = original


def _admin_engine(server_url: str):
    return create_engine(server_url, isolation_level="AUTOCOMMIT")


def _database_url(server_url: str, name: str) -> str:
    return make_url(server_url).set(database=name).render_as_string(
        hide_password=False
    )


def _drop_pg_database(server_url: str, name: str) -> None:
    engine = _admin_engine(server_url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        engine.dispose()


def _ensure_template() -> str:
    """Migrate a template database once per process; return its name or path."""

    global _template
    if _template is not None:
        return _template

    server_url = _server_url()
    if server_url:
        name = f"rightwrite_test_template_{os.getpid()}"
        _drop_pg_database(server_url, name)
        engine = _admin_engine(server_url)
        try:
            with engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
        finally:
            engine.dispose()
        atexit.register(_drop_pg_database, server_url, name)
        _run_migrations(_database_url(server_url, name))
        _template = name
    else:
        template_dir = Path(tempfile.mkdtemp(prefix="rightwrite-test-"))
        atexit.register(shutil.rmtree, template_dir, True)
        path = template_dir / "template.db"
        _run_migrations(f"sqlite:///{path.as_posix()}")
        _template = str(path)
    return _template


@contextmanager
def migrated_database() -> Iterator[str]:
    """Yield the sync URL of a fresh database migrated to head."""

    template = _ensure_template()
    server_url = _server_url()
    if server_url:
        name = f"rightwrite_test_{uuid.uuid4().hex}"
        engine = _admin_engine(server_url)
        try:
            with engine.connect() as connection:
                connection.execute(
                    text(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
                )
        finally:
            engine.dispose()
        try:
            yield _database_url(server_url, name)
        finally:
            _drop_pg_database(server_url, name)
    else:
        # Windows 上路由内残留的连接可能还锁着文件，删不掉就留给系统临时目录
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            path = Path(tmpdir) / "test.db"
            shutil.copyfile(template, path)
            yield f"sqlite:///{path.as_posix()}"


def engine_kwargs(database_url: str) -> dict:
    """connect_args the test engines need for this dialect."""

    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}
