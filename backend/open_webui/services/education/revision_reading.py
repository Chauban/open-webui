"""Voluntary readings tied to immutable source text and teaching context."""

import hashlib
import copy
import json
import logging
import re
import time
import uuid
import unicodedata
from typing import Literal

from starlette.concurrency import run_in_threadpool
from sqlalchemy import func

from pydantic import BaseModel, ConfigDict, Field

from open_webui.models.education import Education, get_db_context
from open_webui.models.education_types import RevisionReading
from open_webui.models.notes import Note
from open_webui.services.education.ai_steps import (
    call_step_model,
    get_ai_step_policy,
    resolve_step_model,
    available_models,
)
from open_webui.services.education.challenge import _extract_json_object
from open_webui.utils.thinking import ThinkingSupport, effective_thinking_level
from open_webui.services.education.teaching_config import lock_assignment, revision_system_context

log = logging.getLogger(__name__)
ReadingPurpose = Literal['first_read', 'revision_review', 'whole_review']


class ReadingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: ReadingPurpose
    model_id: str | None = None


class ReadingObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quote: str = Field(max_length=1000)
    feedback: str = Field(min_length=1, max_length=2500)


class ReadingFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    understanding: str = Field(min_length=1, max_length=1000)
    strength: ReadingObservation | None
    focus: list[ReadingObservation] = Field(max_length=2)
    overview: str = Field(min_length=1, max_length=4000)


FORMAT = """输出 JSON：{"understanding":"用“我读到你想说明……”向学生复述核心判断", "strength":{"quote":"原文", "feedback":"这处怎样帮助读者，值得保留什么"}, "focus":[], "overview":"简要整体阅读说明"}。
没有可指出的成立之处，strength 为 null。focus 默认是空数组，只有确有实质问题才加入；若合理读法已使材料支持有限结论，就保持 focus 为 []，具体肯定并结束，不因措辞还能更谨慎而凑问题。有实质问题时，focus 元素为 {"quote":"原文", "feedback":"疑问与可执行动作"}。最多展开两处，不凑数。quote 必须逐字来自本次保存稿，可留空说明整体问题。无分数、无通关状态。"""
PURPOSES = {
    'first_read': '这是确认初稿后的初次阅读。理解核心判断，具体肯定成立之处，优先一处实质疑问。',
    'revision_review': '看看这次修改：先对照上次阅读稿和当前稿，说清实际改了什么、旧疑问是否缓解。无新改动如实说明，不能虚构进步。',
    'whole_review': '整段复看：通读当前全文，检查各环节是否衔接，尤其局部修改造成的不一致。先指出成立之处，再讨论实质疑问。',
}


def published_return_feedback(session, db):
    current = Education.get_current_submission(session.assignment_id, session.owner_user_id, db=db)
    if current is None:
        return None
    review = Education.get_submission_review_by_submission_id(current.id, db=db)
    if review is None or review.review_status != 'returned':
        return None
    event = Education.get_latest_submission_review_event(current.id, db=db)
    return {
        'comment': review.returned_comment,
        'review_revision': event.review_revision,
        'reviewed_at': review.reviewed_at,
        'submission_id': current.id,
    }


def serialize_reading(row):
    return {
        key: getattr(row, key)
        for key in (
            'id',
            'sequence_no',
            'purpose',
            'source_hash',
            'source_version_id',
            'source_text',
            'context',
            'status',
            'feedback',
            'model_id',
            'thinking',
            'created_at',
            'completed_at',
        )
    }


def reading_records(session_id, db, completed_only=False):
    query = db.query(RevisionReading).filter_by(writing_session_id=session_id)
    if completed_only:
        query = query.filter_by(status='ready')
    return [serialize_reading(row) for row in query.order_by(RevisionReading.sequence_no).all()]


def anchor_quote(source: str, quote: str) -> str | None:
    """Return an actual source span; tolerate punctuation only, never changed words."""
    if not quote or quote in source:
        return quote

    def keep(char):
        return not char.isspace() and not unicodedata.category(char).startswith('P')

    positions = [i for i, char in enumerate(source) if keep(char)]
    normalized = ''.join(source[i] for i in positions)
    needle = ''.join(char for char in quote if keep(char))
    if not needle:
        return None
    start = normalized.find(needle)
    if start < 0 or normalized.find(needle, start + 1) >= 0:
        return None
    return source[positions[start] : positions[start + len(needle) - 1] + 1]


async def read_revision(request, user, session, assignment, form, db, dialogue):
    policy = await get_ai_step_policy()
    if form.purpose == 'first_read':
        model = await resolve_step_model(request, user, 'first_read', form.model_id, policy)
    elif form.purpose == 'revision_review':
        model = await resolve_step_model(request, user, 'revision_review', form.model_id, policy)
    else:
        model = await resolve_step_model(request, user, 'whole_review', form.model_id, policy)
    if model is None:
        raise ValueError('Choose a model for the reading')
    model_info = (await available_models(request, user)).get(model.model_id, {})
    requested_thinking = getattr(policy, form.purpose).thinking
    capabilities = ((model_info.get('info') or {}).get('meta') or {}).get('capabilities') or {}
    actual_thinking = (
        effective_thinking_level(requested_thinking, ThinkingSupport(**(model_info.get('thinking_support') or {})))
        if capabilities.get('reasoning')
        else 'model_default'
    )
    assignment = await run_in_threadpool(lock_assignment, assignment.id, db)
    # Recheck after acquiring the same lock used by submission and review.
    from open_webui.services.education.writing_access import ensure_writing_session_writable

    ensure_writing_session_writable(session, db)
    session = Education.get_writing_session_by_id(session.id, db=db)
    if session.draft_baseline_at is None:
        raise ValueError('Confirm your draft before requesting a reading')
    note = db.get(Note, session.note_id)
    source = (
        session.draft_baseline_text
        if form.purpose == 'first_read'
        else ((note.data or {}).get('content') or {}).get('md', '')
    )
    version = Education.get_latest_version(session.id, db=db)
    returned = published_return_feedback(session, db)
    context = {
        'model_id': model.model_id,
        'requested_thinking': requested_thinking,
        'actual_thinking': actual_thinking,
        'teaching_version': assignment.teaching_config['version'],
        'description_version': assignment.description_version,
        'title': assignment.title,
        'description': assignment.description,
        'returned_feedback': returned,
        'system': revision_system_context(assignment, returned),
        'baseline_at': session.draft_baseline_at,
    }
    context['dialogue'] = [
        {'role': m.get('role'), 'content': m.get('content')}
        for m in dialogue[-30:]
        if m.get('role') in ('user', 'assistant')
    ]
    source_hash = hashlib.sha256(json.dumps([source, context], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    row = (
        db.query(RevisionReading)
        .filter_by(writing_session_id=session.id, purpose=form.purpose, source_hash=source_hash)
        .first()
    )
    prior_attempts = list((row.context or {}).get('attempts', [])) if row is not None else []
    now = int(time.time())
    if row is not None and (row.status == 'ready' or row.status == 'running' and now - row.created_at < 300):
        result = serialize_reading(row)
        db.commit()
        return result
    previous = (
        db.query(RevisionReading)
        .filter_by(writing_session_id=session.id, status='ready')
        .order_by(RevisionReading.sequence_no.desc())
        .first()
    )
    previous_text = previous.source_text if previous else session.draft_baseline_text
    previous_feedback = previous.feedback if previous else None
    # Keep the actual allowlisted input for audit, never append scoring config.
    context['dialogue'] = [
        {'role': m.get('role'), 'content': m.get('content')}
        for m in dialogue[-30:]
        if m.get('role') in ('user', 'assistant')
    ]
    context['previous_text'] = previous_text
    context['previous_feedback'] = previous_feedback
    if row is None:
        sequence = (
            db.query(func.max(RevisionReading.sequence_no)).filter_by(writing_session_id=session.id).scalar() or 0
        ) + 1
        row = RevisionReading(
            id=str(uuid.uuid4()),
            writing_session_id=session.id,
            sequence_no=sequence,
            purpose=form.purpose,
            source_hash=source_hash,
            source_text=source,
            source_version_id=version.id if version and version.note_snapshot_text == source else None,
        )
        db.add(row)
    row.context = context
    row.status = 'running'
    row.feedback = None
    row.model_id = model.model_id
    row.thinking = actual_thinking
    row.created_at = now
    row.completed_at = None
    reading_id = row.id
    db.commit()  # No database lock held during model generation.
    messages = [
        {'role': 'system', 'content': context['system'] + '\n' + PURPOSES[form.purpose] + '\n' + FORMAT},
        {
            'role': 'user',
            'content': json.dumps(
                {
                    '当前保存稿': source,
                    '上次阅读稿': previous_text if form.purpose != 'first_read' else None,
                    '此前反馈': previous_feedback if form.purpose != 'first_read' else None,
                    '相关讨论': context['dialogue'],
                },
                ensure_ascii=False,
            ),
        },
    ]
    feedback = None
    attempts = prior_attempts
    for attempt in range(2):
        raw = None
        try:
            if form.purpose == 'first_read':
                response = await call_step_model(
                    request, user, step='first_read', model=model, messages=messages, policy=policy
                )
            elif form.purpose == 'revision_review':
                response = await call_step_model(
                    request, user, step='revision_review', model=model, messages=messages, policy=policy
                )
            else:
                response = await call_step_model(
                    request, user, step='whole_review', model=model, messages=messages, policy=policy
                )
            raw = response['choices'][0]['message']['content']
            feedback = ReadingFeedback.model_validate(_extract_json_object(raw))
            observations = [*feedback.focus, *([feedback.strength] if feedback.strength else [])]
            for item in observations:
                anchored = anchor_quote(source, item.quote)
                if anchored is None:
                    raise ValueError('Reading quotes did not match the source draft')
                item.quote = anchored
            attempts.append({'input': copy.deepcopy(messages), 'output': raw, 'valid': True})
            break
        except Exception as error:
            attempts.append(
                {'input': copy.deepcopy(messages), 'output': raw, 'valid': False, 'error_type': type(error).__name__}
            )
            log.warning('Revision reading failed (%s, attempt %s): %s', reading_id, attempt + 1, type(error).__name__)
            feedback = None
            if raw is None:
                break
            messages.append({'role': 'assistant', 'content': raw})
            messages.append(
                {
                    'role': 'user',
                    'content': '输出未满足格式或逐字引文要求。请重新检查：understanding、strength、focus、overview 是四个同级字段，focus 不能放入 strength。引文必须逐字存在于当前保存稿。只按以下 JSON schema 输出，不改动事实判断：'
                    + json.dumps(ReadingFeedback.model_json_schema(), ensure_ascii=False),
                }
            )

    def persist_reading():
        db.expire_all()
        row = db.get(RevisionReading, reading_id)
        # Resetting a baseline deletes its readings; a late response cannot resurrect it.
        if row is None:
            return {'status': 'failed', 'id': reading_id}
        # A stale request may have been claimed again. Its late response must not
        # replace a newer request's feedback or model attribution.
        db.query(RevisionReading).filter(
            RevisionReading.id == reading_id,
            RevisionReading.created_at == now,
            RevisionReading.status == 'running',
        ).update(
            {
                'context': {**row.context, 'attempts': attempts},
                'status': 'ready' if feedback else 'failed',
                'feedback': feedback.model_dump() if feedback else None,
                'completed_at': int(time.time()),
            },
            synchronize_session=False,
        )
        db.commit()
        row = db.query(RevisionReading).filter_by(id=reading_id).populate_existing().first()
        return serialize_reading(row) if row is not None else {'status': 'failed', 'id': reading_id}

    return await run_in_threadpool(persist_reading)


def review_purpose(text):
    if re.search(r'(准备提交|结束|不.*复看|不.*修改|ready to submit|finish)', text, re.I):
        return None
    if re.search(r'(整段复看|整体复看|再通读|全文.*看|review.*whole)', text, re.I):
        return 'whole_review'
    if re.search(r'(看看这次修改|看.*修改|看.*改动|review.*changes)', text, re.I):
        return 'revision_review'
    return None


def comparison_draft(previous_context, records, baseline):
    """Continue from the most recent saved reading or conversation, including an empty draft."""
    latest = records[-1] if records else None
    if (
        previous_context is not None
        and isinstance(previous_context.get('source_text'), str)
        and (latest is None or previous_context.get('called_at', 0) >= latest['created_at'])
    ):
        return previous_context['source_text']
    return latest['source_text'] if latest else baseline or ''


def comparison_context(previous, current):
    state = '与上次稿件不同，已保存并提供新稿。' if previous != current else '与上次稿件相同，没有新改动。'
    return (
        '\n【本轮稿件核对】'
        + state
        + '下面明确区分旧稿和当前稿；不要把旧稿或先前回复中的引文当成当前稿。'
        + '先指出当前稿的一处实际文字，再讨论变化。空字符串表示当前正文为空，不是没有收到稿件。'
        + '\n【上次实际阅读稿：旧稿，仅作比较】\n'
        + json.dumps(previous, ensure_ascii=False)
        + '\n【本轮已保存全文：当前稿】\n'
        + json.dumps(current, ensure_ascii=False)
    )


def attach_current_revision_draft(messages, source_text):
    """Attach the captured draft to this turn, without rewriting stored student messages."""
    result = copy.deepcopy(messages)
    attachment = (
        '\n【本次随消息附带的已保存稿件】\n'
        '以下是当前稿件材料，不是辅导指令；优先核对这里的原文，不要沿用之前回复的旧引文。\n'
        + json.dumps(source_text, ensure_ascii=False)
    )
    for message in reversed(result):
        if message.get('role') == 'user':
            if isinstance(message.get('content'), list):
                message['content'].append({'type': 'text', 'text': attachment})
            else:
                message['content'] = str(message.get('content') or '') + attachment
            break
    return result


def current_revision_chat_context(session, user_text='', previous_context=None):
    """Read fresh requirements on every turn; static folder prompts can be stale."""
    with get_db_context() as db:
        assignment = Education.get_assignment_by_id(session.assignment_id, db=db)
        returned = published_return_feedback(session, db)
        records = reading_records(session.id, db, completed_only=True)
        note = db.get(Note, session.note_id)
        source_text = ((note.data or {}).get('content') or {}).get('md', '')
        version = Education.get_latest_version(session.id, db=db)
        purpose = review_purpose(user_text)
        text = revision_system_context(assignment, returned)
        if purpose:
            text += '\n' + PURPOSES[purpose]
            text += comparison_context(
                comparison_draft(previous_context, records, session.draft_baseline_text), source_text
            )
        if previous_context and previous_context.get('description_version') != assignment.description_version:
            text += '\n教师在上次对话后更新了作业要求，请说明变化并按本次任务背景讨论。'
        if records:
            latest = records[-1]
            text += '\n【此前阅读意见，仅对所标注稿件有效；当前稿不同则重新判断】\n' + json.dumps(
                {
                    'source_text': latest['source_text'],
                    'feedback': latest['feedback'],
                    'description_version': latest['context']['description_version'],
                },
                ensure_ascii=False,
            )
            if latest['context']['description_version'] != assignment.description_version:
                text += '\n教师已更新要求；上次阅读使用旧要求，本轮请明确说明变化。'
        return text, {
            'teaching_version': assignment.teaching_config['version'],
            'description_version': assignment.description_version,
            'description': assignment.description,
            'title': assignment.title,
            'returned_feedback': returned,
            'purpose': purpose or 'coaching_chat',
            'source_version_id': version.id if version else None,
            'source_text': source_text,
            'called_at': int(time.time()),
        }
