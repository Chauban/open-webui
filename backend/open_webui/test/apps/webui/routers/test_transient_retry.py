"""服务商一时出错时自动重发：429 / 5xx / 连接与超时；其余 4xx 不重发；只在往下游送内容之前。"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse, StreamingResponse

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import open_webui.routers.openai as openai_router
import open_webui.utils.retry as retry_module
from open_webui.utils.retry import RETRY_DELAYS, RETRY_JITTER, RETRY_TRANSIENT_FLAG, send_with_retry


class FakeResponse:
    def __init__(self, status, body=None, sse=False):
        self.status = status
        self._body = body if body is not None else {'error': {'message': f'status {status}'}}
        self.headers = {'Content-Type': 'text/event-stream' if sse else 'application/json'}
        self.content = SimpleNamespace()

    async def json(self, loads=json.loads):
        return self._body

    async def text(self):
        return json.dumps(self._body)


def _script(outcomes):
    """依次返回给定的响应或抛出给定的错误；记下发了几次、放掉了哪几个响应、每次等了多久。"""
    calls = {'sent': 0, 'released': [], 'slept': []}

    async def send():
        outcome = outcomes[calls['sent']]
        calls['sent'] += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def release(response):
        calls['released'].append(response.status)

    return send, release, calls


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(retry_module.asyncio, 'sleep', fake_sleep)
    return slept


def test_retries_rate_limits_and_server_errors_with_backoff(no_sleep):
    send, release, calls = _script([FakeResponse(429), FakeResponse(503), FakeResponse(200)])

    response = asyncio.run(send_with_retry(send, release, label='t'))

    assert response.status == 200 and calls['sent'] == 3
    assert calls['released'] == [429, 503]
    for delay, base in zip(no_sleep, RETRY_DELAYS):
        assert base * (1 - RETRY_JITTER) <= delay <= base * (1 + RETRY_JITTER)


@pytest.mark.parametrize('status', [400, 401, 403, 404, 408, 422])
def test_other_client_errors_are_not_retried(no_sleep, status):
    send, release, calls = _script([FakeResponse(status)])

    assert asyncio.run(send_with_retry(send, release, label='t')).status == status
    assert calls['sent'] == 1 and no_sleep == []


def test_gives_up_after_four_attempts(no_sleep):
    send, release, calls = _script([FakeResponse(502)] * 4)

    assert asyncio.run(send_with_retry(send, release, label='t')).status == 502
    assert calls['sent'] == 4 and len(no_sleep) == 3
    # 最后一次的响应原样交回,由调用方当错误处理,不放掉
    assert calls['released'] == [502, 502, 502]


def test_retries_connection_errors_and_timeouts(no_sleep):
    send, release, calls = _script(
        [aiohttp.ClientConnectionError(), asyncio.TimeoutError(), aiohttp.ServerTimeoutError(), FakeResponse(200)]
    )
    assert asyncio.run(send_with_retry(send, release, label='t')).status == 200
    assert calls['sent'] == 4

    send, release, calls = _script([asyncio.TimeoutError()] * 4)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(send_with_retry(send, release, label='t'))
    assert calls['sent'] == 4


def test_stops_retrying_past_the_deadline(no_sleep, monkeypatch):
    """一次读超时就等了很久时不再开始新的一次,学生不该为一条回复干等好几分钟。"""
    clock = iter([0.0, 59.5])
    # 只换掉重发模块看到的时钟;asyncio 自己的事件循环也读 time.monotonic,不能全局替换
    monkeypatch.setattr(retry_module, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    send, release, calls = _script([asyncio.TimeoutError(), FakeResponse(200)])

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(send_with_retry(send, release, label='t'))
    assert calls['sent'] == 1


def _router(monkeypatch, outcomes, metadata, stream=False):
    """跑一遍 OpenAI 兼容路由,服务商依次给出 outcomes;返回路由的结果与发出的次数。"""
    sent = {'count': 0}

    class FakeSession:
        async def request(self, **kwargs):
            outcome = outcomes[sent['count']]
            sent['count'] += 1
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    async def fake_session():
        return FakeSession()

    async def config_get(key, default=None):
        return True

    async def no_model(model_id):
        return None

    async def nothing(*args, **kwargs):
        return None

    async def connection(idx):
        return 'https://api.deepseek.com', 'key', {}

    async def headers_and_cookies(*args, **kwargs):
        return {}, {}

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(openai_router, 'Config', SimpleNamespace(get=config_get))
    monkeypatch.setattr(openai_router.Models, 'get_model_by_id', no_model)
    monkeypatch.setattr(openai_router, 'check_model_access', nothing)
    monkeypatch.setattr(openai_router, 'get_openai_connection', connection)
    monkeypatch.setattr(openai_router, 'get_headers_and_cookies', headers_and_cookies)
    monkeypatch.setattr(openai_router, 'get_session', fake_session)
    monkeypatch.setattr(openai_router, 'cleanup_response', nothing)
    monkeypatch.setattr(openai_router, 'publish_model_provider_request_failed', nothing)
    monkeypatch.setattr(openai_router, 'stream_wrapper', lambda response: iter([b'data: {}\n\n']))
    monkeypatch.setattr(retry_module.asyncio, 'sleep', fake_sleep)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={'deepseek-flash': {'urlIdx': 0}})),
        state=SimpleNamespace(),
    )
    body = {
        'model': 'deepseek-flash',
        'messages': [{'role': 'user', 'content': 'hi'}],
        'stream': stream,
        **({'metadata': metadata} if metadata is not None else {}),
    }
    user = SimpleNamespace(id='u-1', name='U', email='u@example.com', role='user')
    try:
        result = asyncio.run(openai_router.generate_chat_completion(request, body, user))
    except HTTPException as error:
        result = error
    return result, sent['count']


OK = {'choices': [{'message': {'content': '2'}}]}


def test_coaching_requests_recover_from_transient_failures(monkeypatch):
    result, sent = _router(
        monkeypatch,
        [FakeResponse(429), aiohttp.ClientConnectionError(), FakeResponse(200, OK)],
        {RETRY_TRANSIENT_FLAG: True},
    )
    assert result == OK and sent == 3


def test_streamed_reply_is_retried_only_before_it_starts(monkeypatch):
    result, sent = _router(
        monkeypatch,
        [FakeResponse(502), FakeResponse(200, sse=True)],
        {RETRY_TRANSIENT_FLAG: True},
        stream=True,
    )
    assert isinstance(result, StreamingResponse) and result.status_code == 200 and sent == 2


def test_other_requests_are_sent_once(monkeypatch):
    for metadata in (None, {RETRY_TRANSIENT_FLAG: False}):
        result, sent = _router(monkeypatch, [FakeResponse(503), FakeResponse(200, OK)], metadata)
        assert isinstance(result, JSONResponse) and result.status_code == 503 and sent == 1


def test_flagged_requests_get_a_bounded_read_timeout(monkeypatch):
    seen = []

    class RecordingSession:
        async def request(self, **kwargs):
            seen.append(kwargs['timeout'])
            return FakeResponse(200, OK)

    async def fake_session():
        return RecordingSession()

    _router(monkeypatch, [FakeResponse(200, OK)], {RETRY_TRANSIENT_FLAG: True})
    monkeypatch.setattr(openai_router, 'get_session', fake_session)
    for stream, metadata in ((True, {RETRY_TRANSIENT_FLAG: True}), (False, {RETRY_TRANSIENT_FLAG: True})):
        body_stream = stream
        asyncio.run(
            openai_router.generate_chat_completion(
                SimpleNamespace(
                    app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={'deepseek-flash': {'urlIdx': 0}})),
                    state=SimpleNamespace(),
                ),
                {
                    'model': 'deepseek-flash',
                    'messages': [{'role': 'user', 'content': 'hi'}],
                    'stream': body_stream,
                    'metadata': metadata,
                },
                SimpleNamespace(id='u-1', name='U', email='u@example.com', role='user'),
            )
        )
    assert seen == [retry_module.STREAM_TIMEOUT, retry_module.NON_STREAM_TIMEOUT]
    assert seen[0].sock_read == 45 and seen[1].sock_read == 180
