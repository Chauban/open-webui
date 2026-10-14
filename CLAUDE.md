# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本文件是仓库内维护并随 Git 同步的 Claude Code 指引；工程规范以 [AGENTS.md](AGENTS.md) 为准，当前资料从 [文档索引](docs/README.md) 查找。外层工作区的 `CLAUDE.md` 仅保留入口，不维护另一份完整内容。

## Project Context

我的需求是，你协助我一起更改优化 open-webui 这个开源 LLM 网页项目（同时选择性追踪这个项目的更新）。
我们是在电脑本地进行开发，网站的前后端会随着代码的更新而热更新。当你给我进行网站的功能性修改或者优化时，不要往 Docker 或者部署方面考虑。

- 本文件所在的 `open-webui/` 是 Git 仓库根目录；代码位于本目录内的 `src/`、`backend/` 等目录。外层工作区 `right-write/` 不是 Git 仓库。下文路径和命令均相对于本仓库根目录。
- 这是官方 open-webui 的 Fork：`origin` → https://github.com/Chauban/open-webui.git，`upstream` → 官方仓库。**当前基于 v0.11.2，工作分支为 `main`**。2026-09-03 完成收线：`upgrade/0.11.2` 快进合入 `main` 并推送（`6f79fbbf2`），该分支已删除。
- Fork 的核心定制是「成长写作教学模块」（education，见下方架构部分）。

## Development Environment (Windows 11, 无可用 WSL)

**启动方式（推荐）**：双击本仓库根目录的两个脚本，各占一个窗口：
1. `start_backend.bat` — 后端，端口 8080（自动生成并加载 `WEBUI_SECRET_KEY`，自动设置 CORS 白名单）
2. `start_frontend.bat` — 前端，端口 5050（内部执行 `npm run dev:5050`）

启动后访问 **http://localhost:5050**；后端健康检查 http://localhost:8080/health（返回 `{"status":true}`）。

**Windows 专属注意事项（违反会直接启动失败或进错项目）**：
- 不要用 `bash dev.sh` 启动后端 —— cmd 里的 `bash` 会调到不可用的 WSL。
- 不要加 `--forwarded-allow-ips "*"` —— Windows 上 `*` 会被展开成文件名导致 uvicorn 报错；本地开发不需要它。
- 前端不要用 `npm run dev`（5173 + `--host`）—— 当其他项目占用 IPv4 的 5173 时，Vite 会静默绑到 IPv6 同号端口，浏览器打开的是别人的项目。固定用 `npm run dev:5050`。
- `WEBUI_SECRET_KEY` 自 v0.9.6 起为硬性要求，保存在 `backend\.webui_secret_key`（已 gitignore）；手动启动时需自行读取该文件设为环境变量。
- socket.io 反复 400 / WebSocket failed：浏览器地址来源不在后端 `CORS_ALLOW_ORIGIN` 白名单里（v0.10 起严格校验 Origin）；新端口需补进 `start_backend.bat` 的 CORS 行并重启后端。
- 不要发明后台启动器、包装脚本或日志重定向启动方式，除非用户明确要求。

手动启动的完整 PowerShell 命令、端口占用处理等详见 [本地开发说明](docs/development/local-development.md)。

**环境**：后端虚拟环境 `backend\.venv`（Python 3.12）；数据库默认 SQLite（`backend\data\webui.db`），首次启动自动执行 Alembic 迁移。

## Common Commands（在本仓库根目录执行）

```bash
npm run build           # 生产构建
npm run check           # 增量类型检查
npm run check:full      # 完整 svelte-check
npm run lint            # ESLint + 类型检查 + pylint
npm run format          # Prettier（前端）
npm run format:backend  # ruff format（后端，注意不是 Black）
npm run test:frontend -- --run  # Vitest，运行后退出；指定文件时追加文件路径
npm run test:education  # pytest 跑 backend/open_webui/test/apps/webui/routers 全部
npm run cy:open         # 保留的 Cypress 入口；当前没有 cypress/ 测试目录
npm run i18n:parse      # 提取 i18n 词条
```

Windows PowerShell 下运行前端测试应使用 `npm.cmd --% run test:frontend -- --run --exclude .claude/**`，避免参数丢失进入 watch，并排除其他工作区副本。

后端测试（PowerShell，在本仓库根目录）：
```powershell
backend\.venv\Scripts\python.exe -m pytest backend/open_webui/test          # 全部
backend\.venv\Scripts\python.exe -m pytest <file>::<test_name> -q           # 单个测试
```

**在 PostgreSQL 上跑测试（生产同方言，改迁移/列类型/SQL 必跑）**：教学测试库一律由 Alembic 迁移生成（`backend/open_webui/test/util/database.py`），默认 SQLite；设 `TEST_DATABASE_URL` 即切到 PG。SQLite 不区分列类型、默认不查外键，只在 SQLite 上全绿不作数。
```powershell
docker start rightwrite-test-pg   # 首次需先建容器，命令见 database.py 文件头；数据在 tmpfs，重启即清空
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5433/postgres"
backend\.venv\Scripts\python.exe -m pytest backend/open_webui/test/apps/webui/routers -q
```
（手动跑 pytest 也要先设 `WEBUI_SECRET_KEY`，取自 `backend\.webui_secret_key`。）

## Architecture

### Frontend — Svelte 5 / SvelteKit 2 + TypeScript + TailwindCSS v4

- **`src/routes/`** — 文件式路由；多数页面在 `(app)/` 下
- **`src/lib/components/`** — 按功能组织的 UI 组件（`chat/`、`admin/`、`layout/`、`channel/`、`common/`、`education/`）
- **`src/lib/stores/index.ts`** — 所有全局 Svelte writable store（`config`、`user`、`models`、`settings`、`chats` 等）
- **`src/lib/apis/`** — 类型化 API 客户端函数，每个后端域一个子目录（如 `chats/`、`models/`、`education/`）
- **`src/lib/utils/`** — 共享工具函数

主应用布局是 `src/routes/(app)/+layout.svelte`：引导 stores、连接 Socket.IO 客户端、渲染 `Sidebar`。

### Backend — FastAPI + SQLAlchemy + Alembic

- **`backend/open_webui/main.py`** — FastAPI 应用，挂载所有路由和中间件
- **`backend/open_webui/routers/`** — 每个域一个文件（`chats.py`、`models.py`、`users.py`、`auths.py`、`knowledge.py`、`education.py` 等）
- **`backend/open_webui/models/`** — SQLAlchemy ORM 模型（同域命名）
- **`backend/open_webui/migrations/versions/`** — Alembic 迁移脚本（教学模块的迁移也全在这里，如 `b2c4d6e8f0a1_education_feedback_loop.py`、`c3e5a7b9d1f2_submission_round_unique.py`；教学表结构一律由 Alembic 负责，代码里不再有运行时建表/补列逻辑）
- **`backend/open_webui/config.py`** — 所有环境变量驱动的配置
- **`backend/open_webui/socket/main.py`** — Socket.IO 服务端（实时事件）

### Data Flow Pattern

前端 `$lib/apis/<domain>/index.ts` → HTTP/WebSocket → FastAPI router → SQLAlchemy model → SQLite（默认）或 PostgreSQL。前端接口请求走 Vite 同源代理转发到 8080（正常应请求 `/api/...`，浏览器直连外部模型服务商通常是管理员「直连」设置导致，并会引发 CORS 报错）。

实时更新（在线用户、流式响应、用量池）走 Socket.IO（前端 `socket.io-client`，后端 `socket/main.py`）。

### 教学模块（Fork 核心定制，成长写作教学）

- **后端**：`routers/education.py` 负责 HTTP/权限/资源装配，`services/education/analysis.py` 负责来源分析与分析缓存，`services/education/profile.py` 负责成长画像，`models/education.py` 负责教育数据模型与仓储方法
- **前端**：`src/lib/apis/education/`、`src/lib/components/education/`；页面路由：教师端 `(app)/teacher/**`（任务、班级、审阅、看板）、学生端 `(app)/me/writing`（写作首页）、`(app)/assignments/[assignmentId]/write`（作业写作工作区）、`(app)/writing/[sessionId]`（个人写作工作区）、邀请链接页 `(app)/join`、引导页 `(app)/education/setup`
- **身份体系**：注册时可选 Teacher/Student，管理员审批并可编辑教学身份；侧边栏按身份显示入口；班级用邀请码加入，**一个学生只能在一个班**（换班：原班老师移出或在本人班级间调班，跨老师由管理员在编辑用户弹窗改班级；提交留在原班，成长画像跟学生走）；作业按班级分发；作业含轮次反馈/退回截止/通知闭环
- 当前需求见 [PRD](docs/product/PRD.md) 和 [开发任务清单](docs/product/教学模块开发任务清单.md)；实现边界见 [教学架构与规则](docs/product/education.md)，双视角完整流程见 [Userflow](docs/product/教学模块Userflow.md)。修改教学业务前阅读这些文档；页面、接口或状态流转变化时同步维护 Userflow。

## Engineering Principles（摘自 AGENTS.md，必须遵守）

- **绝对向前看**：不为历史脏数据写任何兼容逻辑（if/else 兜底、自动补建机制一律不写）；历史坏数据直接删除或废弃，一切以最新的数据结构为准；不保留旧接口、旧页面、旧数据兼容。
- **排障优先级**：涉及模型、聊天、教学身份或各角色行为的运行时问题，先检查管理员设置和角色权限（直连开关、模型可见性/公开访问、访问控制），再排查前端/代理/Socket.IO/后端代码缺陷。AI 聊天失败先看浏览器 Network 面板。

## Git Workflow（详见 [Git 协作规范](docs/development/git-workflow.md)）

- 提交信息用**中文**，格式 `<type>: <subject>`（type：feat/fix/refactor/style/docs/chore/perf/remove），subject ≤ 50 字符，祈使句。
- 不要 `git commit --amend`，不要 force push；相关修改放一个提交，不相关的分开提交。
- 同步本项目时比较 `origin`：先 `git fetch origin --prune`，再核对工作区状态、`HEAD...origin/main`、远端实际提交、其他 worktree、分支和 stash。
- 官方更新仅按任务需要获取并选择性引入；不要自动全量合并 `upstream/main` 或扩展为生产部署。
- 不要提交：`.env*`、`*.db`、`.webui_secret_key`、`node_modules/`、`.venv/`。

## Reference Docs（相对于本仓库根目录）

- [文档索引](docs/README.md) — 当前资料入口、归档边界与同步范围
- [AGENTS.md](AGENTS.md) — 完整仓库工程规范
- [本地开发](docs/development/local-development.md) — 启动细节、环境和常见问题
- [Git 协作](docs/development/git-workflow.md) — 提交、分支与同步核查
- [PRD](docs/product/PRD.md) / [当前开发任务](docs/product/教学模块开发任务清单.md) — 当前产品需求与待办
- [教学架构与规则](docs/product/education.md) — 业务分层、权限与证据边界
- [教学模块 Userflow](docs/product/教学模块Userflow.md) — 学生/教师流程、路由、API 与状态流转
- [部署工具](deploy/README.md) — 仅在明确授权部署时使用；包含现网与哈工深实例文档入口
- [历史资料](docs/archive/README.md) — 旧架构、设计、开发记录和会话快照，不作为当前要求

外层课程材料、行政资料、品牌源素材、截图和个人配置单独管理；密钥、数据库、上传文件、依赖、虚拟环境、构建产物和缓存不入库。不要把“仓库已同步”描述成“整个工作区已备份”。
