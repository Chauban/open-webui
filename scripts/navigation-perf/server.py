"""Loopback-only production-frontend navigation fixture; no database or model access.

Run with backend/.venv/Scripts/python.exe scripts/navigation-perf/server.py.
All API data is synthetic. Each API response incurs 400 ms simulated RTT; this
measures frontend request scheduling/rendering, not production server latency.
"""

import asyncio
import base64
import copy
import json
import os
import time
from pathlib import Path

import socketio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.gzip import GZipMiddleware

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get('NAVIGATION_PERF_BUILD', ROOT / 'build')).resolve()
app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=[])
now = int(time.time())
model = {'id': 'fixture-model', 'name': '隔离模拟模型', 'owned_by': 'openai', 'info': {'meta': {'capabilities': {}}}}
user = {
    'id': 'perf-student',
    'name': '隔离测速学生',
    'email': 'perf@example.test',
    'role': 'user',
    'education_role': 'student',
    'profile_image_url': '/user.png',
    'permissions': {'chat': {'multiple_models': False}, 'features': {}},
    'expires_at': now + 86400,
}
states = {}
requests = []
settings = {
    'delay_ms': 400,
    'tags_delay_ms': 400,
    'save_fail': False,
    'hidden': [],
    'denied': False,
    'aggregate': False,
    'delays': {},
    'extra': [],
    'full_context': False,
}


def document(text):
    return {
        'type': 'doc',
        'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': part}]} if part else {'type': 'paragraph'}
            for part in text.split('\n')
        ],
    }


def make_state(key, chars, count, status='ready', mode='revise_argument'):
    text = ('这是一份用于性能验收的合成大学写作稿件，讨论公共空间中的证据与论证关系。\n' * (chars // 36 + 1))[:chars]
    aid, sid, cid, fid = key, f'session-{key}', f'chat-{key}', f'folder-{key}'
    confirmed = key not in ('empty', 'pending')
    assignment = {
        'id': aid,
        'classroom_id': 'perf-class',
        'teacher_id': 'perf-teacher',
        'title': f'隔离验收 {key}',
        'description': '仅使用合成稿件与模拟模型。',
        'task_mode': mode,
        'due_at': now - 86400 if key == 'overdue' else now + 86400,
        'score_max': 100,
        'scoring_mode': 'total',
        'rubric_schema': {'criteria': []},
        'reflection_questions': [],
        'challenge_enabled': False,
        'config_revision': 1,
        'created_at': now,
        'updated_at': now,
    }
    session = {
        'id': sid,
        'assignment_id': aid,
        'owner_user_id': user['id'],
        'scope': 'assignment',
        'status': 'submitted' if key == 'readonly' else 'draft',
        'note_id': f'note-{key}',
        'folder_id': fid,
        'active_chat_id': cid if count else None,
        'draft_baseline_at': now - 100 if confirmed else None,
        'draft_baseline_text': text if confirmed else '',
        'created_at': now,
        'updated_at': now,
    }
    history = {}
    for i in range(count):
        mid = f'{key}-message-{i}'
        history[mid] = {
            'id': mid,
            'parentId': f'{key}-message-{i - 1}' if i else None,
            'childrenIds': [f'{key}-message-{i + 1}'] if i < count - 1 else [],
            'role': 'assistant' if i % 2 else 'user',
            'content': f'合成历史消息 {key} {i}：请核对这段论证中的证据关系。',
            'timestamp': now - 100 + i,
            'done': key != 'generating' or i != count - 1,
            'model': model['id'],
            'modelName': model['name'],
        }
    readings = (
        []
        if not confirmed or mode == 'from_scratch' or key == 'unread'
        else [
            {
                'id': f'reading-{key}',
                'writing_session_id': sid,
                'purpose': 'first_read',
                'status': status,
                'source_text': text,
                'source_json': document(text),
                'feedback': {'overview': '合成初读反馈', 'focus': []} if status == 'ready' else None,
                'created_at': now - 100,
                'context': {'chat_id': cid, 'message_id': f'{key}-message-1'},
                'error': '模拟初读失败' if status == 'failed' else None,
            }
        ]
    )
    project = {
        'id': fid,
        'name': assignment['title'],
        'user_id': user['id'],
        'meta': {
            'mode': 'assignment_writing',
            'assignment_id': aid,
            'writing_session_id': sid,
            'single_conversation': mode != 'from_scratch',
        },
        'data': {},
        'created_at': now,
        'updated_at': now,
    }
    pending = {'content_json': document(text), 'materials': [], 'revision': 1 if chars else 0}
    review = (
        {
            'review_status': 'reviewed',
            'score': 90,
            'round_no': 1,
            'comment': '合成评阅',
            'scoring_config': {'score_max': 100, 'scoring_mode': 'total', 'rubric_schema': {'criteria': []}},
        }
        if key == 'readonly'
        else None
    )
    workspace = {
        'assignment': assignment,
        'membership_role': 'student',
        'writing_session': session,
        'project': project,
        'note': {
            'id': session['note_id'],
            'title': assignment['title'],
            'data': {'content': {'md': text if confirmed else '', 'json': document(text if confirmed else '')}},
        },
        'active_chat_id': session['active_chat_id'],
        'source_map': [],
        'review': review,
        'effective_due_at': assignment['due_at'],
        'can_switch_thinking': False,
        'initial_state': {
            'teaching_summary': {**model, 'revision': 1, 'thinking': 'medium'} if mode == 'revise_argument' else None,
            'pending_draft': pending if not confirmed else None,
            'readings': readings,
            'challenge': None,
        },
    }
    return {
        'workspace': workspace,
        'pending': pending,
        'readings': readings,
        'chat': {
            'id': cid,
            'user_id': user['id'],
            'folder_id': fid,
            'title': assignment['title'],
            'chat': {
                'title': assignment['title'],
                'models': [model['id']],
                'history': {'messages': history, 'currentId': f'{key}-message-{count - 1}' if count else None},
            },
            'created_at': now,
            'updated_at': now,
        },
    }


for args in [
    ('empty', 0, 0),
    ('pending', 2000, 0),
    ('ordinary', 2000, 10),
    ('long', 20000, 50),
    ('stress', 100000, 200),
    ('running', 2000, 10, 'running'),
    ('failed', 2000, 10, 'failed'),
    ('readonly', 2000, 10),
    ('generating', 2000, 10),
    ('overdue', 2000, 10),
    ('unread', 2000, 0),
    ('scratch', 2000, 10, 'ready', 'from_scratch'),
    ('literature', 2000, 10, 'ready', 'revise_draft'),
    ('returned', 2000, 10),
    ('illustrated', 2000, 10),
]:
    states[args[0]] = make_state(*args)

states['returned']['workspace']['review'] = {
    'review_status': 'returned',
    'comment': '合成退回意见',
    'round_no': 1,
    'resubmit_due_at': now + 86400,
}
illustrated = states['illustrated']['workspace']['note']['data']['content']
illustrated['json']['content'].extend(
    [
        {
            'type': 'table',
            'content': [
                {
                    'type': 'tableRow',
                    'content': [
                        {'type': 'tableCell', 'content': document('合成表格甲')['content']},
                        {'type': 'tableCell', 'content': document('合成表格乙')['content']},
                    ],
                }
            ],
        },
        {
            'type': 'writingImage',
            'attrs': {'materialId': 'fixture-material', 'blockId': 'image-1', 'width': 70},
            'content': [{'type': 'text', 'text': '合成图片说明'}],
        },
    ]
)
illustrated['md'] += '\n合成表格甲\n合成表格乙\n合成图片说明'


def visible(key):
    return key not in settings['hidden'] and (key not in ('returned', 'illustrated') or key in settings['extra'])


@app.api_route('/__fixture', methods=['GET', 'POST'])
async def control(request: Request):
    if request.method == 'POST':
        body = await request.json()
        event = body.pop('event', None)
        notification = body.pop('notification', None)
        reconnect = body.pop('reconnect', False)
        settings.update(body)
        requests.clear()
        if event:
            await sio.emit('events', event)
        if notification:
            await sio.emit('education:notification', notification)
        if reconnect:
            for connection in list(sio.eio.sockets.values()):
                await connection.close(wait=False, abort=True)
    return {'settings': settings, 'requests': requests[-500:]}


@app.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def api(path: str, request: Request):
    start = time.perf_counter()
    await asyncio.sleep(
        settings['delays'].get(path, settings['tags_delay_ms'] if path.endswith('/tags') else settings['delay_ms'])
        / 1000
    )
    data = None
    code = 200
    key = next(
        (
            k
            for k in states
            if f'/{k}/' in f'/{path}/'
            or any(f'/{prefix}-{k}/' in f'/{path}/' for prefix in ('session', 'chat', 'folder'))
        ),
        None,
    )
    state = states.get(key)
    if path.startswith('v1/writing-materials/fixture-material/'):
        return Response(
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z2WQAAAAASUVORK5CYII='
            ),
            media_type='image/png',
        )
    if path == 'config':
        data = {
            'status': True,
            'name': 'Right Write 隔离验收',
            'version': '0.11.2',
            'default_locale': 'zh-CN',
            'default_models': model['id'],
            'features': {'auth': True, 'enable_websocket': True, 'enable_education_return': True},
            'audio': {'tts': {}, 'stt': {}},
            'file': {},
            'ui': {},
            'permissions': user['permissions'],
        }
    elif path == 'version':
        data = {'version': '0.11.2'}
    elif path == 'v1/auths/':
        data = user
    elif path.endswith('/settings'):
        data = {'ui': {'models': [model['id']], 'notificationEnabled': False}}
    elif path == 'models':
        data = {'data': [model]}
    elif path.endswith('/notifications/summary'):
        data = {'total': 0, 'by_type': {}, 'by_assignment': {}}
    elif path == 'v1/me/writing/home':
        items = [s['workspace'] for k, s in states.items() if visible(k)]
        data = {
            'role': 'student',
            'personal_writing_enabled': False,
            'classrooms': [{'id': 'perf-class', 'name': '隔离性能验收班'}],
            'personal_items': [],
            'recent_items': [],
            'assignment_items': [
                {
                    'assignment': w['assignment'],
                    'writing_session_id': w['writing_session']['id'],
                    'project_id': w['project']['id'],
                    'status': w['writing_session']['status'],
                    'review_status': (w['review'] or {}).get('review_status'),
                    'updated_at': now,
                    'effective_due_at': w['effective_due_at'],
                }
                for w in items
            ],
        }
    elif state and (settings['denied'] or key in settings['hidden']):
        code, data = 403, {'detail': 'Assignment access denied'}
    elif state and path.endswith('/workspace'):
        data = copy.deepcopy(state['workspace'])
        if not settings['aggregate']:
            data.pop('initial_state')
    elif state and path.endswith('/teaching-summary'):
        data = state['workspace']['initial_state']['teaching_summary']
    elif state and path.endswith('/pending-draft'):
        if request.method == 'GET':
            data = state['pending']
        elif settings['save_fail']:
            code, data = 400, {'detail': 'Synthetic save failure'}
        else:
            body = await request.json()
            state['pending'] = {**body, 'revision': state['pending']['revision'] + 1}
            data = {'revision': state['pending']['revision']}
    elif state and path.endswith('/readings'):
        if request.method == 'GET':
            data = state['readings']
        else:
            code, data = 409, {'detail': 'Navigation must not start a model'}
    elif state and path == f'v1/chats/chat-{key}':
        data = copy.deepcopy(state['chat'])
        if settings['full_context']:
            for message in data['chat']['history']['messages'].values():
                if message['role'] == 'assistant':
                    message['meta'] = {
                        'education_context': {
                            'source_text': state['workspace']['note']['data']['content']['md'],
                            'called_at': message['timestamp'],
                        }
                    }
    elif path.startswith('tasks/chat/'):
        data = {'task_ids': ['fixture-task'] if key == 'generating' else []}
    elif path.endswith('/process-summary'):
        data = {'clarification_answered_count': 0}
    elif path == 'v1/folders/':
        data = [s['workspace']['project'] for k, s in states.items() if visible(k)]
    elif state and path.startswith('v1/folders/'):
        data = state['workspace']['project']
    elif path == 'v1/chats/' or path.startswith('v1/chats/folder/'):
        data = []
    elif path.endswith('/autosave'):
        if settings['save_fail']:
            code, data = 400, {'detail': 'Synthetic save failure'}
        else:
            body = await request.json()
            if state:
                state['workspace']['note']['data']['content'] = {
                    'md': body.get('content_text', ''),
                    'json': body.get('content_json'),
                }
            data = {'ok': True}
    elif path.endswith('/versions'):
        data = {'id': 'fixture-version'}
    elif path.endswith('/config'):
        data = {}
    elif request.method != 'GET':
        data = {'ok': True}
    else:
        data = []
    raw = json.dumps(data, ensure_ascii=False).encode()
    requests.append(
        {
            'path': path,
            'method': request.method,
            'status': code,
            'duration_ms': round((time.perf_counter() - start) * 1000, 2),
            'json_bytes': len(raw),
        }
    )
    return JSONResponse(copy.deepcopy(data), status_code=code)


@app.get('/{path:path}')
async def frontend(path: str):
    build = BUILD
    target = (build / path).resolve()
    if not target.is_relative_to(build):
        return JSONResponse({'detail': 'Forbidden'}, status_code=403)
    if not target.is_file() and path and not path.startswith('_app/'):
        shared = (ROOT / 'build' / path).resolve()
        if shared.is_relative_to((ROOT / 'build').resolve()) and shared.is_file():
            return FileResponse(shared)
    return FileResponse(target if target.is_file() else build / 'index.html')


if __name__ == '__main__':
    uvicorn.run(socketio.ASGIApp(sio, app, socketio_path='ws/socket.io'), host='127.0.0.1', port=5099)
