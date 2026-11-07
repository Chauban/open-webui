"""One durable conversation per revision workspace; no implicit history cleanup."""

from fastapi import HTTPException
from sqlalchemy import select, update
from open_webui.models.education import Assignment, WritingSession
from open_webui.services.education.task_types import TASK_MODES, is_revision

REVISION_MODES = tuple(mode for mode in TASK_MODES if is_revision(mode))

SINGLE_CONVERSATION_MESSAGE = 'This revision assignment uses one conversation. Reopen the assignment to continue.'


def revision_sessions_query(folder_id):
    return (
        select(WritingSession.id)
        .join(Assignment, Assignment.id == WritingSession.assignment_id)
        .where(
            WritingSession.folder_id == folder_id,
            Assignment.task_mode.in_(REVISION_MODES),
        )
    )


async def is_revision_folder(db, folder_id):
    return bool(folder_id and (await db.execute(revision_sessions_query(folder_id))).first())


async def lock_folder_assignments(db, folder_ids):
    ids = (
        (
            await db.execute(
                select(WritingSession.assignment_id).where(
                    WritingSession.folder_id.in_([fid for fid in folder_ids if fid]),
                    WritingSession.assignment_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for assignment_id in sorted(set(ids)):
        await db.execute(
            update(Assignment).where(Assignment.id == assignment_id).values(updated_at=Assignment.updated_at)
        )


def reject_conversion_with_multiple_chats(db, assignment_id):
    from open_webui.models.chats import Chat
    from sqlalchemy import func

    multiple = (
        db.query(WritingSession.id)
        .join(Chat, Chat.folder_id == WritingSession.folder_id)
        .filter(WritingSession.assignment_id == assignment_id)
        .group_by(WritingSession.id)
        .having(func.count(Chat.id) > 1)
        .first()
    )
    if multiple:
        raise HTTPException(409, 'Remove extra conversations before switching this assignment to revision.')


async def claim_revision_conversation(db, folder_id, user_id, chat_id):
    if not folder_id:
        return
    await lock_folder_assignments(db, [folder_id])
    # A real write serializes first-chat creation on both SQLite and PostgreSQL.
    ids = revision_sessions_query(folder_id)
    result = await db.execute(
        update(WritingSession)
        .where(WritingSession.id.in_(ids))
        .values(updated_at=WritingSession.updated_at)
        .returning(WritingSession.id, WritingSession.owner_user_id)
    )
    row = result.first()
    if row is None:
        return
    if row.owner_user_id != user_id:
        raise HTTPException(403, 'Only the student can create this assignment conversation.')
    from open_webui.models.chats import Chat

    existing = (await db.execute(select(Chat.id).where(Chat.folder_id == folder_id))).scalars().all()
    if existing:
        raise HTTPException(409, SINGLE_CONVERSATION_MESSAGE)
    await db.execute(
        update(WritingSession)
        .where(WritingSession.id == row.id)
        .values(
            chat_id=chat_id,
            active_chat_id=chat_id,
        )
    )


async def reject_revision_folder_change(db, old_folder_id, new_folder_id):
    if old_folder_id == new_folder_id:
        return
    await lock_folder_assignments(db, [old_folder_id, new_folder_id])
    if await is_revision_folder(db, old_folder_id) or await is_revision_folder(db, new_folder_id):
        raise HTTPException(409, SINGLE_CONVERSATION_MESSAGE)


async def reject_revision_chat_copy(db, folder_id, *, lock=False):
    if lock:
        await lock_folder_assignments(db, [folder_id])
    if await is_revision_folder(db, folder_id):
        raise HTTPException(409, SINGLE_CONVERSATION_MESSAGE)


def choose_conversation(chats, active_chat_id):
    """Prefer the active nonempty chat; otherwise the most recently updated nonempty chat."""
    if not chats:
        return None
    nonempty = [chat for chat in chats if chat['has_content']]
    candidates = nonempty or chats
    return next((chat for chat in candidates if chat['id'] == active_chat_id), None) or max(
        candidates, key=lambda chat: (chat['updated_at'], chat['created_at'], chat['id'])
    )


async def reject_revision_bulk_change(db, user_id):
    from open_webui.models.chats import Chat

    query = (
        select(Chat.id)
        .join(WritingSession, WritingSession.folder_id == Chat.folder_id)
        .join(Assignment, Assignment.id == WritingSession.assignment_id)
        .where(Chat.user_id == user_id, Assignment.task_mode.in_(REVISION_MODES))
        .limit(1)
    )
    if (await db.execute(query)).first():
        raise HTTPException(409, SINGLE_CONVERSATION_MESSAGE)


def consolidation_plan(db, session_ids=None):
    from open_webui.models.chats import Chat
    from open_webui.models.chat_messages import ChatMessage

    query = (
        db.query(WritingSession)
        .join(Assignment, Assignment.id == WritingSession.assignment_id)
        .filter(Assignment.task_mode.in_(REVISION_MODES))
    )
    if session_ids is not None:
        query = query.filter(WritingSession.id.in_(session_ids))
    plan = []
    for workspace in query.populate_existing().order_by(WritingSession.id).all():
        if not workspace.folder_id:
            continue
        chats = []
        for chat in (
            db.query(Chat).filter(Chat.folder_id == workspace.folder_id, Chat.user_id == workspace.owner_user_id).all()
        ):
            content = [
                row.content
                for row in db.query(ChatMessage)
                .filter(ChatMessage.chat_id == chat.id, ChatMessage.role.in_(['user', 'assistant']))
                .all()
            ]
            content += [
                item.get('content')
                for item in ((chat.chat or {}).get('history') or {}).get('messages', {}).values()
                if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
            ]
            chats.append(
                {
                    'id': chat.id,
                    'updated_at': chat.updated_at,
                    'created_at': chat.created_at,
                    'has_content': any(value.strip() if isinstance(value, str) else bool(value) for value in content),
                }
            )
        if not chats:
            continue
        keep = choose_conversation(chats, workspace.active_chat_id)
        drop = sorted(chat['id'] for chat in chats if chat['id'] != keep['id'])
        if drop or workspace.active_chat_id != keep['id'] or workspace.chat_id != keep['id']:
            plan.append(
                {
                    'session_id': workspace.id,
                    'active_chat_id': workspace.active_chat_id,
                    'chat_id': workspace.chat_id,
                    'keep': keep['id'],
                    'delete': drop,
                    'chats': sorted(chats, key=lambda row: row['id']),
                }
            )
    return plan


def apply_consolidation(db, plan):
    """Explicit maintenance only. Caller must stop the instance and back up before applying."""
    from sqlalchemy import delete
    from open_webui.models.chats import Chat, ChatFile
    from open_webui.models.chat_messages import ChatMessage
    from open_webui.models.shared_chats import SharedChat
    from open_webui.models.automations import AutomationRun

    ids = [row['session_id'] for row in plan]
    for session_id in sorted(ids):
        db.execute(
            update(WritingSession).where(WritingSession.id == session_id).values(updated_at=WritingSession.updated_at)
        )
    if consolidation_plan(db, ids) != plan:
        raise ValueError('Conversation records changed; generate and review a new plan.')
    for row in plan:
        db.execute(
            update(WritingSession)
            .where(WritingSession.id == row['session_id'])
            .values(chat_id=row['keep'], active_chat_id=row['keep'])
        )
        dropped = row['delete']
        if dropped:
            db.execute(update(AutomationRun).where(AutomationRun.chat_id.in_(dropped)).values(chat_id=None))
            db.execute(delete(SharedChat).where(SharedChat.chat_id.in_(dropped)))
            db.execute(delete(ChatFile).where(ChatFile.chat_id.in_(dropped)))
            db.execute(delete(ChatMessage).where(ChatMessage.chat_id.in_(dropped)))
            db.execute(delete(Chat).where(Chat.id.in_(dropped)))
    return sum(len(row['delete']) for row in plan)
