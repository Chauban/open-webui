import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.test.apps.webui.routers.test_education_smoke import education_client, UserContext
from open_webui.test.apps.webui.routers.test_revision_coaching import setup, submit


@pytest.mark.parametrize('preset', [True, False])
def test_teacher_sees_frozen_review_action_and_reading_source(education_client, preset):
    client, teacher, _, student, _, factory = education_client
    assignment, sid, _ = setup(client, teacher, student, scoring='total')
    stamp = int(time.time())
    user_message = {
        'id': 'question',
        'role': 'user',
        'content': '请看修改' if preset else '我修改了证据范围，请看看',
        'timestamp': stamp,
        'parentId': None,
        'childrenIds': ['reply'],
        'meta': {'revision_review_requested': True, 'auto_started': preset},
    }
    reply = {
        'id': 'reply',
        'role': 'assistant',
        'content': '这次缩小了范围',
        'timestamp': stamp,
        'parentId': 'question',
        'childrenIds': [],
        'done': True,
        'meta': {
            'education_context': {
                'source_text': 'AI 当时读过的稿件',
                'called_at': stamp,
                'description_version': 1,
                'teaching_version': 1,
            }
        },
    }
    for message in [user_message, reply]:
        result = client.post(f'/api/v1/writing-sessions/{sid}/chat/messages/{message["id"]}', json={'message': message})
        assert result.status_code == 200, result.text
    result = submit(client, assignment, sid)
    assert result.status_code == 200, result.text
    submission_id = result.json()['submission_id']
    # Later live edits cannot change the teacher's frozen evidence.
    user_message['meta']['revision_review_requested'] = False
    reply['meta']['education_context']['source_text'] = '后来改写的稿件'
    for message in [user_message, reply]:
        assert (
            client.post(
                f'/api/v1/writing-sessions/{sid}/chat/messages/{message["id"]}', json={'message': message}
            ).status_code
            == 200
        )
    UserContext.current_user = teacher
    response = client.get(f'/api/v1/teacher/submissions/{submission_id}')
    assert response.status_code == 200, response.text
    detail = response.json()
    question = next(item for item in detail['prompt_timeline'] if item['role'] == 'user')
    assert question['revision_review_requested'] is True
    assert question['auto_started'] is preset
    assert detail['round_prompt_count'] == (0 if preset else 1)
    contexts = detail['submission']['stats_json']['chat_contexts']
    assert contexts[0]['source_text'] == 'AI 当时读过的稿件'
