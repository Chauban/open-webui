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
- `writing_context.py`：初稿解析、基线及当前正文；`revision_reading.py`：自主阅读与上下文；`teaching_config.py`：版本、授权及事务锁；`revision_items.py`：历史冻结清单只读汇总。
- `writing_access.py`：统一有效截止时间及写作状态校验。作业已批改返回 409，超过有效截止返回 400；写入路由、对话入口和模型调用共用校验。对话入口在创建聊天或保存消息之前检查，个人写作不受作业截止限制，但学生身份已关闭个人会话访问与写入。
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

- `single_conversation.py` 管理修订作业的单对话边界。`Chats.insert_new_chat` 在同一事务中锁定作业/写作会话、检查现有对话并绑定 `chat_id / active_chat_id`；SQLite 与 PostgreSQL 都通过实际写锁串行首条创建，普通聊天与从零写作不限制数量。
- 模型写入口同时拦截导入、移入/移出与归档；API 拒绝复制/分支、直接删除及会清掉修订记录的全量聊天清理。撤回初稿和显式维护仍走原有授权操作。已有多个对话的从零作业不能直接切换成修订类型，须先处理多余对话。
- 作业文件夹 meta 的 `single_conversation` 仅用于隐藏菜单与拖拽，后端依据真实作业类型校验，不信任客户端标记。文件夹地址跳回作业工作区，刷新继续原对话。
- 多对话清理不会在读取、启动或迁移中自动运行。维护入口为 `scripts/education/consolidate_revision_chats.py`：显式指定 DATABASE_URL 生成计划；停服并验证数据库备份后，携带 `--apply --backup` 执行。执行前重新核对计划中的记录，变动即拒绝；在同一事务删除多余 chat/chat_message/chat_file/shared_chat，更新当前对话指针，保留提交冻结事实、正文和成绩。

- 作业类型集中登记在 `services/education/task_types.py`：`from_scratch / revise_draft / revise_argument`。后两者都需确认基线、使用自主修订辅导且禁止读者试读；模型与数据库共同校验。
- 修订初稿须先明确确认初稿，再解锁正文编辑和 AI 对话；初稿至少 200 个非空白字符。导入支持 `.docx`、`.doc`、`.txt`、`.md`，文件上限 10 MB；也可导入照片（JPG / PNG / WebP，一次最多 8 张，单张 10 MB、合计 30 MB），由管理员选定的识图模型逐张转录、只转录不改写。PDF 在学生浏览器里读取（pdf.js，不上传 PDF、服务端不解析）：文字页直接取文字并还原段落、去掉页眉页脚与页码；扫描页渲染成图后走同一条识图路径，同样受 8 页上限。服务端提取正文供学生核对，不将导入文件或图片存入文件库。从零写作作业可在编辑器里用同一组导入，识别结果经预览后插入，记为外部粘贴并注明来自导入。导入只限作业的学生本人。
- `draft_baseline_text` / `draft_baseline_at` 保存确认基线；确认后不可直接改写，可在尚未提交时通过专用撤回初稿接口重来。退回重交保留最初基线，不能借改稿覆盖它。
- 确认初稿后进入修订工作区；初读及修订对话生成期间，前端临时锁定正文与提交，完成、失败或停止后恢复。初读、修改复看、整段复看由 `revision_reading.py` 记录，不使用评分维度，不要求处理清单。每条阅读保存来源正文、顺序号、教学/要求/退回意见版本与模型；同一请求复用记录，迟到结果不修改提交快照。`revision_items.py` 只读汇总历史清单。
- `Messages.svelte` 将原有阅读记录与当前聊天分支按时间合并展示，稳定 id 保持旧内容；不伪造或复制聊天数据。后续复看使用现有聊天调用及 `education_context` 冻结稿件/要求/模型信息，来源菜单只读原记录。原平台阅读步骤仍用于初读、历史结果与重试。
- `lastReadDraft` 从已完成的阅读或成功聊天回复的服务端 `education_context` 取最近稿件；改稿后提供输入区复看动作，未改回隐藏。点击前等待保存成功；失败保留输入、无请求、无新消息。聊天完成后读取对应消息的服务端上下文用于更新基准，刷新仍使用同一快照。对照稿优先使用上次聊天的较新稿件，避免连续复看一直比较最初稿。
- 每轮修订聊天把服务端捕获的当前稿作为正文材料附在本轮模型请求末尾，与本轮问题相邻；深复制消息，不修改学生原消息和聊天历史。system 中仍维护教学标准与规则，评分与反思不进入模型。仅点击预设复看且未写说明时标记 auto_started，带自己说明时保留真实学生提问属性。
- 修改复看与“整体再看看”等自然语言请求沿用当前聊天的模型/思考设置和辅导上下文，不再提供两个独立复看按钮；教师评分与反思仍不进入修订上下文。
- `WritingWorkspaceShell.svelte` 管理统一工作区；发送前等待正文保存（最多 5 秒，失败提示学生），后端从最近已保存正文注入每轮上下文及改动说明，不能依赖静态文件夹提示词或模型自发调用工具取得正文。
- 教师批改的 `teacherConversationEvents` 从冻结 `prompt_timeline / revision_readings / chat_contexts` 组装交流。`TeacherProcessPanel` 提供过程回放和任意两稿对照，左侧 `ProcessDraftView` 展示当时稿件或按句差异；同一父页面保存选择、展开状态、时间筛选与评分草稿。中间自动保存默认隐藏，实际供 AI 阅读的版本保留在主要节点中；详细编辑记录单独折叠。
- `teacherModelUsage` 只汇总当前提交冻结的对话、阅读及试读模型。分析页顶部按步骤展示，过程回放逐条展示 `model_id / thinking_level`；使用冻结模型标识，不从当前模型列表或管理员配置猜测过去用的模型。缺失字段明确标为未记录。
- 教学内置思考默认为 `medium`，DeepSeek 连接翻译为官方 `high`；图片识别仍为 `off`。已保存的 `education.ai_steps` 需显式调整，不做启动时覆盖或历史回填。学生仅一个可用模型时自动选中并静态展示名称，多个模型保留切换。
- `process_review.py` 仅使用提交冻结 evidence 与 stats 构建目录；`GET .../process` 返回不含正文的目录，`GET .../process/compare` 按需读取两份全文及差异。两接口验证所属教师与 `expected_final_version_id`，重交冲突返回 409，目录外版本返回 404；`GET .../versions` 同样截止到该次提交的 final version。前端后发请求优先，旧响应不覆盖新选择。
- AI 回复按消息 id 绑定真实上下文；学生消息通过明确的 parent/chat 关系关联，同一提问的多次生成若使用不同稿件则不替其猜选。版本 id 与正文同时吻合才复用保存节点，否则保留独立阅读快照。空正文保留为空，不读取实时正文补造。回放中间版本来自当前轮，前轮过程使用现有轮次切换；起点到提交对比仍可使用最初确认的初稿。不新增数据库迁移，不重写历史证据。
- `get_prompt_timeline` 为新提交保留 `revision_review_requested` 标记；快捷预设与学生说明分别展示，`auto_started` 对提问评分适用性的原有规则不变。画像证据 schema、评分口径和历史快照均不改写。旧提交缺少具体操作标记时只显示“平台预设消息”，不猜测按钮来源。
- 教师批改和本次分析读取提交时冻结的 `stats_json.revision_items` 与 `stats_json.coaching`；初稿到终稿按句对比。“说改了但原句未动”只是核查提示，可能在别处作等效修改，不能自动判错。
- 学生的任何对话都禁止读写记忆；作业对话还禁用检索聊天记录与记忆的内置工具。修改模型工具或聊天中间件时必须保持这些权限边界。
- 模型参数与系统提示的覆盖由服务端执行（`utils/access_control/chat.py`）：`/api/chat/completions`、`/openai/chat/completions` 与 Anthropic 兼容的 `/api/v1/messages` 按 `chat.controls` 且 `chat.params` / `chat.system_prompt` 去掉请求里的参数（含顶层的 `temperature`、`thinking` 等，只留流水线字段和 `tool_approval_mode`）与 system / developer 消息。原样转发给服务商、无法逐项去除的接口（`/openai/responses`、默认关闭的 `/openai/{path}`）只对两样都能设的用户开放，其余 403；`/api/v1/messages` 遇原生 Anthropic 连接时，受限用户改走转换后的对话流水线。保存用户设置时同样去掉 `ui.params`、`ui.system`；文件夹系统提示按 `chat.system_prompt`。作业写作区的学生一律去掉，与权限无关；只有辅导对话的思考档位由服务端另行算出（见下）。频道、自动化、子代理、定时器经 `CHAT_COMPLETION_HANDLER` 发出的请求由平台拼成，不经此去除。组权限按最宽松合并，要收回学生须在默认权限里关掉、再给教师组打开。
- 写作区文件夹（`assignment_writing` / `personal_writing`）只由教学路由建立和同步：文件夹接口拒绝建立这两种 mode、拒绝把普通文件夹改成这两种，已有写作区文件夹只接受 `meta.hidden_from_sidebar` 与 `data.model_ids` 的改动，其余 meta / data（关联的写作会话、老师的作业说明）一律 403。

## AI Steps & Thinking

- 统一思考参数 `thinking_level`（`off / low / medium / high`，不设为模型默认）在 `utils/thinking.py` 按连接翻译：连接设置的「思考格式」（`thinking_format`：`openai` 的 reasoning_effort、Responses 的 reasoning.effort、`anthropic` 的 budget_tokens、`deepseek`、`kimi`、`zhipu`、`doubao`、`qwen` 的 enable_thinking、`chat_template`、`openrouter`），没设时按主机名后缀识别。各家写法以 2026-10-18 的实测为准，见 [思考档位实测结果](../reference/thinking-params-test-results.md)：关不掉思考的模型（GLM-5.3 系列实测；GLM-4.7、4.5V、Kimi K2.7-Code 按参考文档）从不发 `disabled`：能分档的「关」退到最低档，不分档的各档都按模型默认、什么也不发；Kimi 用 `thinking.type=disabled` 关，K3 用 `reasoning_effort` 分档，K2.6 只有开 / 关（各档都发 `thinking.type=enabled`）。各模型能不能关、能不能分档记在 `MODEL_THINKING_SUPPORT`，模型列表里每个模型带 `thinking_support`（自建模型随底模），模型编辑页（勾了思考控制时）与 AI 步骤设置（选到这类模型时）据此提示。服务商固定死的采样参数（`FIXED_SAMPLING_PARAMS`，目前是 Kimi 的 `temperature`、`top_p`、`n`、`presence_penalty`、`frequency_penalty`，只接受一个值，`temperature` 还随思考开关变）在发送前一律去掉，不管值是多少、有没有勾思考控制；模型编辑页（参数设了这类参数时）和连接设置（选到 Kimi 时）经 `POST /openai/sampling-rules` 读同一张表显示提示。只有模型能力勾了「思考控制」（`capabilities.reasoning`，默认不勾）才翻译，否则丢弃，档位本身不会原样发给服务商。
- 服务商注意事项（`utils/provider_quirks.py`）：每家服务商、每个模型不寻常的地方一条不漏地写给管理员看——固定死的采样参数、只能开 / 关、关不掉思考、档位映射（如「中」按 high 发）、「模型默认」即开着思考，都从发送时实际读的表（`FIXED_SAMPLING_PARAMS`、`MODEL_THINKING_SUPPORT`、`EFFORT_BY_LEVEL`、`THINKS_BY_DEFAULT`）生成；代码管不了的事实（DeepSeek 高峰价、豆包按原始思考计费、千问开思考不支持 JSON 模式）记在 `PROVIDER_FACTS`。连接设置（「思考格式」下方，整家）与模型编辑页（「能力」下方，这个模型）经 `POST /openai/provider-quirks` 显示；「AI 步骤设置」每行按所选模型与档位显示（`StepView.quirks`），包括第一次通读选「高」或模型默认时可能超过 90 秒读超时、建议「低」（下拉里不标推荐，存的默认仍是「模型默认」）。表头说明「模型默认」：不发送思考参数、由服务商决定，后半句按目前接入的模型与能力表生成（`model_default_meaning`；服务商公开的默认档位记在 `PUBLISHED_DEFAULT_EFFORT`，目前只有 DeepSeek 的 high）。
- 服务商一时出错自动重发（`utils/retry.py`）：作业辅导对话（`main.py` 在 metadata 里带 `retry_transient`）、管理员打开时的个人写作辅导对话（`education.auto_retry.personal_writing`，默认关；哪几处重发、哪些能开关登记在 `ai_steps.py` 的 `RETRY_SCOPES`，管理员「写作辅导」设置里的「自动重发」按它生成）与 `call_step_model` 发出的平台步骤（图片识别除外，它按页自己重发）在 OpenAI 兼容路由里遇 429、5xx、连接失败或超时时，按 1、2、4 秒 ±25% 最多发 4 次；只在还没往下游送内容之前重发（一次性回复读完响应体、流式回复读到第一段才算发成，等它们超时也重发），流式回复中途断了不重来。带重发的请求连接最多等 10 秒；流式第一段及两段之间最多 45 秒、过 60 秒不再开始新的一次；一次性回复最多 90 秒、过 120 秒不再开始新的一次，两者超时后都还能再发一次。其余 4xx 不重发。
- `services/education/ai_steps.py` 登记教学的每处模型调用：`coaching_chat`、`first_read`、`revision_review`、`whole_review`、`reader_check`、`image_parsing`、`class_insight`。平台步骤一律经 `call_step_model(step=…)` 发出，测试静态核对教学代码只在这里调用 `generate_chat_completion`，且每处调用写明登记过的步骤；新增调用必须先登记，管理员表与教师 AI 设置卡都按登记生成。
- `education.ai_steps`：`coaching_chat: {control: admin|teacher|student, default}`，其余平台步骤各 `{model, thinking}`；思考默认全为模型默认，图片识别为关。只有辅导对话可下放；教师设置存 `assignment.model_params`（`{thinking, students_choose_thinking}`，迁移 `b3d5f7a9c1e4`），按此刻的下放方式解读，收回后不再生效。学生只能在允许时关闭当轮，不能调高。
- 冻结与留痕：`stats_json.coaching.thinking` 冻存提交时的 `{control, level, source, students_choose}`；作业对话的每条回复在 `meta.thinking_level` 记实际发出的档位。
- 模型：`model` 为空时初读与复看、读者试读用学生在写作区选的模型，班级论证归纳用老师选的；图片识别必须指定（为空即不提供图片导入，原 `education.draft_image_model` 已由迁移 `c6e8a0b2d4f7` 并入）。辅导对话不设固定模型：学生能选哪些由模型访问控制决定。`resolve_step_model` 是唯一的解析入口：指定的模型还在就用它并跳过学生 / 老师的模型访问控制；已被删掉时记告警、回落到学生 / 老师的模型（图片识别无回落），管理员页按 `EDUCATION_AI_STEP_VIEWS` 标红。保存设置时只校验新选的模型（须存在，图片识别还须能看图），已失效的旧值不挡保存。
- 实际用的模型：`writing_session.revision_items_model_id` / `revision_follow_up_model_id`、`challenge_turn.model_id`、`challenge_session.closing_model_id`、`challenge_insight.model_id`，图片导入写进编辑操作的 `metadata_json.model_id`；提交时冻进 `stats_json.revision_items.models`（`{first_read, follow_up}`）与 `stats_json.challenge.models`，批改页显示。

## Instance Configuration & Evidence

- 管理员维护 `teaching_configuration` 中三类版本化教学配置，以及 `education.default_coaching_style / enable_coaching_styles / coaching_prompts`（仅从零写作）、`education.enable_return / challenge_prompts / ai_steps / auto_retry`。
- `/teacher/assignment-defaults` 返回该教师的类型授权和默认类型，以及三类当前教学配置。旧 `education.task_prompts / default_task_mode / default_rubrics` 仅保留为迁移来源，不再作为当前表单或修订上下文的配置入口。
- 画像事实证据不可变，算法结果与聚合结果保存为版本化投影；普通画像 GET 读取投影，不扫描原始历史或偷偷重算。改算法须提升 `PROFILE_METRIC_VERSION`，改证据 schema 须同步更新严格类型与迁移。
- 当前证据 schema 为 `2026-10-01.1`，指标版本为 `2026-11-07.1`；首轮过程指标从声明初稿算起，重交轮从上一轮终稿算起，不能把整份初稿计成一次大段突增。
- 不兼容迁移可能要求证据/投影表为空（如 `e8a0c2d4f6b7`）；按具体迁移和部署文档显式清理，不编写自动补建或兼容回填。需要切换算法时显式运行 `profile_recompute --activate`，不能在读取接口中修复。

## 2026-11-07 作业类型与版本边界

- `teacher_task_access` 存管理员明确授权与默认类型，数据库约束默认值必须获权；缺失授权记录时关闭创建权限，读取不补建。身份设为教师时显式建立从零写作授权。
- `teaching_configuration` 按类型与版本保存配置；管理员通过 `/configs/education/types` 发布版本，作业保存 `teaching_config` 快照。前端教师默认值读取账号授权及三类配置。
- 作业新增 `scoring_mode`、`config_revision`、`description_version`、`reflection_version`、`change_summary`。更新携带期望配置版本；首次提交锁评分，有基线或提交锁类型与教学规则。
- `lock_assignment` 在 SQLite 与 PostgreSQL 上用同一作业行的写锁串行化更新、基线、提交与批改；模型生成前提交占位，模型调用期间不持有写事务。
- 修订上下文显式白名单选取教学快照、题目说明、当前稿及已发布退回意见，排除评分模式、维度、满分、反思题与通用辅导档位。聊天每轮重新装配，避免旧文件夹提示词继续生效。
- 新提交 `stats_json.assignment_config / revision_readings / returned_feedback / chat_contexts` 冻结实际配置与已完成过程。旧证据不重写、不补建、不清理。
- 批改携带 `expected_final_version_id / expected_review_revision`，冲突返回 409。已发布评阅拒绝存为 pending；更正追加事件、重建当前版本投影，正文仍只读。
- 无反思回答、无学生提问对应质量项不适用。仅总分不生成空分项零分。画像指标版本提升为 `2026-11-07.1`，证据 schema 保持原有结构；新算法的上线激活与重算仍须显式执行。
- 迁移 `d7e9f1a3b5c8` 保留提交、反思、评阅及证据原文，迁移当时为既有作业绑定教学快照；旧教师保留从零写作及已布置类型，段落论证默认未授权。退回开关不变。正式执行前核查授权清单并备份。

## 2026-11-07 学生个人写作暂时关闭

学生写作首页固定展示作业写作，隐藏个人写作分段及侧边栏个人写作项目；首页最近写作不返回个人稿件。服务端拒绝学生新建、打开及操作个人写作会话，也拒绝通过已有对话或项目文件夹继续发起个人写作 AI 对话（403）。已有个人稿件和对话保留，不删除。作业写作、提交、批改和成长画像继续开放。教师保持侧边栏无入口、接口仍可用的现状，管理员不受影响。未新增管理员开关。
