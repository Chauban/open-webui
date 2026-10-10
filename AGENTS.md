# Repository Guidelines

> 更新日期：2026-10-09。按当前 `open-webui/main` 的实际代码核对，重点覆盖 2026-09-23 至 2026-10-06 的更新；功能与命令以代码为准。

## Project Context & Repository Boundary

- 产品是 **Right Write 成长写作教学平台**，基于 Open WebUI v0.11.2 的定制 Fork；主要工作是本地功能开发，不要把普通功能修改扩展成 Docker 或生产部署任务。
- 工作区根目录 `right_chat/` **不是 Git 仓库**；实际仓库是 `open-webui/`，常规工作分支为 `main`。Git 命令必须在实际仓库内执行。
- `origin`：`https://github.com/Chauban/open-webui.git`；`upstream`：`https://github.com/open-webui/open-webui.git`。核对本项目同步状态应比较 `origin`，官方更新仅按任务需要选择性引入。
- 本文件、`docs/` 中的协作资料和仓库根目录 `start_*.bat` 纳入版本管理。外层工作区仅保留原有完整 `CLAUDE.md`、`AGENTS.md` 指引和两个启动入口；已迁入仓库的重复文档入口已删除。个人资料及实例状态不随代码同步。不要把“仓库已同步”描述成“整个工作区已同步”。
- 当前产品需求、规则、Userflow 和待办在 `docs/product/` 持续维护；`docs/archive/` 仅保留已结束、被替代或固定时期的资料。先核对旧内容，不因日期早就自动归档，也不依据旧方案恢复已删除的接口或页面。

##【代码重构与优化原则：绝对的向前看】
在接下来的代码编写和架构优化中，请完全从“产品与功能的最优实现”角度出发，绝对不要考虑任何开发期历史脏数据的兼容问题。
请严格执行以下工程策略：

- 拒绝兼容逻辑：不要为了兼容过去的结构变更或坏数据，而增加任何额外的 if/else 脏数据处理逻辑。保持代码的极致简洁。

- 拒绝自动修复：不需要设计或编写任何“历史数据自动补建”机制。

- 暴力清理原则：默认历史坏数据直接删除或废弃，一切以最新的数据结构为准。

- 严格收缩边界：从现在的代码开始，彻底收严数据模型边界和类型校验，确保新逻辑的纯洁性和严谨性。

- 不保留旧接口、旧页面、旧数据兼容

## Project Structure & Module Organization

这个工作区以 `open-webui/` 为中心。

- `src/`：Svelte 5 / SvelteKit 2、TypeScript、Tailwind CSS 4 前端（`routes/`、`lib/components/`、`lib/apis/`、`lib/stores/`）。
- `backend/open_webui/`：FastAPI 后端（路由、模型、存储、内部服务）。
- `backend/open_webui/services/education/`：教学业务服务，详见 `docs/product/education.md`；不要把业务计算持续堆进路由。
- `backend/open_webui/migrations/versions/`：Alembic 迁移，教学表结构也由这里管理，禁止运行时建表、补列或回填。
- `backend/open_webui/test/apps/webui/routers/`：教学、身份、邮箱和权限相关 pytest；前端测试就近放在组件或工具函数旁（`*.test.ts`、`*.dom.test.ts`）。
- `scripts/`：增量类型检查、Pyodide 准备、后端 Python 测试入口等开发脚本。
- `static/` 与 `backend/open_webui/static/`：前端静态资源与后端静态资源；后端品牌资源不是可随意清理的构建垃圾。
- `package.json` 保留 `cy:open` 命令，但当前仓库没有 `cypress/` 目录；不要把不存在的 E2E 规格当成现成测试。

## Education Architecture & Current Product Rules

开始教学功能任务时还需阅读 [当前 PRD](docs/product/PRD.md) 和 [当前任务清单](docs/product/教学模块开发任务清单.md)，区分当前待办、待确认候选、已完成和已废弃条目。

修改教学业务前，必须阅读 [教学模块当前架构与产品规则](docs/product/education.md) 和 [教学模块 Userflow](docs/product/教学模块Userflow.md)，并遵守身份、权限、任务模式、冻结证据和投影边界。涉及教学页面、接口或状态流转的功能变化时，同步更新 Userflow 的相关章节；它是持续维护的开发文档，不作为历史资料归档。画像实现细节见 [PROFILE_PROJECTIONS.md](backend/open_webui/services/education/PROFILE_PROJECTIONS.md)。

## Build, Test, and Development Commands

除非另有说明，否则请在 `open-webui/` 目录下运行命令。

- `npm run dev:5050`：在固定的 5050 端口启动前端开发服务器（会先拉取 Pyodide）。
- `npm run build`：构建前端生产版本。
- `npm run preview`：预览已构建的前端。
- `npm run check` / `npm run check:full`：增量类型检查 / 完整 Svelte 类型检查。
- `npm run lint`：运行 ESLint、类型检查以及后端 pylint。
- `npm run format` / `npm run format:backend`：格式化前端（Prettier）/ 后端（Ruff）。
- `npm run test:frontend -- --run`：运行 Vitest 后退出；只测指定文件时追加文件路径。
- `npm run test:education`：通过 `scripts/run-backend-python.js` 使用项目虚拟环境运行 `backend/open_webui/test/apps/webui/routers`。
- `backend\.venv\Scripts\python.exe -m pytest backend/open_webui/test`：Windows 下运行后端测试；不要误用系统 Python 或仓库根目录另一份虚拟环境。
- `npm run i18n:parse`：提取并格式化翻译词条；界面改动注意 `zh-CN` 与 `en-US` 文案，别向学生展示内部算法版本和实现细节。
- Docker / Makefile 命令只用于明确要求的容器任务；本地开发用下文两个启动脚本。

## Coding Style & Naming Conventions

- 前端格式由 Prettier 强制约束：使用制表符、单引号、不保留尾随逗号、`printWidth: 100`。
- 已启用 ESLint + TypeScript + Svelte 规则；在提交 PR 之前请修复相关问题。
- Python 代码使用 Ruff 格式化，并通过相关 pylint 检查。
- 命名规范：
  - Svelte 路由遵循 SvelteKit 约定（`+page.svelte`、`+layout.svelte`）。
  - Cypress 规格文件使用 `*.cy.ts`。
  - Python 测试使用 `test_*.py`。

## Testing Guidelines

- 测试应尽量放在对应功能区域附近（`backend/open_webui/test/...`、`src/lib/components/...`、`src/lib/utils/...`）；新增 E2E 测试时先建立实际测试目录与配置。
- 在提交前，为行为变更新增或调整测试。
- 至少运行 `npm run test:frontend -- --run`，以及与你修改过的后端模块相关的 `pytest` 范围测试。
- 教学数据库测试由 `test/util/database.py` 执行真实 Alembic 迁移生成，不用 ORM `create_all` 替代迁移。
- 修改迁移、列类型、数据库约束或 SQL 时，除 SQLite 外必须在 PostgreSQL 上跑相关测试；设置 `TEST_DATABASE_URL` 指向可建库的专用测试服务，测试会复制模板并删除临时测试库，严禁指向生产库。
- 教学相关测试包括 `test_education_smoke.py`、`test_education_migrations.py`、`test_admin_user_classroom_assignment.py`、`test_student_signup_invite_gate.py`、`test_student_memory_denied.py`；账户邮箱变更对应 `test_update_email.py`。
- Windows PowerShell 的 `npm.ps1` 可能吞掉参数分隔符 `--`，使 `--run` 没有传给 Vitest 而进入 watch；使用下面的字面参数命令。当前 Vitest 默认也会发现 `.claude/worktrees/` 内的测试，核查主工作区时应明确排除这些副本。

PowerShell 前端测试（运行后退出，仅检查主工作区）：

```powershell
npm.cmd --% run test:frontend -- --run --exclude .claude/**
```

PowerShell 后端测试示例（从 `open-webui/` 开始，不输出密钥）：

```powershell
$env:WEBUI_SECRET_KEY = (Get-Content backend\.webui_secret_key -Raw).Trim()
npm run test:education
# 运行指定文件：
backend\.venv\Scripts\python.exe -m pytest backend/open_webui/test/apps/webui/routers/test_education_smoke.py -q
# PostgreSQL 测试服务已就绪时：
$env:TEST_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/postgres'
npm run test:education
```

## Commit & Pull Request Guidelines

- 提交格式：`<type>: <subject>`（例如：`fix: 修复登录重定向逻辑`）。
- 推荐类型：`feat`、`fix`、`refactor`、`style`、`docs`、`chore`、`perf`、`remove`。
- 项目约定要求使用中文提交信息，采用祈使语气，主题简洁明确。
- 常规工作流中不要使用 `git commit --amend` 或强制推送。
- PR 应遵循仓库模板，包含清晰的修改范围、关联的 issue/讨论、测试证据，以及在需要时补充文档更新。
- 检查 GitHub 同步时先 `git fetch origin --prune`，再核对 `git status --short --branch`、`git rev-list --left-right --count HEAD...origin/main` 和 `git ls-remote origin refs/heads/main`；远端跟踪引用未刷新时不能当作实时证据。
- 同时核查 `git worktree list` 中的其他工作区、未跟踪文件与本地分支独有提交。旧分支落后于 main 不等于代码遗漏；需确认其提交是否已包含在 main 中，不自动删除分支或工作区。

## Security & Config Tips

- 不要提交密钥或本地状态文件（`.env*`、`*.db`、`.webui_secret_key`、`node_modules/`、`.venv/`）。
- 项目级 `.codex/config.toml` 只能保存非敏感配置；令牌、API Key 和密码必须来自项目目录之外的用户环境或密钥管理器。
- 漏洞请通过 GitHub Security 报告渠道提交，不要在公开 issue 中披露。

## Troubleshooting Priority

When debugging runtime issues involving models, chat, education roles, or student/teacher/admin behavior, first verify whether an administrator setting or role permission controls the behavior before changing code.

- Check admin feature switches and permissions first, especially direct connections, model visibility/public access, access control, and role-scoped capabilities.
- For AI chat failures, inspect the browser Network target early: requests should normally go to local backend routes such as `/api/...`; browser requests directly to external model providers usually indicate a direct-connection setting and may fail due to CORS.
- Treat admin configuration and current user role as part of the root-cause data flow before diagnosing frontend, proxy, Socket.IO, or backend implementation defects.
- Vite 代理见 `vite.config.ts`，默认转发到 8080（可用 `WEBUI_BACKEND_URL` 指定）。先核对实际浏览器 Origin、代理目标与后端 CORS，再调整代码。
- 启用 WebSocket 时断线使用 Socket.IO 自身重连，不人为降级到 polling；多 worker 无粘性会话时 polling 会反复 400。
- 账户设置已支持自助改登录邮箱（`POST /api/v1/auths/update/email`）；排查登录/邮箱变更时核对密码验证、重复邮箱和当前登录身份。

## Local Development Startup

When the user asks to start local development, use the two repository-root launchers. The outer workspace launchers delegate to these files. They are the canonical startup entry points and each opens in its own terminal window:

1. `start_backend.bat`：后端 8080；首次运行生成 `backend/.webui_secret_key`，之后自动加载 `WEBUI_SECRET_KEY` 与本地 CORS 白名单。
2. `start_frontend.bat`：前端 5050；内部执行 `npm run dev:5050`。

启动后访问 `http://localhost:5050`，验证：

```powershell
curl.exe -i --connect-timeout 2 http://localhost:5050/
curl.exe -i --connect-timeout 2 http://localhost:8080/health
```

手动启动时，两个 PowerShell 终端应执行与脚本等价的命令；以下均从仓库根目录开始。

Backend terminal（从仓库根目录开始）：

```powershell
cd .\backend
if (-not (Test-Path .webui_secret_key)) {
    .venv\Scripts\python.exe -c "import base64,os;open('.webui_secret_key','w').write(base64.b64encode(os.urandom(48)).decode())"
}
$env:WEBUI_SECRET_KEY = (Get-Content .webui_secret_key -Raw).Trim()
$env:CORS_ALLOW_ORIGIN = 'http://localhost:5050;http://localhost:5051;http://localhost:5173;http://localhost:8080;http://127.0.0.1:5050;http://127.0.0.1:5051;http://127.0.0.1:5173;http://127.0.0.1:8080'
$env:DEFAULT_LOCALE = 'zh-CN'
.venv\Scripts\python.exe -m uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --reload
```

Frontend terminal（从仓库根目录开始）：

```powershell
npm run dev:5050
```

不要用 `npm run dev`（5173）替代固定端口命令；不要绕过 `.webui_secret_key` 裸启后端。除非用户明确要求，不要创建新的后台启动器、隐藏进程或日志重定向包装层。

Windows 上不要用 `bash dev.sh`（本机无可用 WSL），不要为本地 uvicorn 添加 `--forwarded-allow-ips "*"`。后端使用 `backend\.venv`，默认 SQLite 在 `backend/data/webui.db`，首次启动由 Alembic 管理表结构。

## Reference Documents

- [文档索引](docs/README.md)：当前文档、历史资料与目录边界。
- [本地开发](docs/development/local-development.md)：环境准备、启动与排障。
- [Git 协作规范](docs/development/git-workflow.md)：分支、提交、同步状态检查。
- [仓库与同步范围](docs/README.md#仓库与同步范围)：哪些文件入库、哪些留在本地。
- [当前架构与教学规则](docs/product/education.md)。
- [当前 PRD](docs/product/PRD.md) 与 [当前开发任务](docs/product/教学模块开发任务清单.md)：持续维护，已完成和冲突项见开发记录。
- [教学模块 Userflow](docs/product/教学模块Userflow.md)：持续维护的学生与教师完整流程。
- [压测工具](scripts/loadtest/README.md)：仅在明确要求压测时使用。
- [历史资料](docs/archive/README.md)：旧需求、计划和交接，不代表当前实现。
- [部署工具](deploy/README.md) 与 [历史压测记录](docs/archive/压测记录.md)：旧测量结果不代表当前承载能力。
- [需求原始资料与用途说明](docs/README.md#需求来源与历史资料)：研讨原文用于追溯，不代表当前待办。
- 外层工作区的课程批注材料、行政资料和品牌源素材按需读取；普通功能开发不因此扩展成生产部署任务。
