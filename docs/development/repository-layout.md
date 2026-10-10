# 仓库结构与同步范围

`open-webui/` 是唯一的代码 Git 仓库。根目录保留工具要求的配置、许可证、项目入口和启动脚本；长文档放入 `docs/`，辅助开发工具放入 `scripts/`。

```text
open-webui/
├── AGENTS.md                  # AI 与开发者共享的工程规范
├── README.md                  # Fork 文档入口与上游项目说明
├── start_backend.bat          # Windows 后端启动入口
├── start_frontend.bat         # Windows 前端启动入口
├── docs/
│   ├── README.md              # 文档索引
│   ├── development/           # 本地开发、Git、同步边界
│   ├── architecture/          # 当前架构
│   ├── product/               # 当前产品规则
│   │   └── sources/           # 原始需求资料
│   ├── deployment/            # 部署实例记录
│   │   └── loadtest/          # 历史压测记录
│   ├── archive/               # 旧需求、计划和会话记录
│   └── superpowers/           # 既有设计与计划
├── scripts/
│   └── loadtest/              # 可复用压测工具
├── deploy/                    # 部署工具与服务器配置副本
├── src/                       # 前端代码
├── backend/                   # 后端代码及本地环境
└── static/                    # 前端静态资源
```

构建配置、包管理清单、Docker 文件和上游脚本仍在工具原来要求的位置。整理文档不搬动应用源码、依赖或构建入口。

## 随仓库同步

- 工程规范、Git 协作约定、启动脚本及开发说明。
- 当前产品规则、架构说明、带状态标注的历史设计。
- 可复用压测脚本及不包含实际凭据的说明。
- 已有品牌静态资源、示例配置与 Pyodide 锁文件。
- `docs/deployment/` 中的两份部署流程和 `docs/product/sources/` 中的需求研讨原文；实际凭据不入库。
- `deploy/` 的部署脚本、服务器配置副本及 `docs/deployment/loadtest/` 的历史压测记录。

## 保留在本地或单独管理

- `.env*`（示例除外）、`backend/.webui_secret_key`、数据库及备份、上传文件和向量库。
- `node_modules/`、虚拟环境、构建产物、下载依赖、缓存和日志。
- 本机路径、私人连接配置、会话记录、工具授权和临时 worktree。
- 外层 `行政/`、`哈工深批注/` 中的真实资料、签字文件和运行产物。
- 外层 `VI/`、平台手册、截图及 `deprecated-by-human/`。它们本次未纳入代码仓库；以后按复用价值、隐私和授权逐项筛选。
- `.codex/`、`.claude/` 外层配置本次仍保留在本地；需要共享时单独审核，不整目录加入。

外层重复文档入口已删除，文档统一从仓库的 `docs/README.md` 查找。外层保留完整 `CLAUDE.md`、要求读取仓库规范的 `AGENTS.md`，以及调用仓库同名脚本的两个启动入口。不要在外层恢复第二份文档或启动逻辑。

## 整理记录（2026-10-09）

- 将 `AGENTS.md` 纳入仓库，并把教学架构与产品规则拆到 `docs/product/education.md`。
- 外层原有完整 `CLAUDE.md` 保留在原位置；Git 和本地开发文档在 `docs/development/` 维护。
- 8 份旧文档进入 `docs/archive/`，保留原文并明确历史状态。
- 3 个压测脚本进入 `scripts/loadtest/`；原来的实例测量结果仍留在外层 `loadtest/执行状态.md`。
- 删除外层 10 个已迁移文档的跳转文件和 `loadtest/README.md` 跳转文件；实例历史说明及执行状态保留。
- 两份部署流程移入 `docs/deployment/`，`哈工深需求.txt` 移入 `docs/product/sources/`，原文保持不变，外层不保留副本。
- 维护和提交以仓库文件为准；外层入口、私人资料和运行状态仍不会自动推送。

## 后续整理（2026-10-10）

- 外层 `deploy/` 迁入仓库同名目录，本地入口改为直接定位本仓库。
- 外层 `loadtest/` 剩余两份记录移入 `docs/deployment/loadtest/`，可执行压测工具继续在 `scripts/loadtest/`。
- 两个外层目录迁空后移除；实际密钥、SSH 配置、环境文件及数据库不入库。
