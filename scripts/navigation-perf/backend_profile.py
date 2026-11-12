"""Profile real GET routes against migration-built, synthetic SQLite data only."""

import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
scratch = tempfile.TemporaryDirectory(prefix='rightwrite-profile-', ignore_cleanup_errors=True)
os.environ['DATA_DIR'] = scratch.name
os.environ['DATABASE_URL'] = f'sqlite:///{Path(scratch.name).as_posix()}/bootstrap.db'
os.environ['WEBUI_SECRET_KEY'] = 'isolated-navigation-profile-only'
os.environ.pop('TEST_DATABASE_URL', None)

import pytest
from sqlalchemy import event
import open_webui.internal.db as internal_db
from open_webui.models.chats import Chat
from open_webui.models.chat_messages import ChatMessage
from open_webui.models.notes import Note
from open_webui.services.education.writing_document import text_document
from open_webui.test.apps.webui.routers.test_education_smoke import education_client
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, model_stub

fixture = education_client.__wrapped__()
client, teacher, _, student, _, sessions = next(fixture)
report = {
    'environment': 'SQLite, real Alembic migrations, FastAPI TestClient, no simulated network delay',
    'samples': [],
}
try:
    assignment, sid, _ = setup(client, teacher, student)
    with pytest.MonkeyPatch.context() as patch:
        calls = model_stub(patch, text='隔离模拟初读反馈')
        result = client.post(f'/api/v1/writing-sessions/{sid}/readings', json={'purpose': 'first_read'})
        assert result.status_code == 200, result.status_code
        workspace = client.get(f'/api/v1/assignments/{assignment["id"]}/workspace').json()
        cid = workspace['active_chat_id']
        for chars, count in [(2000, 10), (20000, 50), (100000, 200)]:
            text = ('合成大学写作稿件讨论证据、解释和公共空间的关系。\n' * (chars // 20 + 1))[:chars]
            with sessions() as db:
                note = db.get(Note, workspace['note']['id'])
                note.data = {**note.data, 'content': {'json': text_document(text), 'md': text}}
                chat = db.get(Chat, cid)
                messages = dict(chat.chat['history']['messages'])
                parent = chat.chat['history']['currentId']
                for index in range(count - len(messages)):
                    mid = f'profile-{chars}-{index}'
                    role = 'user' if index % 2 == 0 else 'assistant'
                    meta = (
                        {'education_context': {'source_text': text, 'called_at': int(time.time())}}
                        if role == 'assistant'
                        else {}
                    )
                    value = {
                        'id': mid,
                        'role': role,
                        'content': f'合成历史消息 {index}',
                        'parentId': parent,
                        'childrenIds': [],
                        'done': True,
                        'timestamp': int(time.time()),
                        'meta': meta,
                    }
                    if parent in messages:
                        messages[parent]['childrenIds'] = [mid]
                    messages[mid] = value
                    db.add(
                        ChatMessage(
                            id=mid,
                            chat_id=cid,
                            user_id=student.id,
                            role=role,
                            content=value['content'],
                            parent_id=parent,
                            meta=meta,
                            done=True,
                            created_at=value['timestamp'],
                            updated_at=value['timestamp'],
                        )
                    )
                    parent = mid
                chat.chat = {**chat.chat, 'history': {'messages': messages, 'currentId': parent}}
                db.commit()
            engines = [sessions.kw['bind'], internal_db.AsyncSessionLocal.kw['bind'].sync_engine]
            sql = []

            def before(conn, cursor, statement, params, context, many):
                context._navigation_start = time.perf_counter()

            def after(conn, cursor, statement, params, context, many):
                sql.append((time.perf_counter() - context._navigation_start) * 1000)

            for engine in engines:
                event.listen(engine, 'before_cursor_execute', before)
                event.listen(engine, 'after_cursor_execute', after)
            try:
                for name, url in [
                    ('workspace', f'/api/v1/assignments/{assignment["id"]}/workspace'),
                    ('chat', f'/api/v1/chats/{cid}'),
                ]:
                    for iteration in range(20):
                        sql.clear()
                        start = time.perf_counter()
                        response = client.get(url)
                        elapsed = (time.perf_counter() - start) * 1000
                        assert response.status_code == 200, response.status_code
                        report['samples'].append(
                            {
                                'chars': chars,
                                'messages': count,
                                'route': name,
                                'iteration': iteration,
                                'total_ms': elapsed,
                                'sql_count': len(sql),
                                'sql_ms': sum(sql),
                                'json_bytes': len(response.content),
                                'gzip_bytes': len(gzip.compress(response.content)),
                            }
                        )
            finally:
                for engine in engines:
                    event.remove(engine, 'before_cursor_execute', before)
                    event.remove(engine, 'after_cursor_execute', after)
        assert len(calls) == 1
    output = ROOT / 'docs/development/assets/workspace-performance-20261112/backend-profile.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Saved {len(report["samples"])} isolated GET measurements')
finally:
    fixture.close()
    scratch.cleanup()
