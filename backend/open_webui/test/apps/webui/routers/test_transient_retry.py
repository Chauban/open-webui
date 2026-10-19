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
from open_webui.utils.retry import (
    ONE_SHOT_RETRY,
    RETRY_DELAYS,
    RETRY_JITTER,
    RETRY_TRANSIENT_FLAG,
    STREAM_RETRY,
    send_with_retry,
)
from open_webui.utils.session_pool import stream_wrapper

DEADLINE = 60.0


class FakeContent:
    """流式响应体:chunks 依次给出;某一段是错误时在读到那里抛出(如等第一段超时)。"""

    def __init__(self, chunks):
        self.chunks = list(chunks)

    async def readchunk(self):
        if not self.chunks:
            return b'', False
        chunk = self.chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk, False

    async def iter_chunks(self):
        while self.chunks:
            yield await self.readchunk()


class FakeResponse:
    def __init__(self, status, body=None, sse=False, chunks=(b'data: {}\n\n',), read_error=None):
        self.status = status
        self._body = body if body is not None else {'error': {'message': f'status {status}'}}
        self.headers = {'Content-Type': 'text/event-stream' if sse else 'application/json'}
        self.content = FakeContent(chunks)
        self.read_error = read_error
        self.closed = True

    async def read(self):
        if self.read_error:
            raise self.read_error
        return json.dumps(self._body).encode()

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

    response = asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE))

    assert response.status == 200 and calls['sent'] == 3
    assert calls['released'] == [429, 503]
    for delay, base in zip(no_sleep, RETRY_DELAYS):
        assert base * (1 - RETRY_JITTER) <= delay <= base * (1 + RETRY_JITTER)


@pytest.mark.parametrize('status', [400, 401, 403, 404, 408, 422])
def test_other_client_errors_are_not_retried(no_sleep, status):
    send, release, calls = _script([FakeResponse(status)])

    assert asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE)).status == status
    assert calls['sent'] == 1 and no_sleep == []


def test_gives_up_after_four_attempts(no_sleep):
    send, release, calls = _script([FakeResponse(502)] * 4)

    assert asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE)).status == 502
    assert calls['sent'] == 4 and len(no_sleep) == 3
    # 最后一次的响应原样交回,由调用方当错误处理,不放掉
    assert calls['released'] == [502, 502, 502]


def test_retries_connection_errors_and_timeouts(no_sleep):
    send, release, calls = _script(
        [aiohttp.ClientConnectionError(), asyncio.TimeoutError(), aiohttp.ServerTimeoutError(), FakeResponse(200)]
    )
    assert asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE)).status == 200
    assert calls['sent'] == 4

    send, release, calls = _script([asyncio.TimeoutError()] * 4)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE))
    assert calls['sent'] == 4


def test_stops_retrying_past_the_deadline(no_sleep, monkeypatch):
    """已经等了很久时不再开始新的一次,学生不该为一条回复干等好几分钟。"""
    clock = iter([0.0, DEADLINE - 0.5])
    # 只换掉重发模块看到的时钟;asyncio 自己的事件循环也读 time.monotonic,不能全局替换
    monkeypatch.setattr(retry_module, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    send, release, calls = _script([asyncio.TimeoutError(), FakeResponse(200)])

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(send_with_retry(send, release, label='t', deadline=DEADLINE))
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

    def fake_stream_wrapper(response, head=b''):
        HEADS.append(head)
        return iter([head])

    HEADS.clear()
    monkeypatch.setattr(openai_router, 'stream_wrapper', fake_stream_wrapper)
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
# 路由交给 stream_wrapper 先送出的第一段
HEADS = []


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


@pytest.mark.parametrize('budget', [STREAM_RETRY, ONE_SHOT_RETRY], ids=['stream', 'one-shot'])
def test_a_timeout_still_leaves_room_for_one_more_attempt(no_sleep, monkeypatch, budget):
    """读超时要等满 sock_read;deadline 留得下再发一次,第二次也超时就报错,不再等第三次。"""
    read = budget.timeout.sock_read
    clock = iter([0.0, read, 2 * read + 1])
    monkeypatch.setattr(retry_module, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    send, release, calls = _script([asyncio.TimeoutError()] * 4)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(send_with_retry(send, release, label='t', deadline=budget.deadline))
    assert calls['sent'] == 2 and len(no_sleep) == 1


def test_budgets():
    assert (STREAM_RETRY.timeout.sock_connect, STREAM_RETRY.timeout.sock_read, STREAM_RETRY.deadline) == (10, 45, 60)
    assert (ONE_SHOT_RETRY.timeout.sock_connect, ONE_SHOT_RETRY.timeout.sock_read, ONE_SHOT_RETRY.deadline) == (
        10,
        90,
        120,
    )
    for budget in (STREAM_RETRY, ONE_SHOT_RETRY):
        assert budget.timeout.total is None
        assert budget.deadline > budget.timeout.sock_read + RETRY_DELAYS[0] * (1 + RETRY_JITTER)


def test_one_shot_body_timeout_is_retried(monkeypatch):
    """平台步骤:状态行到了、响应体迟迟不来而超时,也重发。"""
    result, sent = _router(
        monkeypatch,
        [FakeResponse(200, OK, read_error=aiohttp.ServerTimeoutError()), FakeResponse(200, OK)],
        {RETRY_TRANSIENT_FLAG: True},
    )
    assert result == OK and sent == 2


def test_stream_first_chunk_timeout_is_retried_and_the_chunk_goes_first(monkeypatch):
    """辅导对话:迟迟等不到第一段而超时,也重发;重发拿到的第一段原样排在最前送出。"""
    result, sent = _router(
        monkeypatch,
        [
            FakeResponse(200, sse=True, chunks=[aiohttp.ServerTimeoutError()]),
            FakeResponse(200, sse=True, chunks=[b'data: first\n\n']),
        ],
        {RETRY_TRANSIENT_FLAG: True},
        stream=True,
    )
    assert isinstance(result, StreamingResponse) and sent == 2
    assert HEADS == [b'data: first\n\n']


def test_stream_wrapper_sends_the_head_first_then_the_rest():
    response = FakeResponse(200, sse=True, chunks=[b'data: b\n', b'\ndata: c\n\n'])

    async def collect():
        return [line async for line in stream_wrapper(response, head=b'data: a\n\n')]

    assert asyncio.run(collect()) == [b'data: a\n', b'\n', b'data: b\n', b'\n', b'data: c\n', b'\n']


def test_stream_that_breaks_after_it_started_is_not_retried(monkeypatch):
    """第一段已经拿到(就要送给学生),之后才断:不重发,免得学生看到重复的内容。"""
    result, sent = _router(
        monkeypatch,
        [
            FakeResponse(200, sse=True, chunks=[b'data: first\n\n', aiohttp.ClientPayloadError()]),
            FakeResponse(200, sse=True),
        ],
        {RETRY_TRANSIENT_FLAG: True},
        stream=True,
    )
    assert isinstance(result, StreamingResponse) and sent == 1


def test_flagged_requests_get_the_retry_timeouts(monkeypatch):
    seen = []

    class RecordingSession:
        async def request(self, **kwargs):
            seen.append(kwargs['timeout'])
            return FakeResponse(200, OK, sse=len(seen) == 1)

    async def fake_session():
        return RecordingSession()

    _router(monkeypatch, [FakeResponse(200, OK)], {RETRY_TRANSIENT_FLAG: True})
    monkeypatch.setattr(openai_router, 'get_session', fake_session)
    for stream in (True, False):
        asyncio.run(
            openai_router.generate_chat_completion(
                SimpleNamespace(
                    app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={'deepseek-flash': {'urlIdx': 0}})),
                    state=SimpleNamespace(),
                ),
                {
                    'model': 'deepseek-flash',
                    'messages': [{'role': 'user', 'content': 'hi'}],
                    'stream': stream,
                    'metadata': {RETRY_TRANSIENT_FLAG: True},
                },
                SimpleNamespace(id='u-1', name='U', email='u@example.com', role='user'),
            )
        )
    assert seen == [STREAM_RETRY.timeout, ONE_SHOT_RETRY.timeout]
