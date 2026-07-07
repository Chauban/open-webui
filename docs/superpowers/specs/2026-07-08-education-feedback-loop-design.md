# 设计:作业反馈闭环(批改结果送达 + 提交轮次 + 通知)

日期:2026-07-08
状态:已与用户确认方向,待实施

## 背景与目标

现有 education 模块已实现班级/作业/写作溯源/提交/老师批改,但闭环断裂:

1. 学生**看不到**老师的批改结果(分数、评语、退回原因)——`SubmissionReview` 只暴露在 teacher 路由。
2. **没有任何通知**:作业发布、批改完成、退回重写,双方都只能靠手动刷新页面感知。
3. **重新提交会销毁历史**:重复提交覆盖旧提交并删除旧 review 与旧反思,退回—修改—重交的成长过程无法追溯。

本期目标:把「提交 → 批改 → 反馈送达 → 修改 → 重交」的循环真正闭上。

## A. 学生端查看批改结果(工作区内嵌)

### 后端

- 作业写作工作区的加载接口扩展返回当前轮 review 数据:`review_status / score / overall_comment / rubric_json / returned_comment / resubmit_due_at / reviewed_at / round_no`。
- 权限:学生只能读自己的 review;`pending` 状态只返回"已提交待批改",不含评分字段。
- `getWritingHome` 对应接口的作业列表项附带提交/批改状态,用于主页徽章。

### 前端

- `WritingWorkspaceShell.svelte` 写作面板上方新增**批改结果卡片**:
  - `reviewed`:分数、rubric 三项(ideas/structure/evidence)、总评、批改时间。
  - `returned`:醒目的退回横幅——退回评语 + **新截止时间** + "修改后重新提交"引导;编辑器同时解锁。
- 写作主页 `me/writing` 作业卡片加状态徽章:`未提交 / 已提交·待批改 / 已批改(显示分数) / 被退回(显示新截止)`。

## B. 提交轮次(批改后才开新轮)

### 数据模型(`models/education.py`)

- `Submission` 增加 `round_no`(INTEGER,默认 1)与 `is_current`(BOOLEAN);唯一约束由 `(assignment_id, student_id)` 改为 `(assignment_id, student_id, round_no)`。
- `SubmissionReview` 增加 `resubmit_due_at`(BIGINT,可空)——退回时由老师设置的重交截止时间。

### 轮次规则

- 当前轮 review 不存在或为 `pending` → 重交**覆盖当前轮**(维持现状,截止前改错别字不产生噪音)。
- 当前轮为 `reviewed / returned` → 重交创建 `round_no + 1` 新提交,旧轮 `is_current=false`;旧轮的稿件、反思、评语、分数、分析缓存**全部保留**。
- 一轮 = 一次完整的师生反馈循环。

### 退回与截止时间

- 老师执行"退回重写"时,**必须**填写重交截止时间 `resubmit_due_at`(校验:晚于当前时间),与退回评语一起保存。
- 学生该作业的**有效截止时间** = 最近一次退回的 `resubmit_due_at`;从未被退回则为作业原始 `due_at`。多次退回以最新一次为准。
- 退回后 `session.status` 从 `submitted` 回到 `draft`,工作区解锁;超过有效截止时间后照常锁定、禁止提交。
- 学生工作区的截止显示、提交校验、只读判断统一改为按有效截止时间计算。

### 老师批改页(`teacher/submissions/[submissionId]`)

- 顶部轮次切换器,默认最新轮;历史轮整页只读。
- 新增**前后稿对比**:当前轮 vs 上一轮全文 diff(后端 difflib 生成 diff 块,前端红绿标注),放入"分析" Tab。
- `reviewed` 且学生未重交时,老师可修改当前轮评语/分数(更新,不新建轮次)。
- 提交列表、dashboard、overview 统计均按**当前轮**计算;待批改数 = 当前轮为 pending 的数量。

## C. 通知(实时推送 + 未读角标)

### 数据模型

新表 `education_notification`:`id / user_id / type / payload_json / created_at / read_at(可空)`。

四种 type 与触发点(均在 router 内落库后调用 `socket/main.py` 现成的 `emit_to_users` 发 `education:notification` 事件):

| type | 触发 | 接收方 | payload 要点 |
|---|---|---|---|
| `assignment_published` | 创建作业 | 班级全体学生 | assignment_id、标题、截止时间 |
| `submission_created` | 学生提交 | 老师 | submission_id、学生名、作业标题、轮次 |
| `review_completed` | 保存 review(reviewed) | 学生 | assignment_id、分数、作业标题 |
| `submission_returned` | 保存 review(returned) | 学生 | assignment_id、退回评语摘要、**新截止时间** |

离线用户不丢通知:未读记录落库,下次登录由未读数接口补齐。

### API

- `GET /education/notifications/summary` — 未读数(按类型分组)。
- `POST /education/notifications/mark-read` — 按上下文批量标已读(如某作业相关全部)。

### 前端

- `(app)/+layout.svelte` socket 监听处注册 `education:notification` → toast(带跳转链接)+ 更新未读 store。
- 侧边栏"写作"入口(学生)与老师端入口显示未读角标。
- 已读时机:学生打开某作业工作区 → 该作业相关通知已读;老师打开提交列表/批改页 → 对应已读。

## 建表与迁移

三处 schema 变更(`Submission` 加两列、`SubmissionReview` 加一列、新 `education_notification` 表)全部写正式 **Alembic 迁移**;不使用现有运行时 `_ensure_*` 惰性建表。存量 `Submission` 数据回填 `round_no=1, is_current=true`。本期不改动老表的建表机制。

## 测试

沿用 `backend/open_webui/test/apps/webui/routers/test_education_smoke.py` 模式,覆盖:

- 轮次流转:pending 时重交=覆盖;reviewed/returned 后重交=新轮且旧轮数据完整保留。
- 退回:必须带未来的 `resubmit_due_at`;退回后解锁;有效截止时间按最新退回计算;超期禁止提交。
- 权限:学生只能读自己的 review;pending 不泄露评分字段。
- 通知:四类事件正确落库、接收方正确、mark-read 生效。

## 本期明确不做

迟交政策(标记 late)、rubric 可配置、AI 使用政策、独立通知中心页面、老师端列表实时刷新、老表建表机制改造。
