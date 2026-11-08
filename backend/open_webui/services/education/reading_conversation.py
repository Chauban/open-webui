"""Persist a completed reading as a real message in the workspace conversation."""

import copy
import time
import uuid

from open_webui.models.chats import Chat
from open_webui.models.chat_messages import ChatMessages
from open_webui.models.education import WritingSession


def reading_reply(feedback):
    parts = [feedback['understanding']]
    if feedback['strength']:
        parts.append(feedback['strength']['feedback'])
    for item in feedback['focus']:
        if item['quote']:
            parts.append('> ' + item['quote'].replace('\n', '\n> '))
        parts.append(item['feedback'])
    parts.append(feedback['overview'])
    return '\n\n'.join(part for part in parts if part)


def append_reading_message(db, session_id, assignment, reading):
    """Caller holds the assignment lock; reading and chat commit atomically."""
    session = db.get(WritingSession, session_id)
    chat = db.query(Chat).filter_by(folder_id=session.folder_id, user_id=session.owner_user_id).one_or_none()
    now = int(time.time())
    if chat is None:
        chat = Chat(
            id=str(uuid.uuid4()), user_id=session.owner_user_id, folder_id=session.folder_id,
            title=assignment.title, created_at=now, updated_at=now,
            chat={'title': assignment.title, 'models': [reading.model_id], 'params': {},
                  'history': {'messages': {}, 'currentId': None}},
        )
        db.add(chat)
        db.flush()
    payload = copy.deepcopy(chat.chat)
    history = payload['history']
    message_id = f'reading-{reading.id}'
    parent_id = history['currentId']
    context = {
        **{key: reading.context[key] for key in ('ai_revision_id', 'ai_revision', 'call_id', 'config') if key in reading.context},
        'reading_id': reading.id, 'purpose': reading.purpose,
        'source_text': reading.source_text, 'source_version_id': reading.source_version_id,
        'materials': reading.context.get('materials', []),
        'teaching_version': reading.context['teaching_version'],
        'description_version': reading.context['description_version'],
        'called_at': reading.created_at,
    }
    message = {
        'id': message_id, 'role': 'assistant', 'parentId': parent_id, 'childrenIds': [],
        'content': reading_reply(reading.feedback), 'model': reading.model_id,
        'timestamp': now, 'done': True,
        'meta': {'education_context': context, 'thinking_level': reading.thinking},
    }
    if parent_id:
        history['messages'][parent_id]['childrenIds'].append(message_id)
    history['messages'][message_id] = message
    history['currentId'] = message_id
    chat.chat = payload
    chat.current_message_id = message_id
    chat.updated_at = now
    db.add(ChatMessages._build_message(f'{chat.id}-{message_id}', chat.id, session.owner_user_id, message, now))
    session.chat_id = session.active_chat_id = chat.id
    reading.context = {**reading.context, 'chat_id': chat.id, 'message_id': message_id}
