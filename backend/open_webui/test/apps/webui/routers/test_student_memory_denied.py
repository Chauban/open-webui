"""学生的任何对话都不读不写记忆:学生组硬性收回 features.memories,教师不受影响。"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.internal.db as internal_db
from open_webui.models.groups import GroupMember
from open_webui.models.users import User
from open_webui.services.education.identity import STUDENT_GROUP_ID, TEACHER_GROUP_ID
from open_webui.test.util.database import engine_kwargs, migrated_database
from open_webui.utils import access_control
from open_webui.utils.access_control import get_permissions, has_permission
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

# 默认权限里记忆是开着的:组权限按最宽松合并,单靠组设置关不掉,收回必须在代码里。
DEFAULT_PERMISSIONS = {"features": {"memories": True}}


def test_student_group_id_matches_identity():
    assert access_control.STUDENT_GROUP_ID == STUDENT_GROUP_ID


def test_students_lose_memories_teachers_keep_them():
    with migrated_database() as sync_url:
        engine = create_engine(sync_url, **engine_kwargs(sync_url))
        now = int(time.time())
        with sessionmaker(bind=engine)() as session:
            for user_id, group_id in (("student-1", STUDENT_GROUP_ID), ("teacher-1", TEACHER_GROUP_ID)):
                session.add(
                    User(
                        id=user_id,
                        email=f"{user_id}@example.com",
                        name=user_id,
                        role="user",
                        profile_image_url="/user.png",
                        info={},
                        last_active_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.flush()
                session.add(
                    GroupMember(
                        id=str(uuid.uuid4()),
                        group_id=group_id,
                        user_id=user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()
        engine.dispose()

        async def check():
            async_engine = create_async_engine(
                internal_db._make_async_url(sync_url), **engine_kwargs(sync_url)
            )
            try:
                async with async_sessionmaker(bind=async_engine, class_=AsyncSession)() as db:
                    student = await get_permissions("student-1", DEFAULT_PERMISSIONS, db=db)
                    teacher = await get_permissions("teacher-1", DEFAULT_PERMISSIONS, db=db)
                    return (
                        student["features"]["memories"],
                        teacher["features"]["memories"],
                        await has_permission("student-1", "features.memories", DEFAULT_PERMISSIONS, db=db),
                        await has_permission("teacher-1", "features.memories", DEFAULT_PERMISSIONS, db=db),
                    )
            finally:
                await async_engine.dispose()

        assert asyncio.run(check()) == (False, True, False, True)
