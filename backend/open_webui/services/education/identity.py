"""Teaching identity, expressed as membership of two system permission groups.

``user.role`` stays what upstream means by it — platform authority plus the
``pending`` approval gate.  The teaching identity (teacher / student) rides on
group membership instead, so that one mechanism drives both "who is this person
in the course" and "what may they reach" (models, tools, features).  Groups are
already what ``has_permission`` reads, so nothing needs to be kept in sync.

Platform admins are always reported as ``admin`` regardless of group
membership; an admin may additionally sit in the teacher group when they also
teach, and the teaching endpoints accept either.
"""

from __future__ import annotations

from typing import Optional

from open_webui.models.groups import Groups
from sqlalchemy.ext.asyncio import AsyncSession

TEACHER_GROUP_ID = 'education-teacher'
STUDENT_GROUP_ID = 'education-student'

EDUCATION_GROUP_IDS = (TEACHER_GROUP_ID, STUDENT_GROUP_ID)

ROLE_BY_GROUP_ID = {
    TEACHER_GROUP_ID: 'teacher',
    STUDENT_GROUP_ID: 'student',
}
GROUP_ID_BY_ROLE = {role: group_id for group_id, role in ROLE_BY_GROUP_ID.items()}


def role_from_group_ids(group_ids) -> Optional[str]:
    # Teacher wins when an account somehow sits in both groups.
    if TEACHER_GROUP_ID in group_ids:
        return 'teacher'
    if STUDENT_GROUP_ID in group_ids:
        return 'student'
    return None


async def get_education_role(user, db: Optional[AsyncSession] = None) -> Optional[str]:
    """Return ``admin``, ``teacher``, ``student`` or ``None`` for one user."""
    if getattr(user, 'role', None) == 'admin':
        return 'admin'

    groups = await Groups.get_groups_by_member_id(user.id, db=db)
    return role_from_group_ids({group.id for group in groups})


async def set_education_role(
    user_id: str, role: Optional[str], db: Optional[AsyncSession] = None
) -> None:
    """Move a user into the group for ``role``, leaving the other one.

    ``role`` of ``None`` (or ``admin``) removes the account from both groups.
    """
    target_group_id = GROUP_ID_BY_ROLE.get(role or '')

    for group_id in EDUCATION_GROUP_IDS:
        if group_id == target_group_id:
            await Groups.add_users_to_group(group_id, [user_id], db=db)
        else:
            await Groups.remove_users_from_group(group_id, [user_id], db=db)
