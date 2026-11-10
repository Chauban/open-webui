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

- `teaching_search.py` 是段落论证可选检索执行层：`AiCandidate.web_search` 为独立严格布尔字段，默认 false，存于现有 JSON 配置，无新增表或数据回填。`education.teaching_search` 存管理员服务开关和官方连接编号，密钥沿用连接设置，仅后端读取。
- `utils.chat` 仅在可信教学绑定开启搜索时进入工具循环；在全局 inlet 过滤之后由服务端提供 `search_sources/read_source`，过滤器仍不得自行注入工具。关闭分支保持原模型请求。检索轮次沿用发起调用的 AI 步骤，实际发送及响应归入同一次教学证据；Responses 适配保留 function call 和续传输出项。
- 搜索限定 DeepSeek 官方端点，读取仅接受本轮检索所得公开 URL，限时、限次数、限正文长度。工具来源文字作为不可信数据，逐字匹配只证明出现在本次返回文本，不证明史料真实性。`context.source_search` 保存实际查询、来源、截取正文、匹配结果和失败状态，不保存密钥。最终回答仍经原教学过滤和存储流程；管理员撤回服务只阻止新检索，不改写旧证据。

- `routers/education.py`：HTTP、身份权限、资源装配与事务入口；`models/education.py`：严格数据模型、数据库约束与仓储。
- `services/education/identity.py`：教学身份，使用 `education-teacher` / `education-student` 用户组；平台角色 `user.role` 与教学身份不是同一字段，管理员通过平台角色获权。
- `writing_context.py`：初稿解析、基线及当前正文；`revision_reading.py`：自主阅读与上下文；`teaching_config.py`：版本、授权及事务锁；`revision_items.py`：历史冻结清单只读汇总。
- `writing_access.py`：统一有效截止时间及写作状态校验。作业已批改返回 409，超过有效截止返回 400；写入路由、对话入口和模型调用共用校验。对话入口在创建聊天或保存消息之前检查，个人写作不受作业截止限制，但个人会话访问与写入须通过对应角色的实例开关。
- `challenge.py` / `challenge_insight.py`：提交前 AI 读者试读及维度聚合；`analysis.py`：来源、过程指标及分析缓存。
- `profile_evidence.py` / `profile_snapshots.py`：冻结证据；`profile.py` / `profile_aggregates.py`：画像指标和聚合投影；`profile_recompute.py`：显式批量重算。细节参见 [画像投影说明](../../backend/open_webui/services/education/PROFILE_PROJECTIONS.md)。

## Frontend Entry Points

- API 与类型：`src/lib/apis/education/index.ts`、`types.ts`；教学组件：`src/lib/components/education/`。
- 学生：`/me/writing` 写作首页、`/me/writing/growth` 成长画像、`/assignments/[assignmentId]/write` 作业工作区、`/writing/[sessionId]` 个人工作区、`/join` 加班、`/education/setup` 身份引导。
- 教师：`/teacher` 总览、`/teacher/classrooms` 班级、`/teacher/assignments` 作业、`/teacher/review` 全局批改队列、`/teacher/submissions/[submissionId]` 批改工作台。
- 顶栏分区与对象子标签由 `teacher-nav.ts` 统一定义；班级仅“总览 / 学生”，作业为“概况 / 提交与批改 / 本次分析 / 设置”。布局复用 `EduPageShell` / `TeacherPageShell`，全局与作业内提交列表复用 `SubmissionQueue`，教师与学生画像复用 `StudentGrowthProfile`。
- 管理员写作辅导配置在 `src/lib/components/admin/Settings/Education.svelte`；`/admin/education` 为教研数据导出入口。

## Identity, Assignment & Review

- 作业可见性由独立 `Assignment.hidden` 布尔列维护（默认 false，Alembic 迁移 `e5a7c9d143f6`）。`PATCH /assignments/{id}/visibility` 仅所属教师或管理员可用，严格接收 `{hidden: boolean}`，不使用归档状态，不改变配置版本、截止、提交证据或教师批改范围。
- 学生作业查询过滤隐藏记录，统一作业/写作校验拒绝隐藏作业；最近写作、项目列表、通知摘要与学生画像排除相关入口。隐藏期间不向学生发送该作业业务通知，恢复后重新展示既有记录。学生画像的可见范围从冻结投影计算，不改写教师端的完整物化聚合。

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
- 修订初稿先确认至少 200 个非空白字符的正文。Word/PDF 由 `services/education/materials.py` 统一解析：正文与图片、脚注、尾注、批注、文本框、页眉页脚分开；PDF 图文混排页和扫描页通过管理员指定的识图模型读取，保留页码、出处及图表关系，不再因文字层存在而跳过图片。Word/PDF 原件和安全图片预览通过 Storage 保存为专用材料包，不进入聊天文件检索库；文件上限 50 MB、PDF 50 页、材料项目 200 个，纯文本与旧版 OLE Word 保留 10 MB 上限。旧版 `.doc` 的非正文对象及不支持的嵌入对象明确标为未读取。独立照片导入保留原有 8 张/30 MB 与逐张转录流程。导入只限作业的学生本人。
- `draft_baseline_text` / `draft_baseline_at` 保存确认基线；确认后不可直接改写，可在尚未提交时通过专用撤回初稿接口重来。退回重交保留最初基线，不能借改稿覆盖它。
- 确认初稿后进入修订工作区；初读及修订对话生成期间，前端临时锁定正文与提交，完成、失败或停止后恢复。初读、修改复看、整段复看由 `revision_reading.py` 记录，不使用评分维度，不要求处理清单。代码只标明流程阶段和稿件来源，不限制反馈条数或教学顺序。文献综述校验 JSON、非空回复及引文；段落论证直接接收正文，只检查非空和明确的不完整结束。完整回复可放在 `overview`，其余字段可为空，学生与教师过程视图均展示回复。每条阅读保存来源正文、顺序号、教学/要求版本与模型；同一请求复用记录，迟到结果不修改提交快照。`revision_items.py` 只读汇总历史清单。
- 阅读成功时由 `reading_conversation.py` 在同一事务中写入真实 assistant 消息及阅读证据，绑定同一会话；初读回复成为后续消息的父节点，可被正常历史加载器读取。`Messages.svelte` 依据消息与阅读的关联只展示一次，保留来源稿件入口。旧独立记录仍只读保留，不自动补写历史。后续复看使用现有聊天调用及 `education_context` 冻结稿件/要求/模型信息，来源菜单只读原记录。原平台阅读步骤仍用于初读、历史结果与重试。
- `lastReadDraft` 从已完成的阅读或成功聊天回复的服务端 `education_context` 取最近稿件；改稿后提供输入区复看动作，未改回隐藏。点击前等待保存成功；失败保留输入、无请求、无新消息。聊天完成后读取对应消息的服务端上下文用于更新基准，刷新仍使用同一快照。此基准仅用于判断是否显示复看按钮，旧稿不自动发送给模型。
- 每轮修订聊天只把服务端捕获的当前稿附在本轮用户消息末尾一次，与本轮问题相邻；system 不再重复注入正文。普通交流与复看都只附当前全文，不通过关键词判断意图或自动附旧稿；不再通过关键词识别额外注入阅读意见或其旧稿。深复制消息，不修改学生原消息和聊天历史。system 中注入统一辅导提示词（含教学目标、判断标准及各阶段辅导方式），不再附加代码中的教学规则，评分与反思不进入模型。仅点击预设复看且未写说明时标记 auto_started，带自己说明时保留真实学生提问属性。
- 修改复看与“整体再看看”等自然语言请求沿用辅导上下文；段落论证模型/思考来自当前辅导版本，其他类型沿用当前聊天设置，不再提供两个独立复看按钮；教师评分与反思仍不进入修订上下文。
- `WritingWorkspaceShell.svelte` 管理统一工作区；发送前等待正文保存（最多 5 秒，失败提示学生），后端从最近已保存正文注入每轮上下文及改动说明，不能依赖静态文件夹提示词或模型自发调用工具取得正文。
- 教师批改的 `teacherConversationEvents` 从冻结 `prompt_timeline / revision_readings / chat_contexts` 组装交流。`TeacherProcessPanel` 提供过程回放和任意两稿对照，左侧 `ProcessDraftView` 展示当时稿件或按句差异；同一父页面保存选择、展开状态、时间筛选与评分草稿。中间自动保存默认隐藏，实际供 AI 阅读的版本保留在主要节点中；详细编辑记录单独折叠。
- `teacherModelUsage` 只汇总当前提交冻结的对话、阅读及试读模型。分析页顶部按步骤展示，过程回放逐条展示 `model_id / thinking_level`；使用冻结模型标识，不从当前模型列表或管理员配置猜测过去用的模型。缺失字段明确标为未记录。
- 教学内置思考默认为 `medium`，DeepSeek 连接翻译为官方 `high`；图片识别仍为 `off`。已保存的 `education.ai_steps` 需显式调整，不做启动时覆盖或历史回填。其他类型的学生仅一个可用模型时自动选中并静态展示名称，多个模型保留切换；段落论证始终显示教师绑定模型。
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
- `services/education/ai_steps.py` 登记教学的每处模型调用：`coaching_chat`、`first_read`、`revision_review`、`whole_review`、`reader_check`、`image_parsing`、`class_insight`。平台步骤经 `call_step_model(step=…)`，段落论证绑定调用经 `call_captured_model(step=…)` 发出，测试静态核对教学代码只在这里调用 `generate_chat_completion`，且每处调用写明登记过的步骤；新增调用必须先登记，管理员表与教师 AI 设置卡都按登记生成。
- `education.ai_steps`（不覆盖段落论证已发布的辅导版本）：`coaching_chat: {control: admin|teacher|student, default}`，其余平台步骤各 `{model, thinking}`；思考默认全为模型默认，图片识别为关。只有辅导对话可下放；教师设置存 `assignment.model_params`（`{thinking, students_choose_thinking}`，迁移 `b3d5f7a9c1e4`），按此刻的下放方式解读，收回后不再生效。学生只能在允许时关闭当轮，不能调高。
- 冻结与留痕：`stats_json.coaching.thinking` 冻存提交时的 `{control, level, source, students_choose}`；作业对话的每条回复在 `meta.thinking_level` 记实际发出的档位。
- 模型：`model` 为空时初读与复看、读者试读用学生在写作区选的模型，班级论证归纳用老师选的；图片识别必须指定（为空即不提供图片导入，原 `education.draft_image_model` 已由迁移 `c6e8a0b2d4f7` 并入）。除段落论证外，辅导对话模型由学生选择，列表由模型访问控制决定；段落论证改用下述作业辅导版本。其他类型的 `resolve_step_model` 解析规则：指定的模型还在就用它并跳过学生 / 老师的模型访问控制；已被删掉时记告警、回落到学生 / 老师的模型（图片识别无回落），管理员页按 `EDUCATION_AI_STEP_VIEWS` 标红。保存设置时只校验新选的模型（须存在，图片识别还须能看图），已失效的旧值不挡保存。
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
- 修订上下文显式白名单选取教学快照、题目说明与当前稿；不自动注入教师退回意见，排除评分模式、维度、满分、反思题与通用辅导档位。聊天每轮重新装配，避免旧文件夹提示词继续生效。
- 新提交 `stats_json.assignment_config / revision_readings / returned_feedback / chat_contexts` 冻结实际配置与已完成过程。旧证据不重写、不补建、不清理。
- 批改携带 `expected_final_version_id / expected_review_revision`，冲突返回 409。已发布评阅拒绝存为 pending；更正追加事件、重建当前版本投影，正文仍只读。
- 无反思回答、无学生提问对应质量项不适用。仅总分不生成空分项零分。画像指标版本提升为 `2026-11-07.1`，证据 schema 保持原有结构；新算法的上线激活与重算仍须显式执行。
- 迁移 `d7e9f1a3b5c8` 保留提交、反思、评阅及证据原文，迁移当时为既有作业绑定教学快照；旧教师保留从零写作及已布置类型，段落论证默认未授权。退回开关不变。正式执行前核查授权清单并备份。

## 2026-11-09 按角色配置个人写作

管理员在「设置 → 写作辅导 → 个人写作」分别勾选「允许学生使用个人写作」「允许教师使用个人写作」并保存。学生和教师均默认关闭（2026-11-10 调整）；管理员始终可用。管理员开启对应角色后显示写作入口。关闭角色的个人写作分段、侧边栏项目及首页最近个人稿件隐藏，服务端拒绝新建、打开、编辑和新发起的个人写作 AI 对话（403）。已有稿件和对话保留，重新开启即可继续使用；作业写作、提交、批改和成长画像不受影响。设置保存在当前实例数据库，保存后新请求立即生效，无需重启；其他用户刷新页面更新入口，已经开始的生成不会被中断。

## 修订请求的模型配置隔离

- 修订请求使用独立的模型配置视图，排除模型默认系统提示词、知识库、默认技能与模型默认过滤器，并关闭自动内置工具注入；保留模型选择、思考和生成参数。初读/复看平台调用也跳过模型默认系统提示词。共享模型配置不改写，显式附件/工具、全局插件及正常历史对话不在本次清理范围。

## Teacher Teaching Runtime（2026-11-07，本地实现）

- `models/teaching_trials.py`：严格准备稿、AI 候选与证据类型；独立 `TeachingPreparation`、`AssignmentAiRevision`、`TeachingTrialSession`、`TeachingTrialEvent` 和 `TeachingCall`。`Assignment.current_ai_revision_id` 指向当前版本；版本仅追加。`config_revision` 仍负责整体作业并发检测。
- `teaching_preparations.py`：所有权、类型创建授权、准备稿 revision、完整多班事务、发布幂等及采用方案。已有作业的调整按管理权限判断，撤销类型创建授权不剥夺此能力。PATCH 不能修改段落论证生效提示词/模型；首次发布使用准备稿端点。
- `teaching_runtime.py`：在 `lock_assignment` 下重新校验学生、作业、会话和可写性；捕获版本、题目要求、稿件、上一完成稿、模型路由、非秘密生成参数和操作序号。事务在模型生成前提交。普通聊天入口先解析可信写作资源，再检查绑定模型授权，拒绝伪造资源和底模回落。
- `ai_steps.call_captured_model` 沿用 `first_read / coaching_chat / revision_review / whole_review` 登记。段落论证首读共享反馈正文接收与非空／完成度检查（2026-11-08 起不再要求模型 JSON）；聊天共享连续消息与当前稿构造，当前稿只附一次，复看不自动附旧稿。正式阅读和聊天保持原存储，试教通过独立适配器写入私有事件。
- `teaching_filters.py` 统一两条路径的全局过滤器，使用相同学生能力视图和默认个人阀值；不带个人设置、附件或工具。必须改写完整输出的 outlet 过滤器在两边均缓冲后展示，避免先显示未经处理的回复。禁止过滤器改变绑定模型或工具范围。
- `routers/openai.py` 使用服务端 request.state 中经资源校验的绑定，跳过普通模型 ACL 的范围仅限本次任务模型；不使用泛化 `bypass_filter=True`。在供应商实际发送边界记录每次尝试的最终请求与 HTTP 状态，连接密钥和认证头不入证据。
- 配置指纹包含完整提示词、绑定模型/参数、思考、题目要求、执行规则及模型环境指纹。执行实现文件、全局过滤器或可检测的路由/能力变化使旧试教失效；已发布采样参数不被后来全局默认覆盖。网络临时错误重试继续用已捕获配置。供应商内部权重变化不能可靠检测，不承诺永久逐字复现。
- 试教有操作序号和请求幂等键；已完成节点可分支。主动重测是新操作，失败和停止记录保留。正式会话同时只接纳一个 AI 调用；结果按原调用保存，不能按“当前版本”重新标注。提交只冻结已完成调用，迟到结果不写入已冻结证据。
- `stats_json.teaching_evidence` 使用 `FrozenTeachingEvidence` 严格外层及配置类型，schema 为 `2026-11-07.1`。此新增独立证据不改变旧画像证据结构，也不回填过去未知的模型归属；跨版本提交不使用一个 `coaching.task_prompt/thinking` 冒充整轮配置。
- 迁移链为 `a1c3e5f709b2` → `b2d4f6a810c3`。若旧实例已有段落论证作业，前者在任何 DDL 前要求 `TEACHING_AI_MIGRATION_MAP` 完整映射（assignment id → 严格 `AiRuntimeConfig`），题目/要求版本必须匹配，模型与思考必须明确指定。仅为切换后的请求建立 v1，不声称旧调用使用它。缺映射就停止，禁止删真实提交或推测模型。后者为新调用表增加顺序约束，拒绝对未排序的开发中间数据猜测顺序。本次未执行生产迁移。

### 2026-11-08 执行版本与证据边界补充

工作进程缓存自己的执行指纹。正式辅导版本冻结提示词和模型设置，不冻结应用代码；新正式调用的上下文记录当前执行版本，既有版本不因代码更新而被拒绝。旧试教仍按原执行指纹保留，过期后需新建试教；已接纳请求的内部重试不重新判定执行版本，教学模型撤权及路由完整性仍校验。

全局过滤器的流式适配器始终保存原始响应流，包括失败和中断；只有获得完整、非空可显示回复才认定成功。来源稿件版本只有在其正文与捕获稿件完全一致时才关联，无法匹配则保留真实正文快照而不猜测版本。

`GET /assignments/{id}/teaching-trials` 先验证作业管理权限，再仅列出当前教师本人、关联本作业准备稿/已发布版本的试教摘要；管理员也不会据此获得他人的私有试教记录。前端选择旧节点时携带当前目标准备稿，避免把正在调整的作业误带回新建流程。


### 2026-11-08 多模型试教工作台

- `teaching_comparisons.py` 模型与服务新增 `TeachingWorkbench`、`TeachingComparison`、`SavedTeachingPlan`、`TeachingPlanAdoption`。迁移 `c3e5f7a921d4`、`d4f6a8b032e5` 创建独立存储及唯一约束，不自动补造旧比较或满意方案。
- `POST /teacher/teaching-workbenches` 显式创建／恢复本人来源记录的工作稿；PUT 使用 revision。`/{id}/comparisons` 冻结共享输入并在短事务内登记 1—3 个单模型试教会话，按工作稿和请求键去重；客户端并行调用每列原 actions 接口，各列独立流式输出，不引入第二套模型执行逻辑。
- 试教动作收严为确认／初读／保存／普通交流／停止及最新失败请求重试。后台保留原请求事实，界面移除专门复看、评价、原始请求与调用记录；不删除正式学生的冻结证据或回放。
- `/teacher/saved-teaching-plans` 仅返回本人方案；保存从有完整成功输出的真实会话取不可变配置，同一来源重复保留去重。`/{plan_id}/adopt/{preparation_id}` 验证目标权限、revision、模型有效性，使用持久回执去重；不发布。新建可明确带回任务文本，已有作业拒绝通过此接口改任务。
- 试教覆盖按本人匹配的完整配置指纹查询，跨准备稿采用相同组合可以引用真实试教依据；任何题目、要求、模型或提示词不同都不能冒认已试教。


### 2026-11-08 试教反馈界面精简

试教移除 `finish` 动作及反思提交预览，不改变正式学生提交。模型卡片只提供折叠和保存方案，发送目标统一放在输入框旁；折叠仅影响显示，不取消调用、不删除历史，也不改变发送目标。结果卡不再重复展示配置；编辑后用统一提示区分当前设置与旧反馈，保存始终取原结果快照。

共享 Markdown 渲染器通过 `normalizeMarkdownTables` 处理至少三行、列数一致、带首尾竖线但缺少分隔行的表格，只补显示用的格式行；有效表格、围栏代码、缩进代码和不明确的管道文字保持不变。不回写模型响应、聊天记录或冻结证据。正式与试教共用这项显示规则。


`teaching-trial-status.ts` 从最后一个有调用证据的事件派生界面状态，优先采用最终格式校验结果，再区分最后一次供应商尝试的超时。只使用已有证据分类，不猜补错误、不回填数据库。前端刷新单列结果时同步更新比较组缓存，避免历史选择器重新展示创建时的旧快照。


### 2026-11-08 段落论证初读正文协议

`execute_first_read` 使用 `markdown-v1` 输出契约。移除强制 JSON、`_extract_json_object`、生成内容的 `ReadingFeedback` 解析、逐字引文锚定及格式重试；模型直接输出学生可阅读的正文。程序构造严格的 `TeachingTextFeedback` 内部封套，全文原样保存在 `overview`，其他辅助字段为空，因此继续复用原阅读存储、真实 ChatMessage 和冻结证据。该封套由程序生成，不要求供应商生成，未改变数据库结构。

保留过滤前原响应及过滤后可显示全文；记录 output_contract、finish_reason、实际模型和调用快照。空正文使用 `empty_response`，明确长度截断／内容过滤／工具结束使用 `incomplete_response`，均不记作成功，也不因包装格式追加模型请求。暂时性网络重试仍由原供应商调用层执行。文献综述的结构化阅读协议不在本次调整范围。

自然语言正文中的引文不再被当成已验证的定位批注，不自动改写它们。执行版本更新为 `argument-teaching-2026-11-08.text-1`；旧失败记录保持原样，旧试教请使用“重新测试”建立新快照，正式作业后续请求使用当前执行实现。


### 2026-11-08 提示词 A／B 比较

`WorkInput.comparison_mode` 默认为 `models`，保留不同模型共用提示词约束；`prompts` 严格要求两个候选，除 `prompt` 外全部候选设置一致。模式与候选随工作稿和比较组 JSON 保存，无新增 SQL 或迁移。原比较服务为每个候选生成独立会话、冻结配置并复制同一输入状态，继续复用单列 actions；保存与采用只读取所选列真实配置。正式学生调用路径与既有冻结证据不改写。


## Model fallback（2026-11-08，本地）

- `ModelMeta.fallback_model_id` 为可选管理员设置，复用模型 JSON 字段，无新增迁移。创建、更新和导入均校验管理员权限、不同连接、直连模型可用性及循环引用；普通用户不能新增或更改该设置。
- `utils/model_fallback.py` 解析平台模型 ID 到现有连接，后台使用对应凭据；下拉框只返回模型名称、ID、供应商主机名与连接序号，不返回密钥。备用只使用传输和能力设置，不注入备用模型系统提示词、知识、工具或生成参数。
- `routers/openai.py` 的提供商适配层最多发送主、备各一次；配置备用时不再执行原同供应商重试循环。仅超时或 HTTP 408/504 切换，其他 HTTP 错误直接返回。未配置备用保留原自动重发行为。非流式每路读取超时 90 秒、总时限 100 秒；流式首段/段间空闲 45 秒，开始转发后不切换；响应返回前总预算 200 秒。取消与断开不启动备用。
- 教学 `binding` 捕获备用模型、连接指纹与能力；配置变化需要正常发布新辅导版本。每次尝试保存实际模型、连接指纹、是否备用、耗时和结果，不保存密钥。初读和正式调用仍只产生一条阅读记录及一条最终回复。
- 阅读运行时把 `context.retrying` 持久化，前端在 POST 等待期间每两秒读取状态，结束/销毁停止，丢弃迟到的 GET。聊天通过既有 status 事件通知，输出开始或失败后结束重试提示。

### 2026-11-08 作业材料完整读取

- `writing_material`（迁移 `f6b8d0e254a7`）保存会话归属、原文件包路径、识别模型、材料块及确认/启用状态。材料块保留提取文字、学生核对文字、位置和 `read / unreadable / corrected`；确认后不可再改写原记录。原文件包不暴露存储路径，下载需会话本人权限，教师还须提供包含该材料的提交 ID 并通过作业权限校验。
- `/import/document` 返回 `{text, material}`，先保存待确认材料，不改稿、不进 AI 上下文。`draft-baseline` 接收材料 ID 和文字修正，与基线同事务激活。从零写作通过 `POST .../materials` 显式添加或替换，确认成功后才插入正文；附件不计正文来源占比。`GET .../materials` 返回当前材料。撤回初稿停用材料；不回填或改写历史调用/提交。
- PDF 用 PDFium 读取文字及渲染，pypdf 读取批注和链接；遇图片、矢量对象或文字解码失败时读取整页视觉材料。真正空白页跳过，脚注/页码不会作为噪声丢弃。PDFium 调用串行保护，识图并发限制为 4。Word 按 OOXML 文档顺序关联图片、注释和文本框；嵌入 BMP/TIFF/GIF 转为安全栅格预览。链接图片不自动访问外网。
- Word 的脚注/尾注有明确结构，可独立保存并在正文保留引用标记。PDF 没有统一的脚注语义结构，原生文字层中的脚注保留在导入文字中；不凭位置猜删或声称已自动完成正文/脚注语义分离。图文页的视觉识读结果另存为原页材料。
- 未配置模型、无可读输出、部分失败、模糊字符或生成截断均保留具体缺口与原件；不把缺口算成学生未提供来源。状态和提示同时进入学生预览与模型请求，未读取不成为提交门槛。输入长度超限显式拒绝，不静默截断材料。
- 初读、修改复看、普通辅导对话均携带当前正文与同一批已确认材料；附件按文件、位置、原文、来源和读取状态序列化为数据，不叠加材料评价或反馈方式指令。实际材料随 `context.materials / education_context.materials` 捕获；提交另以 `stats_json.materials` 冻结。教师在提交正文旁查看本轮原件、图片与识别文字，不读取学生后来启用的材料。
- 执行版本更新为 `argument-teaching-2026-11-08.materials-1`；识图仍使用平台 `image_parsing` 步骤，不改变教师已发布的辅导模型。PDFium 作为直接依赖固定为 5.10.1。新部署须应用迁移；本轮未部署。

### 2026-11-08 作业识图开关

- `assignment.image_reading_enabled`（迁移 `a7c9e1f365b8`）为非空布尔，默认 false；新旧作业迁移后默认关闭。创建和 PATCH 表单使用严格布尔校验，沿用教师归属权限及 `expected_config_revision` 并发检查。它是作业材料读取权限，不属于教师提示词/模型发布版本；已有提交不锁定该开关，已交配置仍保持冻结事实。
- Word/PDF 导入先捕获开关再识图；关闭时不解析模型配置、不发起视觉调用，图片块记为 `disabled` 并保留原件。识读结束重新检查开关和写入权限，期间关闭则不返回转录正文。独立照片接口同样在调用前、返回前校验。打开开关不会后台重新识别旧导入。
- `model_materials` 对后续调用构造独立材料视图：关闭时图片/页面块的自动识别文字及校订文字均不自动附带，保留未读取原因；原生注释仍可读取，原始材料记录不改写。正文中此前确认的文字和历史文本消息保留。`apply_image_reading_policy` 在请求边界移除直接图片输入及历史消息中的图片输入，不修改保存消息。
- 初读、复看、正式对话捕获 `image_reading_enabled`；开关参与阅读去重，改变后显式阅读不会误复用旧结果。提交配置、材料和真实调用保存当时开关；已发送的调用按捕获状态保留，之后关闭不重写其证据。教师试教目前仅接收文字样稿，捕获识图关闭。
- 已撤销 `material_guidance.py`、`MATERIAL_RULES` 与 `material_rules` 及全部调用，恢复内置默认辅导提示词。初读、复看、正式对话只按原有教师配置和流程协议构建 system；材料增加仅影响材料数据，不添加评价、归责或反馈方式指令。保留独立识图调用的 `EVIDENCE_PROMPT` 转录协议，它不进入辅导上下文。执行版本为 `argument-teaching-2026-11-08.material-data-1`。

### 2026-11-08 上传入口与平台模型只读视图

`TextImportActions.svelte` 使用单一文件 input，按实际文件类型分派已有文档/照片接口；文件筛选随作业开关与平台配置变化，服务端权限保持权威。混选、超限及识图不可用使用就地错误，合法重选清除错误。`baselineHelp` 只影响页面帮助，未进入模型请求。

`GET /teacher/assignment-defaults` 增加 `image_parsing_model`（null 或 `{id, name, available}`），经已有 AI 步骤配置与模型目录读取，仅返回所选模型的展示字段。缺少选择时不读取供应商目录；不回落到作业辅导模型、不调用视觉生成、不返回连接信息。教师身份校验在读取模型信息之前。新建和设置表单仅展示该字段，保存体不含平台模型选择；无新增迁移或 SQL。

### 2026-11-09 结构化图文稿件（本地实现）

- `writing_document.py` 校验有限的 Tiptap 文档节点、文字标记、尺寸和资源归属，派生纯文字投影并输出 DOCX；客户端的 HTML 不作为保存或导出依据。
- `document_layout.py` 将 DOCX 结构、PDF 原生文字/图片、复杂页、Markdown 映射到该文档。原图使用 `writingImage`，图注为节点内容，脚注使用 `writingNote`；不支持内容用显式占位。资源通过材料 ID / 块 ID 引用，不存浏览器临时 URL。
- `Note.data.pending_draft` 保存确认前的 JSON、材料选择和 revision；GET/PUT `/writing-sessions/{id}/pending-draft` 只允许归属人访问，PUT 校验写权限和初稿阶段。确认时校验所见暂存 revision 和完整内容，`Note.data.baseline` 固定初稿结构。暂存不是正式修订版本。
- 自动保存将资源启用与 Note 内容放在同一个同步数据库事务中，避免 SQLite 的同步/异步连接互锁。前端一次保存捕获一致的文档、来源和操作批次；格式和图片变化也生成版本。
- `source_material_ids` 保留本次写作已确认的上传来源；提交材料还包含初稿和历史版本引用的资源。正文替换和图片删除不使旧版本的原图失效；撤回初稿清除来源列表并停用该次材料。
- 独立图片上传保留原始文件，不先在浏览器压缩原件。识图开关只管视觉调用/自动转录传递；原生 PDF 文字层独立记录为 `MaterialBlock.native_text`，不能把无文字层的图片伪装为原生文字。
- POST `/writing-sessions/{id}/materials/{materialId}/read?block_id=...` 显式重读某张图，建立新的不可变材料记录并复用原文件包，不改旧记录。原件列表按 origin_id 合并显示。校订状态根据当前文字与原始提取结果比较，不信任客户端的来源声明。
- 模型材料从当前稿件中的真实引用和位置派生；删除/替换的图片不继续进入后续请求。初读使用基线图文，后续使用当前稿；请求保存 source_json，历史查看不用当前附件替换旧附件。不新增辅导 system 指令。
- POST `/writing-sessions/{id}/export/word` 下载已保存的当前/待确认稿并校验请求文档；GET `/submissions/{id}/export/word` 下载选定提交版本，校验学生本人或授课教师，并以 expected_version_id 拒绝过期页面静默下载另一版本。资源接口允许学生本人查看自己的冻结提交；其他教师和学生拒绝。
- 本次复用已有 JSON 列，无新增迁移；旧数据不自动重建结构。实现方案、测试和界面证据见[图文稿件优化方案](../development/图文稿件统一编辑与Word下载优化方案.md)。仅本地开发测试，未部署 HIT。

个人写作开关使用 `education.personal_writing.student / teacher`，由 `/configs/education` 管理员接口保存，运行时直接读取 Config。`/api/config` 返回当前用户的 `features.enable_personal_writing`，写作首页返回 `personal_writing_enabled`，前端据此显示入口。统一 `ensure_writing_session_access` 同时用于个人会话路由、聊天入口和模型中间件；不新增迁移或自动回填。
