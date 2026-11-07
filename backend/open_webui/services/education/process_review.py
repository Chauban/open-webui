"""Read-only process views built exclusively from submission evidence."""

import difflib
import re
from uuid import UUID
from fastapi import HTTPException

SENTENCES = re.compile(r'[^。！？；!?;\n]*(?:[。！？；!?;]+|\n)|[^。！？；!?;\n]+')


def build_process_catalog(facts, stats):
    snapshots = {}
    bindings = {}
    version_ids = {}

    def add(key, text, kind, created_at=None, version_no=None, trigger_type=None, major=True):
        snapshots[key] = dict(
            id=key,
            text=text,
            kind=kind,
            created_at=created_at,
            version_no=version_no,
            trigger_type=trigger_type,
            major=major,
            used_by_ai=False,
        )
        return key

    if facts['draft_baseline_text'] is not None:
        start_id = add('initial', facts['draft_baseline_text'], 'initial')
    else:
        start_id = add('initial', '', 'empty_start')
    if facts.get('previous_round'):
        previous = facts['previous_round']
        add('round_start', previous['final_content_text'], 'round_start', previous['submitted_at'])
    final_id = facts['document']['final_version_id']
    final_no = None
    for version in facts['versions']:
        if version['id'] == final_id:
            final_no = version['version_no']
            continue
        key = add(
            'version:' + version['id'],
            version['content_text'],
            'version',
            version['created_at'],
            version['version_no'],
            version['trigger_type'],
            version['trigger_type'] != 'autosave',
        )
        version_ids[version['id']] = key
    add('final', facts['document']['content_text'], 'final', facts['submitted_at'], final_no, 'submit')
    version_ids[final_id] = 'final'

    def bind(event_key, text, created_at, source_version_id=None):
        if not isinstance(text, str):
            return
        key = version_ids.get(source_version_id)
        if key is None or snapshots[key]['text'] != text:
            key = (
                start_id
                if text == snapshots[start_id]['text']
                else add('source:' + event_key, text, 'reading', created_at)
            )
        snapshots[key]['major'] = True
        snapshots[key]['used_by_ai'] = True
        bindings[event_key] = key

    for reading in stats.get('revision_readings', []):
        bind(
            'reading:' + reading['id'], reading['source_text'], reading['created_at'], reading.get('source_version_id')
        )
    prompts = stats.get('prompt_timeline', [])
    contexts = {row['message_id']: row for row in stats.get('chat_contexts', [])}
    parent_bindings = {}
    for message in prompts:
        if message['role'] != 'assistant':
            continue
        context = contexts.get(message['id']) or message.get('education_context')
        if not context:
            continue
        event_key = 'prompt:' + message['id']
        bind(
            event_key,
            context.get('source_text'),
            context.get('called_at', message.get('created_at')),
            context.get('source_version_id'),
        )
        parent = message.get('parent_id')
        chat_id = message.get('chat_id')
        if not chat_id and len(message['id']) > 37 and message['id'][36] == '-':
            try:
                chat_id = str(UUID(message['id'][:36]))
            except ValueError:
                pass
        parent_ids = {parent, f'{chat_id}-{parent}'} if chat_id else {parent}
        parents = [
            row
            for row in prompts
            if row['role'] == 'user'
            and parent
            and row['id'] in parent_ids
            and (not chat_id or row.get('chat_id') in (None, chat_id))
        ]
        if len(parents) == 1 and event_key in bindings:
            parent_bindings.setdefault('prompt:' + parents[0]['id'], set()).add(bindings[event_key])
    for parent_key, source_ids in parent_bindings.items():
        if len(source_ids) == 1:
            bindings[parent_key] = next(iter(source_ids))
    ordered = sorted(
        snapshots.values(),
        key=lambda row: (
            0 if row['id'] == 'initial' else 2 if row['id'] == 'final' else 1,
            row['created_at'] or 0,
            row['version_no'] or 0,
            row['id'],
        ),
    )
    return {
        'snapshots': ordered,
        'event_snapshots': bindings,
        'default_before_id': start_id,
        'default_after_id': 'final',
        'final_version_id': final_id,
        'round_no': facts['round_no'],
    }


def catalog_metadata(catalog):
    return {**catalog, 'snapshots': [{k: v for k, v in row.items() if k != 'text'} for row in catalog['snapshots']]}


def compare_snapshots(catalog, before_id, after_id):
    by_id = {row['id']: row for row in catalog['snapshots']}
    if before_id not in by_id or after_id not in by_id:
        raise HTTPException(404, 'The requested draft is not part of this submission.')
    before, after = by_id[before_id], by_id[after_id]
    old, new = SENTENCES.findall(before['text']), SENTENCES.findall(after['text'])
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    blocks = [
        {'op': op, 'old_text': ''.join(old[i:j]), 'new_text': ''.join(new[k:l])}
        for op, i, j, k, l in matcher.get_opcodes()
    ]
    return {
        'before': before,
        'after': after,
        'blocks': blocks,
        'unchanged': before['text'] == after['text'],
        'final_version_id': catalog['final_version_id'],
    }
