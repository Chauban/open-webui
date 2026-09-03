"""education: move teaching identity onto permission groups

Teaching identity used to live in ``user.info['education_role']``, a JSON blob
parallel to the group system that already drives permissions.  This creates the
two system groups and moves every account into the one matching its recorded
identity, then drops the JSON key so that group membership is the only source.

Revision ID: d6f2a8c4e910
Revises: c5a9e3f1b7d4
Create Date: 2026-09-03 00:00:00.000000

"""

import json
import time
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6f2a8c4e910"
down_revision: Union[str, Sequence[str], None] = "c5a9e3f1b7d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEACHER_GROUP_ID = "education-teacher"
STUDENT_GROUP_ID = "education-student"

GROUP_SEED = (
    (TEACHER_GROUP_ID, "教师", "授课教师，可创建班级、布置作业、审阅提交。"),
    (STUDENT_GROUP_ID, "学生", "学生，可加入班级、完成并提交写作作业。"),
)

GROUP_ID_BY_ROLE = {"teacher": TEACHER_GROUP_ID, "student": STUDENT_GROUP_ID}


def upgrade() -> None:
    conn = op.get_bind()
    now = int(time.time())

    owner_id = (
        conn.execute(sa.text("SELECT id FROM \"user\" WHERE role = 'admin' ORDER BY created_at LIMIT 1")).scalar()
        or ""
    )

    existing_group_ids = {
        row[0]
        for row in conn.execute(
            sa.text('SELECT id FROM "group" WHERE id IN (:teacher, :student)'),
            {"teacher": TEACHER_GROUP_ID, "student": STUDENT_GROUP_ID},
        )
    }

    # 'members' keeps these groups pickable in access-control UIs the same way
    # a hand-made group is, without exposing them to non-members for sharing.
    group_data = json.dumps({"config": {"share": "members"}})

    for group_id, name, description in GROUP_SEED:
        if group_id in existing_group_ids:
            continue
        conn.execute(
            sa.text(
                'INSERT INTO "group" (id, user_id, name, description, data, meta, permissions, created_at, updated_at)'
                " VALUES (:id, :user_id, :name, :description, :data, :meta, NULL, :now, :now)"
            ),
            {
                "id": group_id,
                "user_id": owner_id,
                "name": name,
                "description": description,
                "data": group_data,
                "meta": json.dumps({"system": "education_identity"}),
                "now": now,
            },
        )

    already_member = {
        (row[0], row[1])
        for row in conn.execute(
            sa.text("SELECT group_id, user_id FROM group_member WHERE group_id IN (:teacher, :student)"),
            {"teacher": TEACHER_GROUP_ID, "student": STUDENT_GROUP_ID},
        )
    }

    rows = list(conn.execute(sa.text('SELECT id, role, info FROM "user"')))
    for user_id, role, info in rows:
        parsed = info
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (TypeError, ValueError):
                parsed = None
        if not isinstance(parsed, dict):
            continue

        education_role = parsed.pop("education_role", None)

        # Platform admins carry no teaching group; the identity is derived from
        # user.role instead, so an admin is never seeded into either group.
        group_id = GROUP_ID_BY_ROLE.get(education_role) if role != "admin" else None
        if group_id and (group_id, user_id) not in already_member:
            conn.execute(
                sa.text(
                    "INSERT INTO group_member (id, group_id, user_id, created_at, updated_at)"
                    " VALUES (:id, :group_id, :user_id, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "group_id": group_id,
                    "user_id": user_id,
                    "now": now,
                },
            )

        if education_role is not None:
            conn.execute(
                sa.text('UPDATE "user" SET info = :info WHERE id = :id'),
                {"info": json.dumps(parsed), "id": user_id},
            )


def downgrade() -> None:
    conn = op.get_bind()

    for group_id, role in ((TEACHER_GROUP_ID, "teacher"), (STUDENT_GROUP_ID, "student")):
        member_ids = [
            row[0]
            for row in conn.execute(
                sa.text("SELECT user_id FROM group_member WHERE group_id = :group_id"),
                {"group_id": group_id},
            )
        ]
        for user_id in member_ids:
            info = conn.execute(sa.text('SELECT info FROM "user" WHERE id = :id'), {"id": user_id}).scalar()
            parsed = info
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except (TypeError, ValueError):
                    parsed = None
            if not isinstance(parsed, dict):
                parsed = {}
            parsed["education_role"] = role
            conn.execute(
                sa.text('UPDATE "user" SET info = :info WHERE id = :id'),
                {"info": json.dumps(parsed), "id": user_id},
            )

        conn.execute(
            sa.text("DELETE FROM group_member WHERE group_id = :group_id"),
            {"group_id": group_id},
        )
        conn.execute(sa.text('DELETE FROM "group" WHERE id = :group_id'), {"group_id": group_id})
