# 教学模块：当前架构与产品规则

> 核对日期：2026-10-09。依据现有代码及项目工程规范整理；变更业务行为时同步维护本文。历史方案见 [归档说明](../archive/README.md)，不能依据旧方案恢复已删除功能。

[PRD](PRD.md) 维护产品目标与验收边界，[当前任务清单](教学模块开发任务清单.md) 维护待办状态，[Userflow](教学模块Userflow.md) 维护学生与教师流程。本文维护技术架构与实现边界，相关功能变化时同步更新各文档涉及的内容。

## 技术栈与通用入口

Right Write 基于 Open WebUI v0.11.2。前端使用 Svelte 5、SvelteKit 2、TypeScript 和 Tailwind CSS 4，后端使用 FastAPI、SQLAlchemy 和 Alembic。

| 位置                                      | 职责                       |
| ----------------------------------------- | -------------------------- |
| `src/routes/`                             | 页面与布局                 |
| `src/lib/components/`                     | 共享组件与教学 UI          |
| `src/lib/apis/`                           | 前端 HTTP 客户端和类型     |
| `src/lib/stores/`                         | 全局状态和实例功能开关     |
| `backend/open_webui/main.py`              | 应用、路由挂载和中间件     |
| `backend/open_webui/routers/`             | HTTP、身份权限和事务入口   |
| `backend/open_webui/models/`              | 严格模型、数据库约束和仓储 |
| `backend/open_webui/services/education/`  | 教学业务逻辑               |
| `backend/open_webui/migrations/versions/` | Alembic 数据结构迁移       |
| `backend/open_webui/socket/main.py`       | Socket.IO 服务             |

前端通过同源 `/api/...` 请求后端，开发时 Vite 默认代理到 8080。路由检查身份和资源权限，调用业务服务与仓储，并控制事务；Socket.IO 负责实时通知和流式消息。教学数据沿班级与作业、写作会话、提交快照、教师批改和成长画像流转，详细边界见下文。

后端品牌图片、字体等位于 `backend/open_webui/static/`，是项目资源；维护范围见 [品牌资源边界](../rightwrite-branding-boundary.md)。

## Backend Boundaries

- `routers/education.py`：HTTP、身份权限、资源装配与事务入口；`models/education.py`：严格数据模型、数据库约束与仓储。
- `services/education/identity.py`：教学身份，使用 `education-teacher` / `education-student` 用户组；平台角色 `user.role` 与教学身份不是同一字段，管理员通过平台角色获权。
- `writing_context.py`：初稿文件解析、初稿基线和每轮对话的当前正文上下文；`revision_items.py`：第一次通读、修改清单、补看和提交快照汇总。
- `writing_access.py`：统一有效截止时间及写作状态校验。作业已批改返回 409，超过有效截止返回 400；写入路由、对话入口和模型调用共用校验。对话入口在创建聊天或保存消息之前检查，个人写作继续允许写入。
- `challenge.py` / `challenge_insight.py`：提交前 AI 读者试读及维度聚合；`analysis.py`：来源、过程指标及分析缓存。
- `profile_evidence.py` / `profile_snapshots.py`：冻结证据；`profile.py` / `profile_aggregates.py`：画像指标和聚合投影；`profile_recompute.py`：显式批量重算。细节参见 [画像投影说明](../../backend/open_webui/services/education/PROFILE_PROJECTIONS.md)。

## Frontend Entry Points

- API 与类型：`src/lib/apis/education/index.ts`、`types.ts`；教学组件：`src/lib/components/education/`。
- 学生：`/me/writing` 写作首页、`/me/writing/growth` 成长画像、`/assignments/[assignmentId]/write` 作业工作区、`/writing/[sessionId]` 个人工作区、`/join` 加班、`/education/setup` 身份引导。
- 教师：`/teacher` 总览、`/teacher/classrooms` 班级、`/teacher/assignments` 作业、`/teacher/review` 全局批改队列、`/teacher/submissions/[submissionId]` 批改工作台。
- 顶栏分区与对象子标签由 `teacher-nav.ts` 统一定义；班级仅“总览 / 学生”，作业为“概况 / 提交与批改 / 本次分析 / 设置”。布局复用 `EduPageShell` / `TeacherPageShell`，全局与作业内提交列表复用 `SubmissionQueue`，教师与学生画像复用 `StudentGrowthProfile`。
- 管理员写作辅导配置在 `src/lib/components/admin/Settings/Education.svelte`；`/admin/education` 为教研数据导出入口。

## Identity, Assignment & Review

- 一个学生只能加入一个班；同一教师可在本人班级间调班，跨教师换班由管理员处理。既有提交留在原班，成长画像跟随学生。
- 作业归档功能、归档字段和接口已删除；班级作业子页面、旧的按作业取提交列表教师接口也已下线。提交列表使用当前教师队列接口，不重建旧入口。
- 不再做班级或作业层面的风险加总；过程信号用于教师逐份核查，不是作弊结论。消化度与平均改写率已删除，提问质量由教师评分，不以提问条数代替质量。
- 教师按作业配置反思题（单选、多选、文本），提交时冻结题目及回答；批改展示本轮快照，不能用后来编辑的题目替换。修订初稿作业不再问必然为“是”的 AI 使用题。
- 满分与评分维度在首次提交后锁定；已有初稿基线或提交时作业形式锁定，前后端都应执行边界校验。
- 退回重写由实例级 `education.enable_return` 控制，**默认关闭**；前端按 `features.enable_education_return` 显示相关操作与统计，后端在关闭时拒绝退回请求。不要把开关关闭诊断成 UI 或接口缺陷。
- 已批改或已截止的作业禁止写正文、版本、来源、操作、修订清单及试读记录，也禁止发起新对话。只读工作区、过程摘要及已生成通读结论仍可读取；切换已有对话作为查看操作保留。退回、个人延期及待批改编辑按当前有效截止判断。
- 完成批改后重新读取教师待批改队列，优先继续原后序记录，否则进入剩余队列首项；仅服务器总数为零时提示清空，刷新失败返回队列页。

## Task Modes & Writing Context

- `task_mode` 仅为 `from_scratch`（从零写作）或 `revise_draft`（修订初稿）。修订初稿不能启用 AI 读者试读，模型校验与数据库 CHECK 都限制这个组合。
- 修订初稿须先明确确认初稿，再解锁正文编辑和 AI 对话；初稿至少 200 个非空白字符。导入支持 `.docx`、`.doc`、`.txt`、`.md`，文件上限 10 MB；也可导入照片（JPG / PNG / WebP，一次最多 8 张，单张 10 MB、合计 30 MB），由管理员选定的识图模型逐张转录、只转录不改写。PDF 在学生浏览器里读取（pdf.js，不上传 PDF、服务端不解析）：文字页直接取文字并还原段落、去掉页眉页脚与页码；扫描页渲染成图后走同一条识图路径，同样受 8 页上限。服务端提取正文供学生核对，不将导入文件或图片存入文件库。从零写作作业可在编辑器里用同一组导入，识别结果经预览后插入，记为外部粘贴并注明来自导入。导入只限作业的学生本人。
- `draft_baseline_text` / `draft_baseline_at` 保存确认基线；确认后不可直接改写，可在尚未提交时通过专用撤回初稿接口重来。退回重交保留最初基线，不能借改稿覆盖它。
- 确认初稿后自动发起首轮诊断，按评分维度逐项通读；修改清单含 `problem / minor / ok / deferred`，学生处理为 `revised / partly / kept`，暂缓维度通过补看继续。状态与并发请求应由服务端约束。
- `WritingWorkspaceShell.svelte` 管理统一工作区；发送前等待正文保存（最多 5 秒，失败提示学生），后端从最近已保存正文注入每轮上下文及改动说明，不能依赖静态文件夹提示词或模型自发调用工具取得正文。
- 教师批改和本次分析读取提交时冻结的 `stats_json.revision_items` 与 `stats_json.coaching`；初稿到终稿按句对比。“说改了但原句未动”只是核查提示，可能在别处作等效修改，不能自动判错。
- 学生的任何对话都禁止读写记忆；作业对话还禁用检索聊天记录与记忆的内置工具。修改模型工具或聊天中间件时必须保持这些权限边界。
- 模型参数与系统提示的覆盖由服务端执行（`utils/access_control/chat.py`）：`/api/chat/completions`、`/openai/chat/completions` 与 Anthropic 兼容的 `/api/v1/messages` 按 `chat.controls` 且 `chat.params` / `chat.system_prompt` 去掉请求里的参数（含顶层的 `temperature`、`thinking` 等，只留流水线字段和 `tool_approval_mode`）与 system / developer 消息。原样转发给服务商、无法逐项去除的接口（`/openai/responses`、默认关闭的 `/openai/{path}`）只对两样都能设的用户开放，其余 403；`/api/v1/messages` 遇原生 Anthropic 连接时，受限用户改走转换后的对话流水线。保存用户设置时同样去掉 `ui.params`、`ui.system`；文件夹系统提示按 `chat.system_prompt`。作业写作区的学生一律去掉，与权限无关；只有辅导对话的思考档位由服务端另行算出（见下）。频道、自动化、子代理、定时器经 `CHAT_COMPLETION_HANDLER` 发出的请求由平台拼成，不经此去除。组权限按最宽松合并，要收回学生须在默认权限里关掉、再给教师组打开。
- 写作区文件夹（`assignment_writing` / `personal_writing`）只由教学路由建立和同步：文件夹接口拒绝建立这两种 mode、拒绝把普通文件夹改成这两种，已有写作区文件夹只接受 `meta.hidden_from_sidebar` 与 `data.model_ids` 的改动，其余 meta / data（关联的写作会话、老师的作业说明）一律 403。

## AI Steps & Thinking

- 统一思考参数 `thinking_level`（`off / low / medium / high`，不设为模型默认）在 `utils/thinking.py` 按连接翻译：连接设置的「思考格式」（`thinking_format`：`openai` 的 reasoning_effort、Responses 的 reasoning.effort、`anthropic` 的 budget_tokens、`qwen` 的 enable_thinking、`chat_template`、`thinking_type`、`openrouter`），没设时按地址识别。只有模型能力勾了「思考控制」（`capabilities.reasoning`，默认不勾）才翻译，否则丢弃，档位本身不会原样发给服务商。
- `services/education/ai_steps.py` 登记教学的每处模型调用：`coaching_chat`、`first_read`（含补看）、`reader_check`、`image_parsing`、`class_insight`。平台步骤一律经 `call_step_model(step=…)` 发出，测试静态核对教学代码只在这里调用 `generate_chat_completion`，且每处调用写明登记过的步骤；新增调用必须先登记，管理员表与教师 AI 设置卡都按登记生成。
- `education.thinking`：`coaching_chat: {control: admin|teacher|student, default}`，其余步骤各一个档位；默认全为模型默认，图片识别为关。只有辅导对话可下放；教师设置存 `assignment.model_params`（`{thinking, students_choose_thinking}`，迁移 `b3d5f7a9c1e4`），按此刻的下放方式解读，收回后不再生效。学生只能在允许时关闭当轮，不能调高。
- 冻结与留痕：`stats_json.coaching.thinking` 冻存提交时的 `{control, level, source, students_choose}`；作业对话的每条回复在 `meta.thinking_level` 记实际发出的档位。
- 不为通读或试读固定专用模型（推迟）：这些步骤仍用学生所选的对话模型，管理员表与教师卡的「模型」一栏写明这一点。

## Instance Configuration & Evidence

- 管理员持久化配置：`education.default_task_mode`（默认 `from_scratch`）、`education.default_coaching_style`（默认 `balanced`）、`education.default_rubrics`（按作业形式分别配置）、`education.enable_coaching_styles`（默认开启）、`education.coaching_prompts`、`education.task_prompts`、`education.challenge_prompts`、`education.draft_image_model`（初稿图片识别模型，默认空=不提供图片导入）、`education.thinking`（各 AI 步骤的思考档位与辅导对话的下放方式，结构见下）。
- 教师新建作业经 `/api/v1/teacher/assignment-defaults` 获取实例默认值；不要把某个部署实例的课程设定写成所有实例的固定默认值。档位取值为 `socratic / balanced / hands_off`，关闭档位后只使用任务说明，不再注入档位提示词。
- 画像事实证据不可变，算法结果与聚合结果保存为版本化投影；普通画像 GET 读取投影，不扫描原始历史或偷偷重算。改算法须提升 `PROFILE_METRIC_VERSION`，改证据 schema 须同步更新严格类型与迁移。
- 当前初稿证据 schema 与指标版本为 `2026-10-01.1`；首轮过程指标从声明初稿算起，重交轮从上一轮终稿算起，不能把整份初稿计成一次大段突增。
- 不兼容迁移可能要求证据/投影表为空（如 `e8a0c2d4f6b7`）；按具体迁移和部署文档显式清理，不编写自动补建或兼容回填。需要切换算法时显式运行 `profile_recompute --activate`，不能在读取接口中修复。
