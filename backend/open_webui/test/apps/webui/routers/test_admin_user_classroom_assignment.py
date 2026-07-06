from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.internal.db import get_session
from open_webui.models.auths import Auth, Auths
from open_webui.models.education import Classroom, ClassroomMember, Education
from open_webui.models.users import User, Users
from open_webui.routers.users import router as users_router
from open_webui.utils.auth import get_admin_user


class AdminContext:
    current_user = None


def _seed_user(session, name: str, email: str, role: str, education_role: str | None = None):
    user = Auths.insert_new_auth(
        email=email,
        password="hashed-password",
        name=name,
        role=role,
        db=session,
    )
    if education_role:
        Users.update_user_by_id(
            user.id,
            {
                "info": {
                    **(user.info or {}),
                    "education_role": education_role,
                }
            },
            db=session,
        )
        user = Users.get_user_by_id(user.id, db=session)
    return user


def test_admin_can_assign_student_to_classroom():
    internal_db.DATABASE_ENABLE_SESSION_SHARING = True

    tmp_root = BACKEND_ROOT / ".tmp" / "pytest-admin-user-classroom"
    tmp_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_root / f"{uuid.uuid4().hex}.db"
    try:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False,
        )

        for table in [User.__table__, Auth.__table__, Classroom.__table__, ClassroomMember.__table__]:
            table.create(bind=engine, checkfirst=True)

        with engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX IF EXISTS classroom_member_user_idx")

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
            admin_id = admin.id
            student_id = student.id
            teacher_one_id = teacher_one.id
            teacher_two_id = teacher_two.id

        with SessionLocal() as session:
            now = 1
            first_classroom = Classroom(
                id=uuid.uuid4().hex,
                name="Class A",
                teacher_id=teacher_one_id,
                invite_code="CLASSA01",
                status="active",
                created_at=now,
                updated_at=now,
            )
            second_classroom = Classroom(
                id=uuid.uuid4().hex,
                name="Class B",
                teacher_id=teacher_two_id,
                invite_code="CLASSB01",
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(first_classroom)
            session.add(second_classroom)
            session.add(
                ClassroomMember(
                    id=uuid.uuid4().hex,
                    classroom_id=first_classroom.id,
                    user_id=student_id,
                    member_role="student",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

        app = FastAPI()
        app.include_router(users_router, prefix="/api/v1/users")
        app.state.config = SimpleNamespace(
            ENABLE_USER_STATUS=True,
            USER_PERMISSIONS={},
        )

        def override_session():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_admin_user():
            if AdminContext.current_user is None:
                raise HTTPException(status_code=401, detail="Missing admin user")
            return AdminContext.current_user

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_admin_user] = override_admin_user

        client = TestClient(app)
        with SessionLocal() as session:
            AdminContext.current_user = Users.get_user_by_id(admin_id, db=session)

        try:
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
                membership = Education.get_classroom_member_by_user_id(student_id, db=session)
                assert membership is None

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
                membership = Education.get_classroom_member_by_user_id(student_id, db=session)
                updated_user = Users.get_user_by_id(student_id, db=session)
                assert membership is None
                assert updated_user.info["education_role"] == "teacher"
        finally:
            client.close()
            engine.dispose()
            AdminContext.current_user = None
    finally:
        if db_path.exists():
            try:
                db_path.unlink()
            except PermissionError:
                pass
