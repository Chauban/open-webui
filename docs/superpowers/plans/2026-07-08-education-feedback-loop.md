# 作业反馈闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合「提交 → 批改 → 反馈送达学生 → 修改 → 重交」循环:学生工作区内嵌批改结果、提交轮次(批改后才开新轮)、退回需设新截止时间、四类实时通知+未读角标。

**Architecture:** 后端在 `models/education.py` / `routers/education.py` 上扩展(Submission 加轮次列、SubmissionReview 加 `resubmit_due_at`、新增 `education_notification` 表),通过现成的 `socket/main.py::emit_to_users` 推送;前端扩展 `apis/education/index.ts`、`WritingWorkspaceShell.svelte`、teacher 批改页,新增未读通知 store 与角标。

**Tech Stack:** FastAPI + SQLAlchemy + Alembic(后端,SQLite 默认),SvelteKit 5 + TS(前端),Socket.IO,pytest。

**Spec:** `docs/superpowers/specs/2026-07-08-education-feedback-loop-design.md`(实现时先通读)。

## Global Constraints

- 仓库根为 `open-webui/`,以下路径均相对仓库根。本地热更新开发,**不考虑 Docker/部署**。
- Alembic 当前唯一 head 为 `5d3a8c1f7b2e`(`5d3a8c1f7b2e_merge_upstream_v0102_heads.py`),新迁移的 `down_revision` 必须是它。
- education 相关表主键为 Text(UUID 字符串),时间戳为 BigInteger(Unix 秒),布尔用 BigInteger 0/1(与 `TextSegment.is_suspected_unmarked_import` 一致)。
- 后端测试:`backend/open_webui/test/apps/webui/routers/test_education_smoke.py`,运行方式 `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -x -q`(用 `education_client` fixture,切换身份用 `UserContext.current_user = <user>`,API 前缀 `/api/v1`)。
- 前端类型检查:`cd open-webui && npm run check`(增量)。新 UI 文案一律走 `$i18n.t('...')`,同时在 `src/lib/i18n/locales/zh-CN/translation.json` 与 `en-US/translation.json` 加 key(en-US 中 key=value)。
- 提交信息用中文简述,英文前缀(feat:/fix:/test:),每个 Task 至少一次提交。
- 状态语义:`SubmissionReview.review_status ∈ {pending, reviewed, returned}`;`WritingSession.status ∈ {draft, submitted}`(assignment scope)。
- **有效截止时间规则(全局唯一定义)**:按 `round_no` 从大到小遍历该 (assignment, student) 的所有提交轮:遇到的第一个非 pending review 若为 `returned` 且有 `resubmit_due_at` → 有效截止 = `resubmit_due_at`;若为 `reviewed` → 有效截止 = `assignment.due_at`;一个都没有 → `assignment.due_at`。

---

### Task 1: 数据层 —— 轮次列、resubmit_due_at、通知表、Alembic 迁移

**Files:**
- Modify: `backend/open_webui/models/education.py`(ORM 列 + Pydantic 模型 + `_ensure_writing_tables`)
- Create: `backend/open_webui/migrations/versions/b2c4d6e8f0a1_education_feedback_loop.py`
- Modify: `backend/open_webui/test/apps/webui/routers/test_education_smoke.py`(fixture 表清单)

**Interfaces:**
- Produces(后续所有任务依赖):`Submission.round_no: BigInteger(默认1)`、`Submission.is_current: BigInteger(默认1)`;`SubmissionReview.resubmit_due_at: BigInteger 可空`;新 ORM 类 `EducationNotification(id, user_id, type, payload_json, created_at, read_at)`;Pydantic `SubmissionModel(round_no: int = 1, is_current: int = 1)`、`SubmissionReviewModel(resubmit_due_at: Optional[int] = None)`、`EducationNotificationModel`。

- [ ] **Step 1: ORM 列与 Pydantic 模型**

在 `models/education.py` 的 `Submission` 类(现第 161-171 行)末尾加两列;`SubmissionReview` 类(第 174-188 行)`reviewed_at` 之前加一列;文件的 ORM 定义区(`SubmissionReview` 类之后)加新表:

```python
# Submission 类内追加
    round_no = Column(BigInteger, nullable=False, default=1)
    is_current = Column(BigInteger, nullable=False, default=1)

# SubmissionReview 类内追加
    resubmit_due_at = Column(BigInteger, nullable=True)

# 新 ORM 类
class EducationNotification(Base):
    __tablename__ = "education_notification"

    id = Column(Text, primary_key=True, unique=True)
    user_id = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    payload_json = Column(JSONField, nullable=False, default={})
    created_at = Column(BigInteger, nullable=False)
    read_at = Column(BigInteger, nullable=True)
```

对应 Pydantic:`SubmissionModel`(现第 348 行)加 `round_no: int = 1` 与 `is_current: int = 1`;`SubmissionReviewModel`(第 361 行)加 `resubmit_due_at: Optional[int] = None`;并新增:

```python
class EducationNotificationModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: str
    payload_json: dict
    created_at: int
    read_at: Optional[int] = None
```

- [ ] **Step 2: 保护运行时建表逻辑,防止 drop 丢数据**

通读 `EducationTable._ensure_writing_tables`(约第 703-764 行)。它在模型列与库内列不匹配时会 drop 重建部分表。在它对 `submission` / `submission_review` 做任何 mismatch 处理**之前**,先补齐缺失列(幂等),并把 `EducationNotification.__table__` 加入该函数的建表清单。在 `EducationTable` 类内加辅助方法:

```python
    def _sqlite_add_missing_columns(
        self, db: Session, table_name: str, columns: dict[str, str]
    ) -> None:
        try:
            rows = db.execute(text(f'PRAGMA table_info("{table_name}")')).fetchall()
        except OperationalError:
            return
        if not rows:
            return
        existing = {row[1] for row in rows}
        changed = False
        for name, ddl in columns.items():
            if name not in existing:
                db.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {name} {ddl}'))
                changed = True
        if changed:
            db.commit()
```

在 `_ensure_writing_tables` 开头调用:

```python
        self._sqlite_add_missing_columns(
            db,
            "submission",
            {
                "round_no": "BIGINT NOT NULL DEFAULT 1",
                "is_current": "BIGINT NOT NULL DEFAULT 1",
            },
        )
        self._sqlite_add_missing_columns(
            db, "submission_review", {"resubmit_due_at": "BIGINT"}
        )
```

若该函数存在「列不匹配 → drop 重建」的分支且覆盖 `submission`/`submission_review`,确认补列后不会再触发 drop(补列在前即可)。

- [ ] **Step 3: Alembic 迁移**

创建 `backend/open_webui/migrations/versions/b2c4d6e8f0a1_education_feedback_loop.py`:

```python
"""education feedback loop: submission rounds, resubmit due, notifications

Revision ID: b2c4d6e8f0a1
Revises: 5d3a8c1f7b2e
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, Sequence[str], None] = "5d3a8c1f7b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(inspector, table: str) -> set:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "submission" in tables:
        columns = _existing_columns(inspector, "submission")
        if "round_no" not in columns:
            op.execute(
                "ALTER TABLE submission ADD COLUMN round_no BIGINT NOT NULL DEFAULT 1"
            )
        if "is_current" not in columns:
            op.execute(
                "ALTER TABLE submission ADD COLUMN is_current BIGINT NOT NULL DEFAULT 1"
            )

    if "submission_review" in tables:
        columns = _existing_columns(inspector, "submission_review")
        if "resubmit_due_at" not in columns:
            op.execute(
                "ALTER TABLE submission_review ADD COLUMN resubmit_due_at BIGINT"
            )

    op.execute(
        "CREATE TABLE IF NOT EXISTS education_notification ("
        "id TEXT PRIMARY KEY, "
        "user_id TEXT NOT NULL, "
        "type TEXT NOT NULL, "
        "payload_json TEXT NOT NULL DEFAULT '{}', "
        "created_at BIGINT NOT NULL, "
        "read_at BIGINT)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS education_notification_user_idx "
        "ON education_notification (user_id, read_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS education_notification")
    # SQLite 不支持 DROP COLUMN(旧版),轮次列保留无害,不回退
```

- [ ] **Step 4: 测试 fixture 注册新表**

`test_education_smoke.py`:import 处(第 21-31 行)加 `EducationNotification`;fixture 的建表清单(第 389-407 行)加 `EducationNotification.__table__`。

- [ ] **Step 5: 跑现有测试确认无回归**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -x -q`
Expected: 全部 PASS(新列有默认值,旧逻辑不受影响)。

- [ ] **Step 6: 验证迁移在真实 dev 库上可跑**

Run(backend 目录): `python -c "from alembic.config import Config; from alembic import command; cfg = Config('open_webui/alembic.ini'); cfg.set_main_option('script_location', 'open_webui/migrations'); command.upgrade(cfg, 'head')"`
若项目启动时自动跑迁移(`open_webui/config.py` / `main.py` 里有 `run_migrations`),也可直接启动一次后端验证无报错。Expected: 升级成功,`submission` 表出现 `round_no/is_current` 列。

- [ ] **Step 7: Commit**

```bash
git add backend/open_webui/models/education.py backend/open_webui/migrations/versions/b2c4d6e8f0a1_education_feedback_loop.py backend/open_webui/test/apps/webui/routers/test_education_smoke.py
git commit -m "feat: 提交轮次/重交截止/通知表的数据层与迁移"
```

---

### Task 2: 轮次提交与退回逻辑(后端核心)

**Files:**
- Modify: `backend/open_webui/models/education.py`(`insert_submission` 重写 + 新查询方法 + `SubmissionReviewForm` + `upsert_submission_review` + session 状态方法)
- Modify: `backend/open_webui/routers/education.py`(submit 端点第 2680-2805 行、review 端点第 3020-3049 行、新增 `_get_effective_due_at`)
- Test: `backend/open_webui/test/apps/webui/routers/test_education_smoke.py`

**Interfaces:**
- Consumes: Task 1 的列与模型。
- Produces:
  - `Education.get_current_submission(assignment_id: str, student_id: str, db=None) -> Optional[SubmissionModel]`
  - `Education.get_submission_rounds(assignment_id: str, student_id: str, db=None) -> list[SubmissionModel]`(round_no 降序)
  - `Education.set_writing_session_status(session_id: str, status: str, db=None) -> None`
  - `routers/education.py::_get_effective_due_at(assignment, student_id: str, db) -> Optional[int]`(全局约束里的规则)
  - `SubmissionReviewForm.resubmit_due_at: Optional[int] = None`
  - review 端点行为:`returned` 必须带未来的 `resubmit_due_at`,退回后 session.status="draft";历史轮(`is_current==0`)禁止保存 review(400)。

- [ ] **Step 1: 写失败测试**

在 `test_education_smoke.py` 末尾追加(`_prepare_assignment_flow` 已存在,返回 dict 含 classroom/assignment/workspace/submission;沿用其风格,必要时直接内联搭流程,参考现有 `test_submission_accepts_multiple_ai_help_types` 第 551-596 行的搭建方式):

```python
def _submit_body(session_id: str, text: str):
    return {
        "writing_session_id": session_id,
        "final_content_json": None,
        "final_content_html": f"<p>{text}</p>",
        "final_content_text": text,
        "ai_help_types": ["Outline"],
        "reflection_text": "I used AI for outlining then rewrote every paragraph in my own words.",
    }


def _setup_submitted_assignment(client, teacher, student, title="Round Essay"):
    UserContext.current_user = teacher
    classroom = client.post("/api/v1/classrooms", json={"name": f"CR {title}"}).json()[
        "classroom"
    ]
    assignment = client.post(
        "/api/v1/assignments",
        json={"title": title, "classroom_id": classroom["id"], "due_at": 2000000000},
    ).json()
    UserContext.current_user = student
    client.post("/api/v1/classrooms/join", json={"invite_code": classroom["invite_code"]})
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    session_id = workspace["writing_session"]["id"]
    submit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "first draft text for the round essay"),
    )
    assert submit_res.status_code == 200, submit_res.text
    return assignment, session_id, submit_res.json()["submission_id"]


def test_resubmit_before_review_overwrites_same_round(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Overwrite Round"
    )

    resubmit_res = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "second draft replacing the first one entirely"),
    )
    assert resubmit_res.status_code == 200, resubmit_res.text
    assert resubmit_res.json()["submission_id"] == submission_id

    UserContext.current_user = teacher
    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    ).json()
    assert len(submissions) == 1
    assert submissions[0]["submission"]["round_no"] == 1


def test_returned_submission_opens_new_round_and_keeps_history(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Return Round"
    )

    UserContext.current_user = teacher
    # 退回必须带未来的 resubmit_due_at
    missing_due = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "returned", "returned_comment": "Please revise"},
    )
    assert missing_due.status_code == 400, missing_due.text

    returned = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Please revise the argument",
            "resubmit_due_at": 2100000000,
        },
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["resubmit_due_at"] == 2100000000

    # 退回后学生会话解锁为 draft
    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["writing_session"]["status"] == "draft"

    # 重交 → 新轮,旧轮与旧评语保留
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "revised draft after teacher returned it"),
    )
    assert resubmit.status_code == 200, resubmit.text
    new_submission_id = resubmit.json()["submission_id"]
    assert new_submission_id != submission_id

    UserContext.current_user = teacher
    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/submissions"
    ).json()
    assert len(submissions) == 1  # 列表只显示当前轮
    assert submissions[0]["submission"]["id"] == new_submission_id
    assert submissions[0]["submission"]["round_no"] == 2

    old_review = client.get(
        f"/api/v1/teacher/submissions/{submission_id}/review"
    ).json()
    assert old_review["review_status"] == "returned"
    assert old_review["returned_comment"] == "Please revise the argument"

    # 历史轮禁止再保存评语
    historic_save = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "reviewed", "score": 80},
    )
    assert historic_save.status_code == 400, historic_save.text


def test_effective_due_uses_resubmit_due_after_return(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Due Round"
    )

    UserContext.current_user = teacher
    past_due = int(__import__("time").time()) - 3600
    # 先把作业原截止改到过去(PATCH /assignments/{id})
    client.patch(f"/api/v1/assignments/{assignment['id']}", json={"due_at": past_due})

    UserContext.current_user = student
    blocked = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "late resubmit should be blocked now"),
    )
    assert blocked.status_code == 400, blocked.text

    UserContext.current_user = teacher
    future_due = int(__import__("time").time()) + 3600
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Late but returned for revision",
            "resubmit_due_at": future_due,
        },
    )

    UserContext.current_user = student
    allowed = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "resubmit within the new resubmit window"),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["submission_id"] != submission_id
```

注意:若 `PATCH /assignments/{assignment_id}`(第 1439 行 `update_assignment`)的表单不接受 `due_at`,读其 `AssignmentUpdateForm` 并按实际字段调整测试;若确实无法把截止改到过去,改用 `SessionLocal` 直接 UPDATE assignment.due_at(fixture 第六个返回值)。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q -k "round or effective_due"`
Expected: FAIL(round_no 尚不存在于响应/重交仍覆盖删评语/缺 resubmit_due_at 校验)。

- [ ] **Step 3: 模型层实现**

`models/education.py`:

3a. `SubmissionReviewForm`(第 562 行)加 `resubmit_due_at: Optional[int] = None`。

3b. 重写 `insert_submission`(第 1665-1726 行)为轮次逻辑:

```python
    def insert_submission(
        self,
        assignment_id: str,
        student_id: str,
        writing_session_id: str,
        final_version_id: str,
        stats_json: dict,
        micro_reflection_id: str,
        db: Optional[Session] = None,
    ) -> SubmissionModel:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            now = int(time.time())
            current = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.round_no.desc())
                .first()
            )
            review = (
                db.query(SubmissionReview)
                .filter(SubmissionReview.submission_id == current.id)
                .first()
                if current is not None
                else None
            )

            if current is None or (
                review is not None and review.review_status in ("reviewed", "returned")
            ):
                # 首轮,或已批改/退回后的重交:开新轮,旧轮完整保留
                if current is not None:
                    current.is_current = 0
                submission = Submission(
                    id=str(uuid.uuid4()),
                    assignment_id=assignment_id,
                    student_id=student_id,
                    writing_session_id=writing_session_id,
                    final_version_id=final_version_id,
                    stats_json=stats_json,
                    micro_reflection_id=micro_reflection_id,
                    submitted_at=now,
                    round_no=1 if current is None else current.round_no + 1,
                    is_current=1,
                )
                db.add(submission)
            else:
                # 未批改(无 review 或 pending):覆盖当前轮
                previous_reflection_id = current.micro_reflection_id
                current.writing_session_id = writing_session_id
                current.final_version_id = final_version_id
                current.stats_json = stats_json
                current.micro_reflection_id = micro_reflection_id
                current.submitted_at = now
                if review is not None:
                    db.delete(review)
                if (
                    previous_reflection_id
                    and previous_reflection_id != micro_reflection_id
                ):
                    db.query(MicroReflection).filter(
                        MicroReflection.id == previous_reflection_id
                    ).delete(synchronize_session=False)
                submission = current

            db.commit()
            db.refresh(submission)

            session = db.get(WritingSession, writing_session_id)
            if session is not None:
                session.status = "submitted"
                session.submitted_submission_id = submission.id
                session.updated_at = int(time.time())
                db.commit()

            return SubmissionModel.model_validate(submission)
```

3c. 新查询方法(放在 `get_submission_by_id` 附近):

```python
    def get_current_submission(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> Optional[SubmissionModel]:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            submission = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                    Submission.is_current == 1,
                )
                .order_by(Submission.round_no.desc())
                .first()
            )
            return SubmissionModel.model_validate(submission) if submission else None

    def get_submission_rounds(
        self, assignment_id: str, student_id: str, db: Optional[Session] = None
    ) -> list[SubmissionModel]:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            submissions = (
                db.query(Submission)
                .filter(
                    Submission.assignment_id == assignment_id,
                    Submission.student_id == student_id,
                )
                .order_by(Submission.round_no.desc())
                .all()
            )
            return [SubmissionModel.model_validate(s) for s in submissions]

    def set_writing_session_status(
        self, session_id: str, status: str, db: Optional[Session] = None
    ) -> None:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            session = db.get(WritingSession, session_id)
            if session is not None:
                session.status = status
                session.updated_at = int(time.time())
                db.commit()
```

3d. **当前轮口径**:`get_submissions_by_assignment`(第 1812 行)加过滤 `Submission.is_current == 1`。再 `grep -n "db.query(Submission)" backend/open_webui/models/education.py`,除上面三个新方法与 `get_submission_by_id` 外,其余所有按 assignment/student 聚合统计的查询(teacher overview、classroom progress、student dashboard 等)全部补 `Submission.is_current == 1` 过滤,保持"统计=当前轮"。

3e. `upsert_submission_review`(第 1756 行):新建与更新两个分支均写入 `review.resubmit_due_at = form_data.resubmit_due_at`。

- [ ] **Step 4: 路由层实现**

`routers/education.py`:

4a. 新增 helper(放在 `_get_assignment_or_404` 附近):

```python
def _get_effective_due_at(assignment, student_id: str, db: Session) -> Optional[int]:
    for submission in Education.get_submission_rounds(
        assignment.id, student_id, db=db
    ):
        review = Education.get_submission_review_by_submission_id(
            submission.id, db=db
        )
        if review is None or review.review_status == "pending":
            continue
        if review.review_status == "returned" and review.resubmit_due_at:
            return review.resubmit_due_at
        break  # reviewed:本作业反馈循环已关闭,回落到原始截止
    return assignment.due_at
```

4b. `submit_assignment`(第 2693-2698 行)把原 due 校验替换为:

```python
    effective_due_at = _get_effective_due_at(assignment, user.id, db)
    if effective_due_at is not None and effective_due_at <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment due time has passed",
        )
```

4c. `save_submission_review`(第 3020-3049 行)在状态校验后追加:

```python
    if not submission.is_current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Historical submission rounds are read-only",
        )
    if form_data.review_status == "returned":
        if (
            form_data.resubmit_due_at is None
            or form_data.resubmit_due_at <= int(time.time())
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A future resubmit due time is required when returning",
            )
```

并在 `upsert_submission_review` 调用之后:

```python
    if form_data.review_status == "returned":
        Education.set_writing_session_status(
            submission.writing_session_id, "draft", db=db
        )
```

4d. **分析缓存按轮隔离**:读 `_get_or_build_submission_analysis`(第 1226 行起)与 `Education.get_analysis_result` / `upsert_analysis_result`(第 1570-1628 行附近)。把缓存命中条件加上 `submission_id` 匹配:`get_analysis_result` 增加可选参数 `submission_id: Optional[str] = None`,传入时 filter 追加 `AnalysisResult.submission_id == submission_id`;`upsert_analysis_result` 的查找 filter 同样在 `submission_id` 非空时追加该条件(这样每轮各有一行缓存,旧轮分析不被新轮覆盖)。`_get_or_build_submission_analysis` 调用处传 `submission_id=submission.id`。

- [ ] **Step 5: 跑测试至全绿**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q`
Expected: 新增 3 个测试 PASS,既有测试无回归(尤其 `test_education_classroom_main_flow`)。

- [ ] **Step 6: Commit**

```bash
git add backend/open_webui/models/education.py backend/open_webui/routers/education.py backend/open_webui/test/apps/webui/routers/test_education_smoke.py
git commit -m "feat: 提交轮次流转与退回重交截止时间(后端)"
```

---

### Task 3: 学生端 payload —— 工作区 review 视图 + 主页徽章字段(后端)

**Files:**
- Modify: `backend/open_webui/models/education.py`(响应模型加字段)
- Modify: `backend/open_webui/routers/education.py`(`get_assignment_workspace` 第 2168-2262 行、`get_writing_home` 第 2265-2350 行)
- Test: `backend/open_webui/test/apps/webui/routers/test_education_smoke.py`

**Interfaces:**
- Consumes: Task 2 的 `Education.get_current_submission`、`_get_effective_due_at`;测试 helper `_submit_body(session_id, text)` 与 `_setup_submitted_assignment(client, teacher, student, title) -> (assignment, session_id, submission_id)`(Task 2 已加入 test_education_smoke.py 末尾)。
- Produces:
  - `AssignmentWorkspaceResponse` 增加 `review: Optional[dict] = None`、`effective_due_at: Optional[int] = None`。
  - `AssignmentWorkspaceListItem` 增加 `review_status: Optional[str] = None`、`score: Optional[int] = None`、`effective_due_at: Optional[int] = None`、`round_no: Optional[int] = None`。
  - review dict 结构(前端依赖):`{round_no, submitted_at, review_status}`;`reviewed` 时另含 `score, overall_comment, rubric, reviewed_at`;`returned` 时另含 `returned_comment, resubmit_due_at, reviewed_at`。**pending 不含任何评分字段。**

- [ ] **Step 1: 写失败测试**

```python
def test_student_workspace_exposes_review_after_grading(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Student View"
    )

    # 批改前:pending,不泄露评分字段
    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "pending"
    assert "score" not in workspace["review"]
    assert workspace["effective_due_at"] == 2000000000

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "reviewed",
            "score": 88,
            "overall_comment": "Strong structure",
            "rubric_json": {"ideas": 30, "structure": 29, "evidence": 29},
        },
    )

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "reviewed"
    assert workspace["review"]["score"] == 88
    assert workspace["review"]["overall_comment"] == "Strong structure"
    assert workspace["review"]["rubric"]["ideas"] == 30

    home = client.get("/api/v1/me/writing/home").json()
    item = next(
        i for i in home["assignment_items"] if i["assignment"]["id"] == assignment["id"]
    )
    assert item["review_status"] == "reviewed"
    assert item["score"] == 88


def test_student_workspace_exposes_returned_state(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Returned View"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Add evidence in paragraph two",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    workspace = client.get(f"/api/v1/assignments/{assignment['id']}/workspace").json()
    assert workspace["review"]["review_status"] == "returned"
    assert workspace["review"]["returned_comment"] == "Add evidence in paragraph two"
    assert workspace["review"]["resubmit_due_at"] == 2100000000
    assert workspace["effective_due_at"] == 2100000000
    assert workspace["writing_session"]["status"] == "draft"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q -k "student_workspace"`
Expected: FAIL(响应无 `review`/`effective_due_at` 字段)。

- [ ] **Step 3: 实现**

3a. `models/education.py` `AssignmentWorkspaceResponse`(第 406 行)加 `review: Optional[dict] = None` 与 `effective_due_at: Optional[int] = None`;`AssignmentWorkspaceListItem`(第 499 行)加 Interfaces 所列 4 个字段。

3b. `routers/education.py` 新增 helper:

```python
def _build_student_review_view(
    assignment, student_id: str, db: Session
) -> tuple[Optional[dict], Optional[int]]:
    effective_due_at = _get_effective_due_at(assignment, student_id, db)
    submission = Education.get_current_submission(assignment.id, student_id, db=db)
    if submission is None:
        return None, effective_due_at
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    view = {
        "round_no": submission.round_no,
        "submitted_at": submission.submitted_at,
        "review_status": review.review_status if review else "pending",
    }
    if review and review.review_status == "reviewed":
        view.update(
            {
                "score": review.score,
                "overall_comment": review.overall_comment,
                "rubric": review.rubric_json,
                "reviewed_at": review.reviewed_at,
            }
        )
    elif review and review.review_status == "returned":
        view.update(
            {
                "returned_comment": review.returned_comment,
                "resubmit_due_at": review.resubmit_due_at,
                "reviewed_at": review.reviewed_at,
            }
        )
    return view, effective_due_at
```

3c. `get_assignment_workspace` 的**两个** `return AssignmentWorkspaceResponse(...)`(第 2244 与 2254 行)都补:

```python
    review_view, effective_due_at = _build_student_review_view(assignment, user.id, db)
    # ...
        review=review_view,
        effective_due_at=effective_due_at,
```

(新建 session 的分支里 review 必为 None,直接同样调用即可,不必特判。)

3d. `get_writing_home` 学生分支(第 2294-2332 行):有 session 时构造 item 前取 `review_view, effective_due_at = _build_student_review_view(assignment, user.id, db)`,item 增加:

```python
                    review_status=review_view["review_status"] if review_view else None,
                    score=(review_view or {}).get("score"),
                    round_no=(review_view or {}).get("round_no"),
                    effective_due_at=effective_due_at,
```

无 session 的 `not_started` 分支只补 `effective_due_at=assignment.due_at`。

- [ ] **Step 4: 跑测试至全绿**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/models/education.py backend/open_webui/routers/education.py backend/open_webui/test/apps/webui/routers/test_education_smoke.py
git commit -m "feat: 学生端工作区/主页返回批改结果与有效截止时间"
```

---

### Task 4: 教师端轮次列表 + 前后稿 diff 端点(后端)

**Files:**
- Modify: `backend/open_webui/models/education.py`(`SubmissionDetailResponse` 加 rounds 字段、`get_version_by_id` 方法若缺则加)
- Modify: `backend/open_webui/routers/education.py`(`get_submission_detail` 第 2828 行起、新 diff 端点)
- Test: `backend/open_webui/test/apps/webui/routers/test_education_smoke.py`

**Interfaces:**
- Consumes: Task 2 的 `get_submission_rounds`;测试 helper `_submit_body` / `_setup_submitted_assignment`(Task 2 已加入 test_education_smoke.py)。
- Produces:
  - `SubmissionDetailResponse.rounds: list[dict]`,每项 `{submission_id, round_no, submitted_at, is_current, review_status, score}`(round_no 降序)。
  - `GET /teacher/submissions/{submission_id}/diff` → `{"has_previous": bool, "previous_round_no": Optional[int], "blocks": [{"op": "equal|insert|delete|replace", "old_text": str, "new_text": str}]}`。
  - `Education.get_version_by_id(version_id: str, db=None) -> Optional[WritingVersionModel]`。

- [ ] **Step 1: 写失败测试**

```python
def test_teacher_sees_rounds_and_diff(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, first_submission_id = _setup_submitted_assignment(
        client, teacher, student, "Rounds Diff"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{first_submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Rewrite the ending",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    resubmit = client.post(
        f"/api/v1/assignments/{assignment['id']}/submit",
        json=_submit_body(session_id, "first draft text for the round essay with a new ending"),
    )
    second_submission_id = resubmit.json()["submission_id"]

    UserContext.current_user = teacher
    detail = client.get(f"/api/v1/teacher/submissions/{second_submission_id}").json()
    rounds = detail["rounds"]
    assert [r["round_no"] for r in rounds] == [2, 1]
    assert rounds[0]["is_current"] == 1
    assert rounds[1]["review_status"] == "returned"

    diff = client.get(
        f"/api/v1/teacher/submissions/{second_submission_id}/diff"
    ).json()
    assert diff["has_previous"] is True
    assert diff["previous_round_no"] == 1
    ops = {block["op"] for block in diff["blocks"]}
    assert "equal" in ops
    assert ("insert" in ops) or ("replace" in ops)

    first_diff = client.get(
        f"/api/v1/teacher/submissions/{first_submission_id}/diff"
    ).json()
    assert first_diff["has_previous"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q -k "rounds_and_diff"`
Expected: FAIL(无 rounds 字段、diff 404)。

- [ ] **Step 3: 实现**

3a. `models/education.py`:`SubmissionDetailResponse`(第 587 行)加 `rounds: list[dict] = Field(default_factory=list)`。检查 `EducationTable` 是否已有按 id 取版本的方法(`grep -n "def get_version" backend/open_webui/models/education.py`);若无:

```python
    def get_version_by_id(
        self, version_id: str, db: Optional[Session] = None
    ) -> Optional[WritingVersionModel]:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            version = db.get(WritingVersion, version_id)
            return WritingVersionModel.model_validate(version) if version else None
```

3b. `routers/education.py` `get_submission_detail` 构造响应前:

```python
    rounds = [
        {
            "submission_id": item.id,
            "round_no": item.round_no,
            "submitted_at": item.submitted_at,
            "is_current": item.is_current,
            "review_status": (
                item_review.review_status if item_review else "pending"
            ),
            "score": item_review.score if item_review else None,
        }
        for item in Education.get_submission_rounds(
            submission.assignment_id, submission.student_id, db=db
        )
        for item_review in [
            Education.get_submission_review_by_submission_id(item.id, db=db)
        ]
    ]
```

响应构造处传 `rounds=rounds`。

3c. diff 端点(文件顶部 `import difflib`):

```python
@router.get("/teacher/submissions/{submission_id}/diff")
async def get_submission_round_diff(
    submission_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _ensure_teacher_identity(user)
    submission = Education.get_submission_by_id(submission_id, db=db)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    assignment = _get_assignment_or_404(submission.assignment_id, db)
    _ensure_assignment_access(user, assignment, db, require_teacher=True)

    previous = next(
        (
            item
            for item in Education.get_submission_rounds(
                submission.assignment_id, submission.student_id, db=db
            )
            if item.round_no == submission.round_no - 1
        ),
        None,
    )
    if previous is None:
        return {"has_previous": False, "previous_round_no": None, "blocks": []}

    current_version = Education.get_version_by_id(submission.final_version_id, db=db)
    previous_version = Education.get_version_by_id(previous.final_version_id, db=db)
    old_text = (previous_version.note_snapshot_text or "") if previous_version else ""
    new_text = (current_version.note_snapshot_text or "") if current_version else ""
    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    blocks = [
        {
            "op": op,
            "old_text": old_text[i1:i2],
            "new_text": new_text[j1:j2],
        }
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
    ]
    return {
        "has_previous": True,
        "previous_round_no": previous.round_no,
        "blocks": blocks,
    }
```

- [ ] **Step 4: 跑测试至全绿**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/models/education.py backend/open_webui/routers/education.py backend/open_webui/test/apps/webui/routers/test_education_smoke.py
git commit -m "feat: 教师端提交轮次列表与前后稿 diff 端点"
```

---

### Task 5: 通知后端 —— 落库、触发、API

**Files:**
- Modify: `backend/open_webui/models/education.py`(通知 CRUD 方法)
- Modify: `backend/open_webui/routers/education.py`(通知 helper + 三个触发点 + 两个端点)
- Test: `backend/open_webui/test/apps/webui/routers/test_education_smoke.py`

**Interfaces:**
- Consumes: Task 1 的 `EducationNotification`/`EducationNotificationModel`;`socket/main.py::emit_to_users(event, data, user_ids)`(已存在,内部吞异常,测试环境无连接也安全);测试 helper `_submit_body` / `_setup_submitted_assignment`(Task 2 已加入 test_education_smoke.py)。
- Produces:
  - `Education.insert_notifications(user_ids: list[str], type: str, payload: dict, db=None) -> int`
  - `Education.get_unread_notification_summary(user_id: str, db=None) -> dict`(`{"total": int, "by_type": {type: count}}`)
  - `Education.mark_notifications_read(user_id, types: Optional[list[str]] = None, assignment_id: Optional[str] = None, db=None) -> int`
  - `GET /me/notifications/summary`、`POST /me/notifications/mark-read`(body `{types?, assignment_id?}` → `{"marked": n}`)
  - 通知类型常量:`assignment_published | submission_created | review_completed | submission_returned`

- [ ] **Step 1: 写失败测试**

```python
def test_notifications_flow(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Notify Round"
    )

    # 学生:布置作业时收到 assignment_published
    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("assignment_published") == 1

    # 老师:学生提交后收到 submission_created
    UserContext.current_user = teacher
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("submission_created") == 1

    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={"review_status": "reviewed", "score": 90},
    )

    # 学生:批改完成收到 review_completed
    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("review_completed") == 1

    # 按作业上下文标已读
    marked = client.post(
        "/api/v1/me/notifications/mark-read",
        json={"assignment_id": assignment["id"]},
    ).json()
    assert marked["marked"] >= 2  # assignment_published + review_completed
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["total"] == 0


def test_returned_review_sends_return_notification(education_client):
    client, teacher, _, student, _, _ = education_client
    assignment, session_id, submission_id = _setup_submitted_assignment(
        client, teacher, student, "Notify Return"
    )

    UserContext.current_user = teacher
    client.post(
        f"/api/v1/teacher/submissions/{submission_id}/review",
        json={
            "review_status": "returned",
            "returned_comment": "Needs another pass",
            "resubmit_due_at": 2100000000,
        },
    )

    UserContext.current_user = student
    summary = client.get("/api/v1/me/notifications/summary").json()
    assert summary["by_type"].get("submission_returned") == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q -k "notification"`
Expected: FAIL(404,端点不存在)。

- [ ] **Step 3: 模型层实现**

`models/education.py` `EducationTable` 内(import 区补 `EducationNotification` 已在同文件,无需 import):

```python
    def insert_notifications(
        self,
        user_ids: list[str],
        type: str,
        payload: dict,
        db: Optional[Session] = None,
    ) -> int:
        if not user_ids:
            return 0
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            now = int(time.time())
            for user_id in user_ids:
                db.add(
                    EducationNotification(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        type=type,
                        payload_json=payload,
                        created_at=now,
                        read_at=None,
                    )
                )
            db.commit()
            return len(user_ids)

    def get_unread_notification_summary(
        self, user_id: str, db: Optional[Session] = None
    ) -> dict:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            rows = (
                db.query(EducationNotification)
                .filter(
                    EducationNotification.user_id == user_id,
                    EducationNotification.read_at.is_(None),
                )
                .all()
            )
            by_type: dict[str, int] = {}
            for row in rows:
                by_type[row.type] = by_type.get(row.type, 0) + 1
            return {"total": len(rows), "by_type": by_type}

    def mark_notifications_read(
        self,
        user_id: str,
        types: Optional[list[str]] = None,
        assignment_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        with get_db_context(db) as db:
            self._ensure_writing_tables(db)
            query = db.query(EducationNotification).filter(
                EducationNotification.user_id == user_id,
                EducationNotification.read_at.is_(None),
            )
            if types:
                query = query.filter(EducationNotification.type.in_(types))
            rows = query.all()
            now = int(time.time())
            marked = 0
            for row in rows:
                if assignment_id is not None:
                    payload = row.payload_json or {}
                    if payload.get("assignment_id") != assignment_id:
                        continue
                row.read_at = now
                marked += 1
            db.commit()
            return marked
```

同时确认 `_ensure_writing_tables` 的建表清单包含 `EducationNotification.__table__`(Task 1 已加,若漏则补)。

- [ ] **Step 4: 路由层实现**

`routers/education.py`:

4a. 顶部 import:`from open_webui.socket.main import emit_to_users`。若引入造成循环 import(启动报错),改为在 helper 函数体内局部 import。

4b. helper:

```python
async def _send_education_notifications(
    user_ids: list[str], notification_type: str, payload: dict, db: Session
) -> None:
    if not user_ids:
        return
    Education.insert_notifications(user_ids, notification_type, payload, db=db)
    await emit_to_users(
        "education:notification",
        {"type": notification_type, "payload": payload},
        user_ids,
    )
```

4c. 三个触发点:

- `create_assignment`(第 1408 行)返回前:取班级学生(`grep -n "def get_classroom_members" backend/open_webui/models/education.py` 找现成方法;若只有按 classroom_id 查 member 的方法,过滤 `member_role == "student"`):

```python
    student_ids = [
        member.user_id
        for member in Education.get_classroom_members(assignment.classroom_id, db=db)
        if member.member_role == "student"
    ]
    await _send_education_notifications(
        student_ids,
        "assignment_published",
        {
            "assignment_id": assignment.id,
            "assignment_title": assignment.title,
            "due_at": assignment.due_at,
        },
        db,
    )
```

(方法名以 grep 结果为准,不要凭空造名。)

- `submit_assignment`(第 2805 行 return 前):

```python
    await _send_education_notifications(
        [assignment.teacher_id],
        "submission_created",
        {
            "assignment_id": assignment.id,
            "assignment_title": assignment.title,
            "submission_id": submission.id,
            "student_id": user.id,
            "student_name": user.name,
            "round_no": submission.round_no,
        },
        db,
    )
```

- `save_submission_review` 保存成功后(pending 不发):

```python
    if form_data.review_status == "reviewed":
        await _send_education_notifications(
            [submission.student_id],
            "review_completed",
            {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "score": form_data.score,
            },
            db,
        )
    elif form_data.review_status == "returned":
        await _send_education_notifications(
            [submission.student_id],
            "submission_returned",
            {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "returned_comment": form_data.returned_comment,
                "resubmit_due_at": form_data.resubmit_due_at,
            },
            db,
        )
```

4d. 端点(与 `/me/writing/...` 并列风格):

```python
class NotificationMarkReadForm(BaseModel):
    types: Optional[list[str]] = None
    assignment_id: Optional[str] = None


@router.get("/me/notifications/summary")
async def get_my_notification_summary(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    return Education.get_unread_notification_summary(user.id, db=db)


@router.post("/me/notifications/mark-read")
async def mark_my_notifications_read(
    form_data: NotificationMarkReadForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    marked = Education.mark_notifications_read(
        user.id,
        types=form_data.types,
        assignment_id=form_data.assignment_id,
        db=db,
    )
    return {"marked": marked}
```

- [ ] **Step 5: 跑测试至全绿**

Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q`
Expected: 全部 PASS(emit_to_users 在测试环境无 socket 连接时静默)。

- [ ] **Step 6: Commit**

```bash
git add backend/open_webui/models/education.py backend/open_webui/routers/education.py backend/open_webui/test/apps/webui/routers/test_education_smoke.py
git commit -m "feat: 教育通知落库、三类触发与未读/已读 API"
```

---

### Task 6: 前端 API 封装 + 学生端 UI(批改结果卡片、有效截止、主页徽章)

**Files:**
- Modify: `src/lib/apis/education/index.ts`
- Create: `src/lib/components/education/ReviewResultCard.svelte`
- Modify: `src/lib/components/education/WritingWorkspaceShell.svelte`
- Modify: `src/routes/(app)/assignments/[assignmentId]/write/+page.svelte`(透传新字段;先读该文件确认 props 流向)
- Modify: `src/routes/(app)/me/writing/+page.svelte`(作业卡片徽章)
- Modify: `src/lib/i18n/locales/zh-CN/translation.json`、`src/lib/i18n/locales/en-US/translation.json`

**Interfaces:**
- Consumes: Task 3 的 `AssignmentWorkspaceResponse.review / effective_due_at`、home item 的 `review_status / score / effective_due_at / round_no`;Task 5 的 `/me/notifications/*`(封装函数在本任务加,接线在 Task 8)。
- Produces:
  - `getEducationNotificationSummary(token) -> {total, by_type}`、`markEducationNotificationsRead(token, {types?, assignment_id?})`、`getSubmissionRoundDiff(token, submissionId)`(供 Task 7/8 用;签名与文件内现有函数风格一致 —— fetch → `res.json()`,错误抛出)。
  - `ReviewResultCard.svelte` props:`review: 上述 review dict`、`onRevise: () => void`(可选,退回横幅"去修改"回调,不传则不渲染按钮)。

- [ ] **Step 1: API 封装**

按 `src/lib/apis/education/index.ts` 内现有函数(如 `getSubmissionReview` 第 348 行)的完全相同风格追加三个函数,路径分别为 `/me/notifications/summary`(GET)、`/me/notifications/mark-read`(POST, body JSON)、`/teacher/submissions/${submissionId}/diff`(GET)。同时给 `saveSubmissionReview` 的 body 类型(若有显式类型)补 `resubmit_due_at?: number | null`。

- [ ] **Step 2: ReviewResultCard 组件**

创建 `src/lib/components/education/ReviewResultCard.svelte`:

```svelte
<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	export let review: {
		round_no: number;
		submitted_at: number;
		review_status: string;
		score?: number | null;
		overall_comment?: string | null;
		rubric?: Record<string, number> | null;
		returned_comment?: string | null;
		resubmit_due_at?: number | null;
		reviewed_at?: number | null;
	};
	export let onRevise: (() => void) | null = null;

	const formatTime = (ts: number | null | undefined) =>
		ts ? new Date(ts * 1000).toLocaleString() : '';
</script>

{#if review.review_status === 'returned'}
	<div
		class="rounded-xl border border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/40 p-4 mb-3"
	>
		<div class="font-semibold text-rose-700 dark:text-rose-300">
			{$i18n.t('Returned for revision')} · {$i18n.t('Round {{round}}', { round: review.round_no })}
		</div>
		{#if review.returned_comment}
			<p class="mt-2 text-sm whitespace-pre-wrap">{review.returned_comment}</p>
		{/if}
		{#if review.resubmit_due_at}
			<div class="mt-2 text-sm font-medium">
				{$i18n.t('Resubmit before')}: {formatTime(review.resubmit_due_at)}
			</div>
		{/if}
		{#if onRevise}
			<button
				class="mt-3 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-sm hover:bg-rose-700"
				on:click={onRevise}
			>
				{$i18n.t('Revise and resubmit')}
			</button>
		{/if}
	</div>
{:else if review.review_status === 'reviewed'}
	<div
		class="rounded-xl border border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40 p-4 mb-3"
	>
		<div class="flex items-center justify-between">
			<div class="font-semibold text-emerald-700 dark:text-emerald-300">
				{$i18n.t('Reviewed')} · {$i18n.t('Round {{round}}', { round: review.round_no })}
			</div>
			{#if review.score !== null && review.score !== undefined}
				<div class="text-2xl font-bold">{review.score}</div>
			{/if}
		</div>
		{#if review.rubric}
			<div class="mt-2 flex gap-4 text-sm">
				{#each Object.entries(review.rubric) as [key, value]}
					<span class="text-gray-600 dark:text-gray-300">{key}: {value}</span>
				{/each}
			</div>
		{/if}
		{#if review.overall_comment}
			<p class="mt-2 text-sm whitespace-pre-wrap">{review.overall_comment}</p>
		{/if}
		<div class="mt-2 text-xs text-gray-500">{formatTime(review.reviewed_at)}</div>
	</div>
{:else}
	<div
		class="rounded-xl border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 p-3 mb-3 text-sm text-gray-600 dark:text-gray-300"
	>
		{$i18n.t('Submitted, awaiting review')} · {$i18n.t('Round {{round}}', {
			round: review.round_no
		})} · {formatTime(review.submitted_at)}
	</div>
{/if}
```

- [ ] **Step 3: 接入 WritingWorkspaceShell**

读 `WritingWorkspaceShell.svelte` 与 `assignments/[assignmentId]/write/+page.svelte`,确认 workspace 响应如何变成 shell 的 props(`assignment` 等)。改动:

1. shell 新增 props:`export let review = null;`、`export let effectiveDueAt = null;`,页面从 workspace 响应透传 `review` / `effective_due_at`。
2. 截止逻辑(第 85-88 行)改为优先用有效截止:

```svelte
	$: activeDueAt = isAssignment ? (effectiveDueAt ?? assignment?.due_at ?? null) : null;
	$: isPastDue = activeDueAt ? activeDueAt <= Math.floor(Date.now() / 1000) : false;
	$: isReadOnly = isAssignment ? isPastDue : false;
	$: canSubmitAssignment = isAssignment && !isPastDue;
```

页面上原来显示 `assignment.due_at` 的位置(截止倒计时/日期,搜第 507 行 `isPastDue` 附近)统一改用 `activeDueAt`。
3. 写作面板(RichTextInput 上方)插入卡片:

```svelte
	{#if isAssignment && review}
		<ReviewResultCard {review} onRevise={null} />
	{/if}
```

(工作区本身就是编辑处,退回横幅无需跳转按钮,传 null。)
4. 提交成功后(`submitAssignment` 调用处第 406 行附近)重新拉取 workspace 或把本地 `review` 置为 `{ round_no: (review?.round_no ?? 0) + (review && review.review_status !== 'pending' ? 1 : review ? 0 : 1), submitted_at: Math.floor(Date.now() / 1000), review_status: 'pending' }` —— 优先选择重新拉取 workspace(简单可靠)。

- [ ] **Step 4: 主页徽章**

`me/writing/+page.svelte`:找到 assignment_items 渲染的卡片,按 item 新字段加徽章(样式沿用页面现有 badge/pill 类名;若无现成样式,用 `text-xs px-2 py-0.5 rounded-full` + 语义色):

- `item.review_status === 'returned'` → 玫红徽章 `{$i18n.t('Returned')}`,旁边显示 `{$i18n.t('Resubmit before')}: {formatTime(item.effective_due_at)}`
- `item.review_status === 'reviewed'` → 绿徽章 `{$i18n.t('Reviewed')} {item.score ?? ''}`
- `item.review_status === 'pending'` → 灰徽章 `{$i18n.t('Awaiting review')}`
- 无 review(未提交)→ 维持现状。

- [ ] **Step 5: i18n**

`zh-CN/translation.json` 增加(en-US 同 key,值=key):

```json
{
	"Returned for revision": "已退回重写",
	"Round {{round}}": "第 {{round}} 轮",
	"Resubmit before": "重交截止",
	"Revise and resubmit": "修改并重新提交",
	"Reviewed": "已批改",
	"Submitted, awaiting review": "已提交,等待批改",
	"Awaiting review": "待批改",
	"Returned": "已退回"
}
```

- [ ] **Step 6: 类型检查 + 手动验证**

Run: `npm run check`
Expected: 0 errors(允许既有 warnings)。
手动:起前后端(`bash dev.sh` + `npm run dev`),用测试账户(密码 666888)走一遍:老师布置→学生提交→老师打分→学生工作区看到绿色卡片;老师退回(设新截止)→学生看到玫红横幅且可编辑。

- [ ] **Step 7: Commit**

```bash
git add src/lib/apis/education/index.ts src/lib/components/education/ReviewResultCard.svelte src/lib/components/education/WritingWorkspaceShell.svelte "src/routes/(app)/assignments" "src/routes/(app)/me/writing" src/lib/i18n/locales/zh-CN/translation.json src/lib/i18n/locales/en-US/translation.json
git commit -m "feat: 学生端批改结果卡片、退回横幅与主页状态徽章"
```

---

### Task 7: 教师端 UI —— 轮次切换、前后稿 diff、退回设新截止

**Files:**
- Modify: `src/routes/(app)/teacher/submissions/[submissionId]/+page.svelte`
- Modify: `src/lib/i18n/locales/zh-CN/translation.json`、`en-US/translation.json`

**Interfaces:**
- Consumes: Task 4 的 `detail.rounds`、`GET .../diff`(Task 6 已封装 `getSubmissionRoundDiff`);Task 2 的 review 校验(returned 必带未来 `resubmit_due_at`,历史轮保存返回 400)。

- [ ] **Step 1: 轮次切换器**

读 `teacher/submissions/[submissionId]/+page.svelte`(约 800 行),在页面头部(学生名/统计条附近)渲染:

```svelte
	{#if detail?.rounds?.length > 1}
		<div class="flex gap-1.5 items-center">
			{#each detail.rounds as round}
				<a
					href={`/teacher/submissions/${round.submission_id}`}
					class="px-2.5 py-1 rounded-lg text-sm border
						{round.submission_id === detail.submission.id
						? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
						: 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'}"
				>
					{$i18n.t('Round {{round}}', { round: round.round_no })}
					{#if !round.is_current}<span class="opacity-60"> · {$i18n.t('History')}</span>{/if}
				</a>
			{/each}
		</div>
	{/if}
```

确认该页面路由参数变化时会重新加载 detail(SvelteKit 同路由跳转需响应 `$page.params` 变化;若页面在 `onMount` 拉数据,改为 `$: submissionId = $page.params.submissionId` 触发重新加载)。

- [ ] **Step 2: 历史轮只读**

`$: isHistoricalRound = detail ? !detail.submission.is_current : false;`
为 true 时:评分 Tab 的所有输入/按钮 `disabled`,顶部显示横幅 `{$i18n.t('Historical round, read-only')}`。

- [ ] **Step 3: 退回表单加"重交截止时间"**

评分 Tab 现有"退回重写"区域(搜 `returned_comment` / `returned`)加 `datetime-local` 输入(参考 `teacher/assignments/new/+page.svelte` 中 due_at 的转换写法):

```svelte
	<input type="datetime-local" bind:value={resubmitDueLocal} class="..." />
```

```ts
	let resubmitDueLocal = '';
	const toEpoch = (v: string) => (v ? Math.floor(new Date(v).getTime() / 1000) : null);
```

保存为 returned 时:若 `!toEpoch(resubmitDueLocal)` 或 ≤ 当前时间,前端直接 toast 报错不发请求;否则 body 带 `resubmit_due_at: toEpoch(resubmitDueLocal)`。加载 detail 时若已有 `detail.review?.resubmit_due_at`,反填输入框。

- [ ] **Step 4: 前后稿 diff 视图**

"分析" Tab 内(时间线区块之后)加折叠区:

```svelte
	{#if detail?.submission?.round_no > 1}
		<div class="mt-4">
			<button class="text-sm font-medium underline" on:click={loadDiff}>
				{$i18n.t('Compare with previous round')}
			</button>
			{#if diffData?.has_previous}
				<div class="mt-2 p-3 rounded-lg border border-gray-200 dark:border-gray-800 text-sm leading-7 whitespace-pre-wrap">
					{#each diffData.blocks as block}
						{#if block.op === 'equal'}<span>{block.new_text}</span>
						{:else if block.op === 'insert'}<span class="bg-emerald-100 dark:bg-emerald-900/50">{block.new_text}</span>
						{:else if block.op === 'delete'}<span class="bg-rose-100 dark:bg-rose-900/50 line-through">{block.old_text}</span>
						{:else}<span class="bg-rose-100 dark:bg-rose-900/50 line-through">{block.old_text}</span><span class="bg-emerald-100 dark:bg-emerald-900/50">{block.new_text}</span>{/if}
					{/each}
				</div>
			{/if}
		</div>
	{/if}
```

```ts
	let diffData: any = null;
	const loadDiff = async () => {
		diffData = await getSubmissionRoundDiff(localStorage.token, detail.submission.id);
	};
```

- [ ] **Step 5: i18n**

zh-CN 增加:`"History": "历史"`,`"Historical round, read-only": "历史轮次,只读"`,`"Compare with previous round": "与上一轮对比"`,`"A future resubmit due time is required": "退回时必须设置一个未来的重交截止时间"`(en-US 同 key=value)。`Round {{round}}` 已在 Task 6 加过。

- [ ] **Step 6: 类型检查 + 手动验证**

Run: `npm run check` → 0 errors。
手动:退回不填时间被前端拦截;填过去时间被拦截;退回成功后学生端解锁;学生重交后老师页出现两轮切换与 diff;历史轮表单禁用。

- [ ] **Step 7: Commit**

```bash
git add "src/routes/(app)/teacher/submissions" src/lib/i18n/locales/zh-CN/translation.json src/lib/i18n/locales/en-US/translation.json
git commit -m "feat: 教师端轮次切换、前后稿对比与退回设新截止"
```

---

### Task 8: 通知前端 —— socket 监听、toast、未读角标、已读

**Files:**
- Modify: `src/lib/stores/index.ts`(新 store)
- Modify: `src/routes/+layout.svelte`(socket 监听,现有 `$socket?.on('events', ...)` 在第 1108 行附近)
- Modify: `src/lib/components/layout/Sidebar.svelte`(角标)
- Modify: `src/routes/(app)/assignments/[assignmentId]/write/+page.svelte`、`src/routes/(app)/me/writing/+page.svelte`、`src/routes/(app)/teacher/review/+page.svelte`、`src/routes/(app)/teacher/assignments/[assignmentId]/submissions/+page.svelte`(已读触发 + 刷新 store)
- Modify: i18n 两个 translation.json

**Interfaces:**
- Consumes: Task 5 的 socket 事件 `education:notification`(data `{type, payload}`)与 `/me/notifications/*`;Task 6 的 `getEducationNotificationSummary` / `markEducationNotificationsRead`。
- Produces: `src/lib/stores/index.ts` 导出 `export const educationNotificationSummary: Writable<{ total: number; by_type: Record<string, number> } | null> = writable(null);`

- [ ] **Step 1: store 与初始加载**

`stores/index.ts` 按上面签名加 store。在 `src/routes/(app)/+layout.svelte` 的启动逻辑(bootstrap stores 处)加:

```ts
	import { educationNotificationSummary } from '$lib/stores';
	import { getEducationNotificationSummary } from '$lib/apis/education';
	// onMount/初始化块内:
	educationNotificationSummary.set(
		await getEducationNotificationSummary(localStorage.token).catch(() => null)
	);
```

- [ ] **Step 2: socket 监听 + toast**

`src/routes/+layout.svelte` 在注册 `events` 处(第 1108 行附近)同点注册;handler 定义在同文件(参考 `chatEventHandler` 的定义位置):

```ts
	const educationNotificationHandler = async (data) => {
		const payload = data?.payload ?? {};
		const title = payload.assignment_title ?? '';
		if (data.type === 'assignment_published') {
			toast.info($i18n.t('New assignment: {{title}}', { title }));
		} else if (data.type === 'submission_created') {
			toast.info(
				$i18n.t('{{name}} submitted {{title}}', { name: payload.student_name ?? '', title })
			);
		} else if (data.type === 'review_completed') {
			toast.success($i18n.t('Your submission for {{title}} has been reviewed', { title }));
		} else if (data.type === 'submission_returned') {
			toast.warning($i18n.t('Your submission for {{title}} was returned', { title }));
		}
		educationNotificationSummary.set(
			await getEducationNotificationSummary(localStorage.token).catch(() => null)
		);
	};
	// 注册处:
	$socket?.on('education:notification', educationNotificationHandler);
```

toast 用该文件已 import 的 svelte-sonner;若 `$i18n` 在该文件不可用,按文件内既有 toast 文案的 i18n 获取方式处理。

- [ ] **Step 3: 侧边栏角标**

`Sidebar.svelte`:找到指向 `/me/writing` 的入口(搜 `me/writing`)与 teacher 入口(搜 `/teacher`)。学生角标数 = `by_type` 中 `assignment_published + review_completed + submission_returned` 之和;老师角标数 = `submission_created`。渲染:

```svelte
	{#if studentUnread > 0}
		<span class="ml-auto min-w-[1.25rem] h-5 px-1 rounded-full bg-rose-500 text-white text-[11px] flex items-center justify-center">
			{studentUnread > 99 ? '99+' : studentUnread}
		</span>
	{/if}
```

```ts
	$: byType = $educationNotificationSummary?.by_type ?? {};
	$: studentUnread =
		(byType['assignment_published'] ?? 0) +
		(byType['review_completed'] ?? 0) +
		(byType['submission_returned'] ?? 0);
	$: teacherUnread = byType['submission_created'] ?? 0;
```

- [ ] **Step 4: 已读触发**

统一小工具(可放 `src/lib/apis/education/index.ts` 导出,或各页面内联):调 `markEducationNotificationsRead` 后刷新 store。触发点:

- `assignments/[assignmentId]/write/+page.svelte` 加载成功后:`{ assignment_id, types: ['assignment_published', 'review_completed', 'submission_returned'] }`
- `teacher/assignments/[assignmentId]/submissions/+page.svelte` 加载后:`{ assignment_id, types: ['submission_created'] }`
- `teacher/review/+page.svelte` 加载后:`{ types: ['submission_created'] }`

- [ ] **Step 5: i18n**

zh-CN:`"New assignment: {{title}}": "新作业:{{title}}"`,`"{{name}} submitted {{title}}": "{{name}} 提交了《{{title}}》"`,`"Your submission for {{title}} has been reviewed": "你的《{{title}}》已批改"`,`"Your submission for {{title}} was returned": "你的《{{title}}》被退回重写"`(en-US key=value)。

- [ ] **Step 6: 类型检查 + 全量回归**

Run: `npm run check` → 0 errors。
Run: `cd backend && python -m pytest open_webui/test/apps/webui/routers/test_education_smoke.py -q` → 全部 PASS。
手动(两个浏览器分别登老师/学生,密码 666888):老师布置作业→学生即时收到 toast+角标;学生提交→老师收到;老师批改/退回→学生收到;进对应页面后角标清零;刷新页面未读仍准确(落库生效)。

- [ ] **Step 7: Commit**

```bash
git add src/lib/stores/index.ts src/routes/+layout.svelte "src/routes/(app)" src/lib/components/layout/Sidebar.svelte src/lib/apis/education/index.ts src/lib/i18n/locales/zh-CN/translation.json src/lib/i18n/locales/en-US/translation.json
git commit -m "feat: 教育通知实时推送、toast 与未读角标"
```

---

## 验收清单(对照 spec)

- [ ] 学生工作区能看到 reviewed 卡片(分数/rubric/总评)与 returned 横幅(评语+新截止),pending 只显示"待批改" —— spec §A
- [ ] 主页作业卡片四态徽章 —— spec §A
- [ ] pending 重交=覆盖;reviewed/returned 后重交=新轮,旧轮稿件/反思/评语/分析全保留 —— spec §B
- [ ] 退回必带未来 resubmit_due_at;有效截止 = 最新退回时间;退回解锁、超期锁定 —— spec §B
- [ ] 教师端轮次切换、历史轮只读、前后稿 diff;统计按当前轮 —— spec §B
- [ ] 四类通知:落库+socket 实时+未读角标+进页已读;离线不丢 —— spec §C
- [ ] schema 变更全部走 Alembic,存量数据回填 round_no=1/is_current=1 —— spec §迁移
