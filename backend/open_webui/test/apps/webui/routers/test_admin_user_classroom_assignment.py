import asyncio
import sys
import uuid
from contextlib import contextmanager
from itertools import count
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.models.auths import Auth
from open_webui.models.education import Classroom, ClassroomMember, Education
from open_webui.models.groups import Group, GroupMember
from open_webui.models.users import User, UserModel
from open_webui.services.education.identity import GROUP_ID_BY_ROLE
from open_webui.routers.groups import router as groups_router
from open_webui.routers.users import router as users_router
from open_webui.utils.auth import get_admin_user


class AdminContext:
    current_user = None


# created_at 严格递增,保证 get_first_user()(主管理员检测,按 created_at 排序)
# 稳定命中第一个种子用户
_seed_clock = count(1)


def _seed_user(session, name: str, email: str, role: str, education_role: str | None = None):
    # Users/Auths 表 API 自 v0.10.2 合并起为 async(绑定全局 async engine 的
    # AsyncSession),这里直接用 ORM 在本测试的 sync session 上种数据
    now = next(_seed_clock)
    user_row = User(
        id=uuid.uuid4().hex,
        email=email,
        name=name,
        role=role,
        profile_image_url="/user.png",
        info={},
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(user_row)

    # 教学身份来自权限组,种子数据同样按组写入
    group_id = GROUP_ID_BY_ROLE.get(education_role or "")
    if group_id:
        if session.get(Group, group_id) is None:
            session.add(
                Group(
                    id=group_id,
                    user_id="",
                    name=group_id,
                    description="",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            GroupMember(
                id=uuid.uuid4().hex,
                group_id=group_id,
                user_id=user_row.id,
                created_at=now,
                updated_at=now,
            )
        )

    session.commit()
    session.refresh(user_row)
    return UserModel.model_validate(user_row)


@contextmanager
def _harness(tmp_name: str):
    """A FastAPI client and a session factory, both bound to one throwaway sqlite file."""
    internal_db.DATABASE_ENABLE_SESSION_SHARING = True

    tmp_root = BACKEND_ROOT / ".tmp" / tmp_name
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / f"{uuid.uuid4().hex}.db"
    original_async_session_local = internal_db.AsyncSessionLocal
    original_session_local = internal_db.SessionLocal
    async_engine = None
    try:
        sync_url = f"sqlite:///{db_path}"
        engine = create_engine(
            sync_url,
            connect_args={"check_same_thread": False},
        )
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False,
        )

        for table in [
            User.__table__,
            Auth.__table__,
            Classroom.__table__,
            ClassroomMember.__table__,
            Group.__table__,
            GroupMember.__table__,
        ]:
            table.create(bind=engine, checkfirst=True)

        with engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX IF EXISTS classroom_member_user_idx")

        # users router 端点的 db 来自 get_async_session(全局 AsyncSessionLocal),
        # 端点内的 sync Education 调用则回落到全局 SessionLocal —— 两者都指向
        # 本测试的 sqlite 文件,保证完全隔离(参照 test_education_smoke 的做法)
        async_engine = create_async_engine(
            internal_db._make_async_url(sync_url),
            connect_args={"check_same_thread": False},
        )
        internal_db.AsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        internal_db.SessionLocal = SessionLocal

        app = FastAPI()
        app.include_router(users_router, prefix="/api/v1/users")
        app.include_router(groups_router, prefix="/api/v1/groups")
        app.state.config = SimpleNamespace(
            ENABLE_USER_STATUS=True,
            USER_PERMISSIONS={},
        )

        def override_admin_user():
            if AdminContext.current_user is None:
                raise HTTPException(status_code=401, detail="Missing admin user")
            return AdminContext.current_user

        app.dependency_overrides[get_admin_user] = override_admin_user

        client = TestClient(app)
        try:
            yield SessionLocal, client
        finally:
            client.close()
            engine.dispose()
            AdminContext.current_user = None
    finally:
        internal_db.AsyncSessionLocal = original_async_session_local
        internal_db.SessionLocal = original_session_local
        if async_engine is not None:
            asyncio.run(async_engine.dispose())
        if db_path.exists():
            try:
                db_path.unlink()
            except PermissionError:
                pass


def _seed_classroom(session, name: str, teacher_id: str, invite_code: str):
    now = next(_seed_clock)
    classroom = Classroom(
        id=uuid.uuid4().hex,
        name=name,
        teacher_id=teacher_id,
        invite_code=invite_code,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(classroom)
    session.commit()
    session.refresh(classroom)
    return classroom


def _seed_membership(session, classroom_id: str, user_id: str, member_role: str):
    now = next(_seed_clock)
    session.add(
        ClassroomMember(
            id=uuid.uuid4().hex,
            classroom_id=classroom_id,
            user_id=user_id,
            member_role=member_role,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _group_ids_of(session, user_id: str) -> set:
    return {
        row[0]
        for row in session.query(GroupMember.group_id)
        .filter(GroupMember.user_id == user_id)
        .all()
    }


def test_admin_can_assign_student_to_classroom():
    with _harness("pytest-admin-user-classroom") as (SessionLocal, client):
        with SessionLocal() as session:
            admin = _seed_user(session, "Admin", "admin@example.com", "admin")
            teacher_one = _seed_user(
                session, "Teacher One", "teacher1@example.com", "user", "teacher"
            )
            teacher_two = _seed_user(
                session, "Teacher Two", "teacher2@example.com", "user", "teacher"
            )
            student = _seed_user(
                session, "Student One", "student1@example.com", "user", "student"
            )
            student_id = student.id

            first_classroom = _seed_classroom(session, "Class A", teacher_one.id, "CLASSA01")
            second_classroom = _seed_classroom(session, "Class B", teacher_two.id, "CLASSB01")
            _seed_membership(session, first_classroom.id, student_id, "student")

        AdminContext.current_user = admin

        assignment_res = client.get(f"/api/v1/users/{student_id}/education/classroom")
        assert assignment_res.status_code == 200, assignment_res.text
        assignment_payload = assignment_res.json()
        assert assignment_payload["classroom_id"] == first_classroom.id
        assert len(assignment_payload["classrooms"]) == 2
        assert {item["teacher_name"] for item in assignment_payload["classrooms"]} == {
            "Teacher One",
            "Teacher Two",
        }

        switch_res = client.post(
            f"/api/v1/users/{student_id}/update",
            json={
                "role": "user",
                "name": "Student One",
                "email": "student1@example.com",
                "profile_image_url": "/user.png",
                "education_role": "student",
                "classroom_id": second_classroom.id,
            },
        )
        assert switch_res.status_code == 200, switch_res.text

        with SessionLocal() as session:
            membership = Education.get_classroom_member_by_user_id(student_id, db=session)
            assert membership is not None
            assert membership.classroom_id == second_classroom.id

        clear_res = client.post(
            f"/api/v1/users/{student_id}/update",
            json={
                "role": "user",
                "name": "Student One",
                "email": "student1@example.com",
                "profile_image_url": "/user.png",
                "education_role": "student",
                "classroom_id": None,
            },
        )
        assert clear_res.status_code == 200, clear_res.text

        with SessionLocal() as session:
            assert Education.get_classroom_member_by_user_id(student_id, db=session) is None

        promote_res = client.post(
            f"/api/v1/users/{student_id}/update",
            json={
                "role": "user",
                "name": "Student One",
                "email": "student1@example.com",
                "profile_image_url": "/user.png",
                "education_role": "teacher",
                "classroom_id": first_classroom.id,
            },
        )
        assert promote_res.status_code == 200, promote_res.text

        with SessionLocal() as session:
            assert Education.get_classroom_member_by_user_id(student_id, db=session) is None
            # 升为教师 = 换权限组:进教师组、离开学生组
            assert _group_ids_of(session, student_id) == {GROUP_ID_BY_ROLE["teacher"]}


def test_leaving_the_student_identity_clears_every_classroom():
    """一个学生可能同时在多个班里,身份一变,所有班籍都必须跟着掉。"""
    with _harness("pytest-admin-user-classroom") as (SessionLocal, client):
        with SessionLocal() as session:
            admin = _seed_user(session, "Admin", "admin@example.com", "admin")
            teacher = _seed_user(session, "Teacher", "teacher@example.com", "user", "teacher")
            student = _seed_user(session, "Student", "student@example.com", "user", "student")
            student_id = student.id

            first_classroom = _seed_classroom(session, "Class A", teacher.id, "CLASSA02")
            second_classroom = _seed_classroom(session, "Class B", teacher.id, "CLASSB02")
            _seed_membership(session, first_classroom.id, student_id, "student")
            _seed_membership(session, second_classroom.id, student_id, "student")

        AdminContext.current_user = admin

        promote_res = client.post(
            f"/api/v1/users/{student_id}/update",
            json={
                "role": "user",
                "name": "Student",
                "email": "student@example.com",
                "profile_image_url": "/user.png",
                "education_role": "teacher",
            },
        )
        assert promote_res.status_code == 200, promote_res.text

        with SessionLocal() as session:
            assert Education.get_classroom_members_by_user_id(student_id, db=session) == []
            assert _group_ids_of(session, student_id) == {GROUP_ID_BY_ROLE["teacher"]}


def test_teacher_owning_classrooms_cannot_lose_the_teaching_identity():
    """班级跟着 teacher_id 走,教师被降级会留下没人管的班,所以直接拦住。"""
    with _harness("pytest-admin-user-classroom") as (SessionLocal, client):
        with SessionLocal() as session:
            admin = _seed_user(session, "Admin", "admin@example.com", "admin")
            teacher = _seed_user(session, "Teacher", "teacher@example.com", "user", "teacher")
            teacher_id = teacher.id
            classroom = _seed_classroom(session, "Class A", teacher_id, "CLASSA03")
            _seed_membership(session, classroom.id, teacher_id, "teacher")

        AdminContext.current_user = admin

        demote_res = client.post(
            f"/api/v1/users/{teacher_id}/update",
            json={
                "role": "user",
                "name": "Teacher",
                "email": "teacher@example.com",
                "profile_image_url": "/user.png",
                "education_role": "student",
            },
        )
        assert demote_res.status_code == 400, demote_res.text
        assert "classroom" in demote_res.json()["detail"]

        with SessionLocal() as session:
            assert _group_ids_of(session, teacher_id) == {GROUP_ID_BY_ROLE["teacher"]}
            assert Education.get_classroom_members_by_user_id(teacher_id, db=session) != []


def test_identity_groups_reject_direct_membership_edits():
    """身份只能在用户编辑里改,从用户组页面直接增删成员会绕开班籍清理。"""
    with _harness("pytest-admin-user-classroom") as (SessionLocal, client):
        with SessionLocal() as session:
            admin = _seed_user(session, "Admin", "admin@example.com", "admin")
            student = _seed_user(session, "Student", "student@example.com", "user", "student")
            student_id = student.id

        AdminContext.current_user = admin

        student_group_id = GROUP_ID_BY_ROLE["student"]
        for action in ("add", "remove"):
            res = client.post(
                f"/api/v1/groups/id/{student_group_id}/users/{action}",
                json={"user_ids": [student_id]},
            )
            assert res.status_code == 400, res.text
            assert "teaching identity" in res.json()["detail"]

        with SessionLocal() as session:
            assert _group_ids_of(session, student_id) == {student_group_id}
