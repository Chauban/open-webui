"""Observe provider calls without changing their retry, cancellation or stream semantics."""

import asyncio
import codecs
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

import aiohttp
import anyio
from open_webui.internal.db import get_async_db
from open_webui.models.model_calls import ModelCall, ModelCallAttempt
from sqlalchemy import delete, select
from starlette.responses import StreamingResponse

log = logging.getLogger(__name__)
_last_cleanup = 0.0
RETENTION_DAYS = 30
current_call = ContextVar('model_health_call', default=None)


@asynccontextmanager
async def model_call_scope(model_id, user_id):
    """Group page-level image retries into a single logical provider call."""
    recorder = ModelCallRecorder(model_id, user_id)
    token = current_call.set(recorder)
    reason = None
    try:
        yield recorder
    except BaseException as error:
        reason = error_reason(error)
        if recorder.attempts and reason != 'cancelled':
            reason = recorder.attempts[-1].data['reason'] or reason
        raise
    finally:
        current_call.reset(token)
        await recorder.finish(reason)


def error_reason(error=None, status=None):
    if isinstance(error, (asyncio.CancelledError, GeneratorExit)):
        return 'cancelled'
    if isinstance(error, TimeoutError) or status in (408, 504):
        return 'timeout'
    if isinstance(error, aiohttp.ClientConnectionError):
        return 'connection'
    if isinstance(error, aiohttp.ClientPayloadError):
        return 'interrupted'
    if status in (401, 403):
        return 'authentication'
    if status == 429:
        return 'rate_limit'
    if status and status >= 500:
        return 'provider'
    if status and status >= 400:
        return 'request'
    return 'invalid_response'


def route_label(url, index):
    # Host and a fingerprint distinguish routes, including different paths on one host.
    # The path, userinfo, query, fragment, headers and key are never persisted.
    parsed = urlsplit(url)
    identity = f'{parsed.scheme}://{parsed.hostname}:{parsed.port}{parsed.path}'
    digest = hashlib.sha256(identity.encode()).hexdigest()[:8]
    return f'{parsed.hostname or "unknown"} · {index + 1} · {digest}'


async def save_call(call, attempts):
    global _last_cleanup
    async with get_async_db() as db:
        db.add(ModelCall(**call))
        await db.flush()
        db.add_all([ModelCallAttempt(**attempt) for attempt in attempts])
        cleanup_due = time.monotonic() - _last_cleanup > 3600
        if cleanup_due:
            cutoff = int(time.time()) - RETENTION_DAYS * 86400
            old = ModelCall.started_at < cutoff
            await db.execute(
                delete(ModelCallAttempt).where(ModelCallAttempt.call_id.in_(select(ModelCall.id).where(old)))
            )
            await db.execute(delete(ModelCall).where(old))
        await db.commit()
        if cleanup_due:
            _last_cleanup = time.monotonic()


class Attempt:
    def __init__(self, call_id, model_id, route, fallback):
        self.started = time.monotonic()
        self.data = dict(
            id=str(uuid.uuid4()),
            call_id=call_id,
            model_id=model_id,
            route=route,
            started_at=int(time.time()),
            duration_ms=0,
            outcome='success',
            reason=None,
            http_status=None,
            fallback=fallback,
        )
        self.finished = False

    def finish(self, reason=None, status=None):
        if self.finished:
            return
        self.finished = True
        self.data.update(
            duration_ms=int((time.monotonic() - self.started) * 1000),
            reason=reason,
            outcome='cancelled' if reason == 'cancelled' else 'failed' if reason else 'success',
        )
        if status is not None:
            self.data['http_status'] = status


class StreamOutcome:
    """Inspect bounded SSE framing in memory, forwarding the original bytes unchanged."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.buffer = ''
        self.complete = False
        self.failed = False

    def feed(self, chunk):
        self.buffer += self.decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                self.complete = True
                continue
            try:
                value = json.loads(data)
            except (ValueError, TypeError):
                continue
            if not isinstance(value, dict):
                continue
            if value.get('error') or value.get('type') in ('error', 'response.failed', 'response.incomplete'):
                self.failed = True
            choices = value.get('choices')
            if value.get('type') == 'response.completed' or (
                isinstance(choices, list)
                and any(isinstance(choice, dict) and choice.get('finish_reason') is not None for choice in choices)
            ):
                self.complete = True
        # Unusually large data frames are skipped, never retained as diagnostics.
        if len(self.buffer) > 65536:
            self.buffer = ''


class ModelCallRecorder:
    def __init__(self, model_id, user_id):
        self.started = time.monotonic()
        self.call = dict(
            id=str(uuid.uuid4()),
            model_id=model_id,
            user_id=user_id,
            started_at=int(time.time()),
            duration_ms=0,
            outcome='success',
            fallback_used=False,
        )
        self.attempts = []
        self.saved = False

    def begin(self, model_id, url, index, fallback=False):
        attempt = Attempt(self.call['id'], model_id, route_label(url, index), fallback)
        self.attempts.append(attempt)
        self.call['fallback_used'] |= fallback
        return attempt

    async def finish(self, reason=None):
        if self.saved or not self.attempts:
            return
        self.saved = True
        latest = self.attempts[-1]
        latest.finish(reason)
        self.call.update(
            outcome='cancelled' if reason == 'cancelled' else 'failed' if reason else 'success',
            duration_ms=int((time.monotonic() - self.started) * 1000),
        )
        try:
            # A short, independent transaction; never keep a DB connection during inference.
            with anyio.CancelScope(shield=True):
                async with asyncio.timeout(2):
                    await save_call(self.call, [a.data for a in self.attempts])
        except Exception as error:
            # Diagnostics must not turn an otherwise successful model request into an error.
            log.warning('Model health recording failed (%s)', type(error).__name__)

    async def observe(self, response, *, finalize=True):
        status = getattr(response, 'status_code', 200)
        if isinstance(response, StreamingResponse) and status < 400:
            original = response.body_iterator

            async def stream():
                outcome = StreamOutcome()
                reason = 'cancelled'
                try:
                    async for chunk in original:
                        outcome.feed(chunk)
                        yield chunk
                    outcome.feed('\n')
                    reason = 'provider' if outcome.failed else None if outcome.complete else 'interrupted'
                except BaseException as error:
                    reason = error_reason(error)
                    raise
                finally:
                    try:
                        if hasattr(original, 'aclose'):
                            await original.aclose()
                    finally:
                        await self.finish(reason)

            response.body_iterator = stream()
            return response
        reason = error_reason(status=status) if status >= 400 else None
        if status < 400 and (not isinstance(response, dict) or response.get('error') or not response.get('choices')):
            reason = 'invalid_response'
        if finalize:
            await self.finish(reason)
        elif self.attempts:
            self.attempts[-1].finish(reason)
        return response
