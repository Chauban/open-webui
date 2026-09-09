"""学生注册必须持有效班级邀请码,持码即激活;教师注册仍走管理员审批。"""

import asyncio
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.internal.db import get_async_session
from open_webui.models.auths import Auth
from open_webui.models.config import Config
from open_webui.models.education import Classroom, ClassroomMember
from open_webui.models.groups import Group, GroupMember
from open_webui.models.users import User
from open_webui.routers.auths import router as auths_router
from open_webui.services.education.identity import GROUP_ID_BY_ROLE

TEACHER_ID = "teacher-1"
CLASSROOM_ID = "classroom-1"
INVITE_CODE = "ABCD1234"


@contextmanager
def _signup_app(tmp_path):
    sync_url = f"sqlite:///{tmp_path / 'signup.db'}"
    engine = create_engine(sync_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
    )

    for table in [
        Config.__table__,
        User.__table__,
        Auth.__table__,
        Group.__table__,
        GroupMember.__table__,
        Classroom.__table__,
        ClassroomMember.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    async_engine = create_async_engine(
        internal_db._make_async_url(sync_url),
        connect_args={"check_same_thread": False},
    )
    TestAsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # 注册接口拿到的是 AsyncSession,把它传给 Education 的同步仓储方法时
    # get_db_context() 的 isinstance(db, Session) 判定不成立,会退回**进程级**
    # 的同步 SessionLocal。两个工厂都要指向同一个 sqlite 文件,班级查询才看得见
    # 本测试种下的数据。
    original_async_session_local = internal_db.AsyncSessionLocal
    original_session_local = internal_db.SessionLocal
    internal_db.AsyncSessionLocal = TestAsyncSessionLocal
    internal_db.SessionLocal = SessionLocal

    now = int(time.time())
    with SessionLocal() as session:
        # 教学身份组由启动播种建立;组行不存在时 add_users_to_group 会静默返回
        for group_id in GROUP_ID_BY_ROLE.values():
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
            User(
                id=TEACHER_ID,
                email="teacher@example.com",
                name="Teacher One",
                role="user",
                profile_image_url="/user.png",
                info={},
                last_active_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Classroom(
                id=CLASSROOM_ID,
                name="Writing 101",
                teacher_id=TEACHER_ID,
                invite_code=INVITE_CODE,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    app = FastAPI()
    app.include_router(auths_router, prefix="/api/v1/auths")

    async def override_async_session():
        async with TestAsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_async_session

    client = TestClient(app)
    try:
        yield client, SessionLocal
    finally:
        client.close()
        engine.dispose()
        asyncio.run(async_engine.dispose())
        internal_db.AsyncSessionLocal = original_async_session_local
        internal_db.SessionLocal = original_session_local


@pytest.fixture
def signup_client(tmp_path):
    with _signup_app(tmp_path) as ctx:
        yield ctx


def _signup(client, *, education_role, invite_code=None, email=None):
    payload = {
        "name": "New Person",
        "email": email or f"{uuid.uuid4().hex}@example.com",
        "password": "Passw0rd!2345",
        "profile_image_url": "/user.png",
        "education_role": education_role,
    }
    if invite_code is not None:
        payload["classroom_invite_code"] = invite_code
    return client.post("/api/v1/auths/signup", json=payload)


def _user_by_email(SessionLocal, email):
    with SessionLocal() as session:
        return session.query(User).filter(User.email == email).first()


def test_student_signup_without_invite_code_is_rejected(signup_client):
    """没有邀请码的学生注册直接被拒,且不留下任何用户记录。"""
    client, SessionLocal = signup_client

    email = "no-code@example.com"
    res = _signup(client, education_role="student", email=email)

    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "Classroom invite code is required"
    assert _user_by_email(SessionLocal, email) is None


def test_student_signup_with_blank_invite_code_is_rejected(signup_client):
    """空白字符串不算填了邀请码。"""
    client, SessionLocal = signup_client

    email = "blank-code@example.com"
    res = _signup(client, education_role="student", invite_code="   ", email=email)

    assert res.status_code == 400, res.text
    assert _user_by_email(SessionLocal, email) is None


def test_student_signup_with_unknown_invite_code_is_rejected(signup_client):
    """码不存在时报 404,同样不建号。"""
    client, SessionLocal = signup_client

    email = "wrong-code@example.com"
    res = _signup(client, education_role="student", invite_code="ZZZZ0000", email=email)

    assert res.status_code == 404, res.text
    assert res.json()["detail"] == "Invalid classroom invite code"
    assert _user_by_email(SessionLocal, email) is None


def test_student_signup_with_valid_code_is_active_and_enrolled(signup_client):
    """持有效码注册:直接 active,不进待激活队列,并且当场入班。"""
    client, SessionLocal = signup_client

    email = "student@example.com"
    res = _signup(
        client, education_role="student", invite_code=INVITE_CODE, email=email
    )

    assert res.status_code == 200, res.text
    assert res.json()["role"] == "user"

    user = _user_by_email(SessionLocal, email)
    assert user is not None
    assert user.role == "user"

    with SessionLocal() as session:
        membership = (
            session.query(ClassroomMember)
            .filter(ClassroomMember.user_id == user.id)
            .one()
        )
        assert membership.classroom_id == CLASSROOM_ID
        assert membership.member_role == "student"

        group_ids = {
            row[0]
            for row in session.query(GroupMember.group_id)
            .filter(GroupMember.user_id == user.id)
            .all()
        }
        assert group_ids == {GROUP_ID_BY_ROLE["student"]}


def test_invite_code_is_case_insensitive(signup_client):
    """邀请码不区分大小写,学生照抄小写也能进班。"""
    client, SessionLocal = signup_client

    email = "lowercase@example.com"
    res = _signup(
        client,
        education_role="student",
        invite_code=INVITE_CODE.lower(),
        email=email,
    )

    assert res.status_code == 200, res.text
    assert res.json()["role"] == "user"


def test_archived_classroom_invite_code_is_rejected(signup_client):
    """归档班级的旧码立即失效,不能再被拿来注册。"""
    client, SessionLocal = signup_client

    with SessionLocal() as session:
        classroom = session.get(Classroom, CLASSROOM_ID)
        classroom.status = "archived"
        session.commit()

    email = "archived@example.com"
    res = _signup(
        client, education_role="student", invite_code=INVITE_CODE, email=email
    )

    assert res.status_code == 404, res.text
    assert _user_by_email(SessionLocal, email) is None


def test_teacher_signup_still_waits_for_admin_approval(signup_client):
    """教师不受邀请码约束,但仍然停在 pending 等管理员审批。"""
    client, SessionLocal = signup_client

    email = "new-teacher@example.com"
    res = _signup(client, education_role="teacher", email=email)

    assert res.status_code == 200, res.text
    assert res.json()["role"] == "pending"

    user = _user_by_email(SessionLocal, email)
    assert user.role == "pending"

    with SessionLocal() as session:
        assert (
            session.query(ClassroomMember)
            .filter(ClassroomMember.user_id == user.id)
            .count()
            == 0
        )
