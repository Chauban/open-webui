> **历史资料，非当前规范。** 2026-10-09 整理入库，以下保留原始内容用于追溯，可能包含已下线功能、过期状态及旧路径。当前规则见 [教学模块](../product/education.md)、[开发说明](../development/local-development.md) 和 [AGENTS.md](../../AGENTS.md)。

# 会话交接记录

更新时间：2026-09-03

## 当前基线

- 产品品牌：**RightWrite**
- Git 仓库：`open-webui/`
- 分支：**`main`**（2026-09-03 收线完成，`upgrade/0.11.2` 已快进合入并删除本地分支）
- `main` HEAD：`6f79fbbf2`，已推送 origin
- 上游基线：**v0.11.2 已正式定为基线**（`7af39ca94` 合入），下次追上游从这里算 delta
- 遗留：`origin/upgrade/0.11.2` 远端分支尚未删除（与 `main` 同一提交，纯冗余，可随时删）
- 当前工作区：**干净**。成长画像那条线已收工，2026-09-03 分三个提交落库（画像证据/投影拆分、教学前端接入、教学身份 i18n）
- 本地环境：Windows 11、Python 3.12、Node.js，默认数据库为 SQLite

工作区根目录本身不是 Git 仓库；业务代码 Git 仓库位于 `open-webui/`。

## 本地启动

以根目录两个脚本为唯一推荐入口：

1. `start_backend.bat`：后端 `http://localhost:8080`
2. `start_frontend.bat`：前端 `http://localhost:5050`

后端脚本负责生成并加载 `open-webui/backend/.webui_secret_key`，同时配置开发 CORS 白名单。前端脚本执行 `npm run dev:5050`。完整手动命令与排障见 `本地开发启动流程.md`。

验证地址：

- 前端：`http://localhost:5050/`
- 后端健康检查：`http://localhost:8080/health`

## 产品主线

RightWrite 是基于 Open WebUI 二次开发的成长写作教学平台，核心数据链路为：

`classroom -> assignment -> writing_session -> versions/provenance -> submission rounds -> review -> growth profile`

已形成的主要闭环：

- 教师创建班级、批量管理学生、发布作业、查看进度与催交
- 学生加入班级，在作业或个人写作空间中使用 AI 协作写作
- 系统记录版本、来源片段、编辑操作、Prompt 时间线与微反思
- 教师查看终稿和过程证据，完成评分、评语、退回与重交
- 已批改即定稿；只有教师明确退回后才开放下一轮
- 通知覆盖提交、评阅、退回和催交
- 教师和学生可查看长期成长画像、趋势与轮次进步

双视角路由、API 和状态流转见 `教学模块Userflow.md`。

## 当前后端结构

- `backend/open_webui/routers/education.py`：HTTP 路由、权限和资源装配
- `backend/open_webui/services/education/analysis.py`：来源映射、版本差异、风险汇总和分析缓存
- `backend/open_webui/services/education/profile.py`：成长指标、趋势、轮次进步和画像组装
- `backend/open_webui/models/education.py`：ORM、DTO 和教育仓储方法
- `backend/open_webui/migrations/versions/`：教育表结构的唯一来源

教育表不再通过运行时代码建表或补列。

## 2026-08-05 至 2026-08-31 的修复（2026-08-31 已提交）

### 1. 补齐空数据库迁移

- 新增教育基础表迁移 `a1c3e5f7b9d2_create_education_tables.py`
- 将后续教育迁移接到该基线
- 新增“空 SQLite 数据库升级到 Alembic head”回归测试
- Alembic 当前保持单一 head：`e7b9d1f3a5c7`

### 2. 恢复教学前端类型保护

- 删除 20 个教学页面或组件中的 `@ts-nocheck`
- 教学增量检查范围为 0 warning
- 同步修正来源高亮深色模式的陈旧测试断言

### 3. 拆分教育后端单体路由

- 将来源分析与缓存迁到 `services/education/analysis.py`
- 将成长画像迁到 `services/education/profile.py`
- `routers/education.py` 从约 4600 行收缩到约 3000 行
- 算法测试改为直接覆盖服务层，不保留旧路由私有函数兼容别名

## 最近验证

- `npm run test:education`：55 passed
- `npm run test:frontend -- --run`：21 passed
- `npm run check`：教学范围 0 warning
- `npm run build`：通过
- Python 编译、Black（新文件）和 `git diff --check`：通过
- 空数据库 `alembic upgrade head`：通过

`npm run check` 仍会忽略教育范围外约 1324 条既有诊断；这不是本轮新增问题。

## 当前待办与决策

1. **上述三项已于 2026-08-31 分三个提交落地**（`8e9f5926c` 迁移基线 / `44c945da4` 服务层拆分 / `b941faea6` 前端类型检查），尚未 `git push`。
2. **开发令牌仍保存在工作区 `.codex/config.toml`。** 该目录不属于 `open-webui` Git 仓库，但明文令牌仍可能进入备份、同步盘或截图。建议移到 Windows 用户级环境变量后立即轮换旧令牌。
3. 聊天流式输出在升级后的手动浏览器回归尚未形成固定测试。2026-09-03 已人工验过一轮：流式逐字返回正常、中断正常，**该项通过**；同一轮确认 `ask_user` 选项面板是上游 v0.11 内置工具（`tools/builtin.py`，Timothy Baek 2026-08-13），不是 fork 回归，详见下节。
4. 全量 Svelte 历史诊断需要单独治理，不应混进教育功能提交。
5. **上游已发布 v0.11.0 / v0.11.1 / v0.11.2，落后 1180 个提交。** 评估结论见下节，不要直接 `git merge upstream/main`。
6. ~~**分支收线**~~ —— 2026-09-03 已完成。工作区清空 → 三套测试全绿 → 流式手动回归通过 →
   `push origin upgrade/0.11.2` 备份 → `branch -f main` 快进 → `push origin main`（`adb48d2eb..6f79fbbf2`）
   → 删本地分支。v0.11.2 正式定为基线。只剩远端 `origin/upgrade/0.11.2` 未删（冗余备份，与 main 同提交）。
7. **待做：学生对「写作构成」的补充说明（2026-09-23 记）。** 背景：`8a8168822` 起写作构成只在作业定稿
   （已批改或已截止）后给学生看，学生觉得数字不对时目前没有任何反馈渠道。已商定方案：
   - 定稿后构成面板下加「对这组数字有补充说明？」，每轮提交一段文字、可改；只有本人、只在定稿后能写；
   - 教师批改页在构成数字旁显示；若该轮已批改，给教师发新通知类型，是否重看/退回由教师决定；
   - 系统不判定、不改数字，说明同样是客户端的话，只作背景；学生报「记错了」顺带当留痕 bug 线索。
   - 工作量：`Submission` 加列（迁移用 `sa.Text`，PG 上跑测试）+ 学生写接口 + 学生端输入框 + 教师端展示与通知。
   - 已否决的方案：提交即锁定再即时显示（会取消「截止前可改稿重交」）；提交弹窗里先显示数字再让学生写说明（学生看完可回去改稿刷数）。

### ask_user 选项面板（2026-09-03 查明）

对话中途弹出的「请选择」面板是上游 v0.11 新增的内置工具 `ask_user`（`backend/open_webui/tools/builtin.py`
与 `utils/ask_user.py`，随 `7af39ca94` 进入本分支），模型可在回答中途向用户提 1–3 个问题、每题 2–3 个选项，
`allow_other` 控制能否自由填写。功能本身正常：本地那轮对话 9 次调用里 4 次返回 `{"status":"answered"}`。

另 5 次被后端参数校验拒绝（4 个选项超上限、缺 `id`、选项缺 description、把 questions 套进 options），
是模型把参数拼错后自行重试，所以界面上会反复弹面板；模型随后那句「界面里选择选项后没把文字带给我」
是它对自己被拒调用的臆测，不是前端丢数据。用户点的「我直接输入主题」是个普通选项，回传只有 option_index，
本来就不带文本——自由输入要走 `allow_other`。

**待评估**：这个内置工具在学生写作区同样可用，教学模块的 AI 使用留痕（`ai_used` / `ai_help_types`）
未把它计入，画像口径可能有缺口。

## 上游更新评估（2026-08-31）

- 三个版本均带 Security Advisory；v0.11.0 同时是界面重设计 + 数据库迁移 + 管理设置重构。
- 冲突面：与上游重叠改动的文件 180 个（非 i18n 121 个）。其中 61 个是我们已删除的文件（Ollama 支持与精简掉的语言包），会成为 delete/modify 冲突但处理机械。
- 真正困难的是 `chat/Chat.svelte` 与 `layout/Sidebar.svelte`：两侧各有约 2000 行改动，且 0.11.0 重做了界面、0.11.1 重写了流式。
- Alembic 在合并后会出现双 head（上游新增 10 个迁移），需要补一个 merge revision。
- 遗留疤痕：0.8.5→0.10.2 那次合并把 `Chat.svelte` 的冲突按旧版解决，导致该文件比上游 0.10.2 少约 456 行，不再引用 `chatRequestQueues`、`getSkills`、`terminalServers`、`structuredOutput`、`FilesOverlay`；其中 `chatRequestQueues` 目前全仓库只剩 store 定义。
- 路线：先在当前 0.10.2 基线上定向 cherry-pick 安全补丁，整版升级另开分支单独做。

### 已挑取的上游安全补丁（2026-08-31）

| 本地提交 | 上游 | 内容 |
| --- | --- | --- |
| `86870a88c` | `bc600d3f0` #26718 | KaTeX 渲染失败回退经 `{@html}` 导致存储型 XSS |
| `91b928fef` | `707efeaed` #26722 | 知识库 sync/cleanup 可跨库删除目录与向量集合 |
| `30c799f13` | `6d4c02a89` #26706 | 网页搜索临时 RAG 集合未按属主收敛 |
| `78eff6648` | `f89b50198` #26739 | `get_accessible_folder_files` 漏校验 note 条目 |
| `02e526efc` | `f517cc717` #27537 | WebSocket 认证缺角色校验（手工改写） |

`02e526efc` 为手工改写：上游同一提交里的 `user_join` 会话池复用分支我们没有，其余按上游语义落地。教学身份走 `education_role`，`role` 仍只有 user/admin/pending，`VERIFIED_USER_ROLES` 白名单对师生无影响。

### 升级到 v0.11.2（2026-08-31，分支 upgrade/0.11.2）

分两段合并完成，`main` 未动，随时可回退。

| 提交 | 内容 |
| --- | --- |
| `a30cda4fd` | 恢复上游 55 个语言包（消除每次升级 58 个 modify/delete 冲突） |
| `adb48d2eb` | 恢复 6 个 Ollama 模块文件（0.11.2 有 99 个文件引用它） |
| `09de3c9b7` | 合入 v0.11.0（51 个冲突，其中 32 块是上次合并的漂移） |
| `7af39ca94` | 合入 v0.11.2（31 个冲突，含 0.11.1 流式重写） |

前两个提交已在 `main` 上并推送；后两个合并提交只在升级分支。

**关键处置**
- `Chat.svelte` 与 `Sidebar.svelte` 均从上游整份重建再贴回教学定制，而不是逐块缝合——两文件的历史基底过旧（Chat.svelte 曾丢掉 chatRequestQueues、getSkills、terminalServers、structuredOutput、FilesOverlay，本次一并修复）
- 教学入口改为注册进 0.11.0 的可固定菜单项系统（writing / teaching）
- `readOnly` 折进上游同名推导；`showModelSelector`、`initialChatData` 随上游变化下线
- socket 保留 polling 兜底（上游改为仅 websocket），fork 的 `get_socketio_transports` 保留
- alembic 两个合并修订：`d7f1b3c5e9a2`（0.11.0）、`e9a3c7b5d1f4`（0.11.2）
- 新增依赖 `docx-preview`；`npm run build` 需要 `NODE_OPTIONS=--max-old-space-size=8192`

**验证**：pytest 62 passed（含空库迁移到 head）、`npm run check` 教学范围 0 warning、vitest 29 passed、`npm run build` 通过。**浏览器端手工回归尚未做。**

**待办**
1. 手工回归：学生写作留痕（ai_inserted / ai_pasted 采集点在 0.11.1 流式重写后需重点验证）、教师批改、退回重交、通知、侧边栏写作区入口
2. 合回 main 前先在本地跑通前后端
3. 上游在品牌位置新增了 LICENSE 声明注释（禁止更改/移除 Open WebUI 品牌标识）。本次保留了注释、维持 RightWrite 现状，**需要确认许可条款是否允许当前的改名**

### 工作区里有一批未提交的 score_max WIP

`models/education.py`、`routers/education.py`、`services/education/profile.py`、
`apis/education/index.ts`、`StudentGrowthProfile.svelte`、两个测试文件，外加未跟踪的
`a8c4e2f6b1d9_require_assignment_score_max.py`。内容是「作业满分 score_max」特性，
其测试当前失败（process_index 为 None、trends 缺 score 键）。它不属于本次升级，已排除在
两个合并提交之外；同一份内容也存在于 `stash@{0}`。注意工作区里的副本会被反复重新写入，
提交前先确认哪一份是最新的。

### 尚未挑取、混在 0.11.1 流式重写里无法单独 cherry-pick


- 角色变更立即生效
- 回复中途截断 / 消失 / 排队消息丢失
- Windows 下代码解释器启动失败

## 文档事实优先级

发生描述冲突时，按以下顺序判断：

1. 当前代码、迁移与自动化测试
2. `AGENTS.md` 和 `CLAUDE.md`
3. `本地开发启动流程.md`
4. `教学模块Userflow.md`
5. `PRD.md` 与历史设计文档
