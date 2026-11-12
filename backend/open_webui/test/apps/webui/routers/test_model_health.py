import asyncio
import copy
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from open_webui.internal import db as internal_db
from open_webui.routers import analytics, openai
from open_webui.services.model_health import model_health_failures, model_health_summary
from open_webui.test.apps.webui.routers.test_model_fallback import routing as base_routing
from open_webui.test.apps.webui.routers.test_transient_retry import OK, FakeResponse, _router
from open_webui.test.util.database import migrated_database
from open_webui.utils import model_health as health
from open_webui.utils.auth import get_current_user

routing = base_routing


@pytest.fixture
def records(monkeypatch):
    rows = []

    async def save(call, attempts):
        rows.append(copy.deepcopy((call, attempts)))

    monkeypatch.setattr(health, 'save_call', save)
    return rows


def test_retry_success_counted_once_with_two_failed_attempts(monkeypatch, records):
    result, sent = _router(
        monkeypatch, [FakeResponse(429), TimeoutError(), FakeResponse(200, OK)], {'retry_transient': True}
    )
    assert result == OK and sent == 3
    call, attempts = records[0]
    assert len(records) == 1 and call['outcome'] == 'success'
    assert [a['reason'] for a in attempts] == ['rate_limit', 'timeout', None]
    assert [a['outcome'] for a in attempts] == ['failed', 'failed', 'success']
    assert all(a['duration_ms'] >= 0 for a in attempts)


def test_fallback_groups_both_routes(routing, records):
    routing.outcomes[:] = [TimeoutError(), FakeResponse(200, OK)]
    assert asyncio.run(openai.generate_chat_completion(routing.request, routing.body, routing.user)) == OK
    call, attempts = records[0]
    assert call['model_id'] == 'primary' and call['fallback_used'] and call['outcome'] == 'success'
    assert [a['model_id'] for a in attempts] == ['primary', 'google/backup']
    assert attempts[0]['route'] != attempts[1]['route']
    assert 'Read my draft' not in str(records) and 'key-' not in str(records)


def test_final_timeout_preserves_reason(monkeypatch, records):
    result, _ = _router(monkeypatch, [TimeoutError()], None)
    assert isinstance(result, HTTPException)
    assert records[0][0]['outcome'] == 'failed'
    assert records[0][1][0]['reason'] == 'timeout'


def test_non_retry_body_timeout_is_not_reported_as_generic_500(monkeypatch, records):
    response = FakeResponse(200, OK)

    async def timeout(*args, **kwargs):
        raise TimeoutError()

    response.json = timeout
    response.text = timeout
    result, _ = _router(monkeypatch, [response], None)
    assert isinstance(result, HTTPException)
    assert records[0][1][0]['reason'] == 'timeout'


@pytest.mark.parametrize(
    'chunks,expected',
    [
        ([b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n', b'data: [DONE]\n\n'], 'success'),
        ([b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'], 'failed'),
        ([b'data: {"error":{"message":"secret"}}\n\n', b'data: [DONE]\n\n'], 'failed'),
        ([b'data: {"type":"response.completed"}\n\n'], 'success'),
        ([b'data: {"choices":null}\n\n', b'data: [DONE]'], 'success'),
    ],
)
def test_stream_results_wait_for_end_and_preserve_bytes(records, chunks, expected):
    async def run():
        recorder = health.ModelCallRecorder('m', 'u')
        recorder.begin('m', 'https://provider.test/v1', 0)

        async def body():
            for chunk in chunks:
                yield chunk

        response = await recorder.observe(StreamingResponse(body()))
        assert not records
        assert [chunk async for chunk in response.body_iterator] == chunks

    asyncio.run(run())
    assert records[0][0]['outcome'] == expected
    assert 'secret' not in str(records)


def test_cancelled_stream_closes_upstream_and_is_not_failure(records):
    closed = []

    async def run():
        recorder = health.ModelCallRecorder('m', 'u')
        recorder.begin('m', 'https://provider.test/v1', 0)

        async def body():
            try:
                yield b'data: {}\n\n'
                raise asyncio.CancelledError()
            finally:
                closed.append(True)

        response = await recorder.observe(StreamingResponse(body()))
        with pytest.raises(asyncio.CancelledError):
            async for _ in response.body_iterator:
                pass

    asyncio.run(run())
    assert closed and records[0][0]['outcome'] == 'cancelled'
    assert records[0][1][0]['outcome'] == 'cancelled'


def test_image_scope_groups_page_retries_and_is_task_local(records):
    async def page(index):
        async with health.model_call_scope('vision', str(index)) as recorder:
            recorder.begin('vision', 'https://vision.test/v1', 0).finish('timeout')
            await asyncio.sleep(0)
            assert health.current_call.get() is recorder
            recorder.begin('vision', 'https://vision.test/v1', 0)
            await recorder.observe(OK, finalize=False)

    async def run():
        await asyncio.gather(page(1), page(2))
        assert health.current_call.get() is None

    asyncio.run(run())
    assert len(records) == 2
    assert all(c['outcome'] == 'success' and len(a) == 2 for c, a in records)


def test_route_redacts_credentials_and_distinguishes_paths():
    route = health.route_label('https://user:password@provider.test/private?key=secret#token', 1)
    assert all(value not in route for value in ('password', 'private', 'secret', 'token', 'user'))
    assert route != health.route_label('https://provider.test/other', 1)


def test_storage_error_does_not_break_response(monkeypatch):
    async def broken(*args):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(health, 'save_call', broken)

    async def run():
        recorder = health.ModelCallRecorder('m', 'u')
        recorder.begin('m', 'https://provider.test', 0)
        assert await recorder.observe(OK) == OK

    asyncio.run(run())


@pytest.fixture
def database(monkeypatch):
    with migrated_database() as url:
        engine = create_async_engine(internal_db._make_async_url(url), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(internal_db, 'AsyncSessionLocal', factory)
        yield factory
        asyncio.run(engine.dispose())


def test_migration_storage_aggregates_filters_and_pagination(database):
    async def run():
        for index, reason in enumerate((None, 'timeout', 'cancelled')):
            recorder = health.ModelCallRecorder('m', 'u')
            recorder.begin('m', 'https://provider.test', 0)
            await recorder.finish(reason)
        recovered = health.ModelCallRecorder('m', 'u2')
        recovered.begin('m', 'https://provider.test', 0).finish('rate_limit', 429)
        recovered.begin('backup', 'https://backup.test', 1, True)
        await recovered.finish()
        async with database() as db:
            end = int(time.time()) + 1
            models = await model_health_summary(db, end - 100, end)
            model = models[0]
            assert model['calls'] == 4 and model['successes'] == 2 and model['failures'] == 1
            assert model['cancelled'] == 1 and model['affected_users'] == 1
            assert model['failure_rate'] == pytest.approx(1 / 3)
            assert model['attempts'] == 5 and model['attempt_failure_rate'] == 0.5
            assert model['fallback_successes'] == model['fallback_calls'] == 1
            assert model['reasons'] == {'timeout': 1, 'rate_limit': 1}
            first = await model_health_failures(db, end - 100, end, 'm', 0, 1)
            second = await model_health_failures(db, end - 100, end, 'm', 1, 1)
            assert first['total'] == 2 and first['items'][0]['id'] != second['items'][0]['id']
            assert not (await model_health_failures(db, end - 100, end, 'other', 0, 25))['items']
            assert not await model_health_summary(db, end + 1, end + 100)

    asyncio.run(run())


def test_retention_removes_expired_calls_and_attempts(database, monkeypatch):
    async def run():
        old = health.ModelCallRecorder('old', 'u')
        old.call['started_at'] -= 31 * 86400
        old.begin('old', 'https://provider.test', 0)
        monkeypatch.setattr(health, '_last_cleanup', time.monotonic())
        await old.finish('timeout')
        monkeypatch.setattr(health, '_last_cleanup', 0)
        fresh = health.ModelCallRecorder('fresh', 'u')
        fresh.begin('fresh', 'https://provider.test', 0)
        await fresh.finish()
        async with database() as db:
            assert [m['model_id'] for m in await model_health_summary(db, 0, int(time.time()) + 1)] == ['fresh']
            assert not (await model_health_failures(db, 0, int(time.time()) + 1, None, 0, 25))['items']

    asyncio.run(run())


def test_admin_only_and_query_validation(database):
    app = FastAPI()
    app.include_router(analytics.router)
    user = SimpleNamespace(role='user')
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        for path in ('/model-health', '/model-health/failures'):
            assert client.get(path).status_code == 401
        user.role = 'admin'
        assert client.get('/model-health').status_code == 200
        assert client.get('/model-health?period=all').status_code == 422
        assert client.get('/model-health/failures?limit=1000').status_code == 422
