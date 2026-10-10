#!/bin/bash
# 预启动初始化：单进程完成「数据库迁移 + 默认配置播种」，然后才允许 worker 启动。
#
# 为什么必须单进程（两个竞态都只在并发时出现，后果都是启动失败）：
#   1) config.py 在 import 末尾触发 run_migrations()，多 worker 并发会撞成事务回滚
#   2) main.py 启动时 seed_registered_defaults() 批量 INSERT config 表，
#      多 worker 并发会撞 config_pkey1 唯一约束
#
# 不能直接调 alembic CLI：migrations/env.py 会反向 import open_webui.config，
# 而 config.py 自身触发迁移，直接调会形成循环导入。
#
# run_migrations() 内部用 except Exception 吞异常，失败时不会抛出，
# 因此下面必须显式比对「数据库版本 == 代码里的最新版本」，否则会带着半迁移的
# schema 静默上线。校验失败即退出非零，systemd 会拒绝启动 worker。
set -euo pipefail
[ -r /opt/rightwrite/rightwrite.env ] && { set -a; . /opt/rightwrite/rightwrite.env; set +a; }
export PYTHONPATH=/opt/rightwrite/app/backend
export HOME=/opt/rightwrite
export ENABLE_DB_MIGRATIONS=true          # 本进程强制开启，覆盖 env 文件里的 false
cd /opt/rightwrite/app/backend

/opt/rightwrite/app/.venv/bin/python - <<'PY'
import asyncio
import open_webui.config as cfg          # import 副作用即执行 run_migrations()
from open_webui.env import OPEN_WEBUI_DIR
from open_webui.internal.db import engine
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

names = set(inspect(engine).get_table_names())
missing = {"config", "user", "auth", "chat", "alembic_version"} - names
if missing:
    raise SystemExit(f"迁移失败 — 缺表: {sorted(missing)}")

# 代码里的最新迁移版本
acfg = AlembicConfig(OPEN_WEBUI_DIR / "alembic.ini")
acfg.set_main_option("script_location", str(OPEN_WEBUI_DIR / "migrations"))
code_head = ScriptDirectory.from_config(acfg).get_current_head()

with engine.connect() as c:
    db_head = c.execute(text("select version_num from alembic_version")).scalar()

if db_head != code_head:
    raise SystemExit(
        f"迁移未到最新 — 数据库在 {db_head}，代码要求 {code_head}。"
        f"请查看上方 alembic 报错，修复后重试；拒绝以旧 schema 启动。"
    )

asyncio.run(cfg.seed_registered_defaults())   # 单进程播种默认配置

with engine.connect() as c:
    rows = c.execute(text("select count(*) from config")).scalar()
print(f"INIT OK — {len(names)} 张表, alembic = {db_head}, config 行数 = {rows}")
PY
