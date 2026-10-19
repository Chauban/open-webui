"""Shared aiohttp ClientSession pool.

Instead of creating a new ClientSession (and TCPConnector) per request,
callers acquire a long-lived session from this module.  The pool manages
a single TCPConnector with configurable limits, enabling TCP/SSL connection
reuse, shared DNS cache, and bounded concurrency.

All pool parameters are configurable via environment variables:
    - AIOHTTP_POOL_CONNECTIONS (default 100) — max total connections
    - AIOHTTP_POOL_CONNECTIONS_PER_HOST (default 30) — per-host limit
    - AIOHTTP_POOL_DNS_TTL (default 300) — DNS cache TTL in seconds

Usage:
    from open_webui.utils.session_pool import get_session, cleanup_response

    session = await get_session()
    r = await session.request(...)
    # When done with the *response* (not the session):
    await cleanup_response(r)

IMPORTANT: Callers must NOT close the shared session.  Only the response
needs cleanup.  The session is closed once during application shutdown
via ``close_session()``.
"""

import logging
from typing import Optional

import aiohttp
from open_webui.env import (
    AIOHTTP_CLIENT_STREAM_IDLE_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_POOL_CONNECTIONS,
    AIOHTTP_POOL_CONNECTIONS_PER_HOST,
    AIOHTTP_POOL_DNS_TTL,
)
from open_webui.utils.misc import stream_chunks_handler

log = logging.getLogger(__name__)

_session: Optional[aiohttp.ClientSession] = None

_CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
_CLIENT_STREAM_TIMEOUT = aiohttp.ClientTimeout(
    total=AIOHTTP_CLIENT_TIMEOUT,
    sock_read=AIOHTTP_CLIENT_STREAM_IDLE_TIMEOUT,
)


def get_client_timeout(stream: bool = False) -> aiohttp.ClientTimeout:
    return _CLIENT_STREAM_TIMEOUT if stream else _CLIENT_TIMEOUT


async def get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp ClientSession, creating it lazily."""
    global _session
    if _session is None or _session.closed:
        connector_kwargs = {
            'ttl_dns_cache': AIOHTTP_POOL_DNS_TTL,
            'enable_cleanup_closed': True,
        }
        if AIOHTTP_POOL_CONNECTIONS is not None:
            connector_kwargs['limit'] = AIOHTTP_POOL_CONNECTIONS
        else:
            connector_kwargs['limit'] = 0  # aiohttp: 0 = unlimited
        if AIOHTTP_POOL_CONNECTIONS_PER_HOST is not None:
            connector_kwargs['limit_per_host'] = AIOHTTP_POOL_CONNECTIONS_PER_HOST
        else:
            connector_kwargs['limit_per_host'] = 0  # aiohttp: 0 = unlimited
        connector = aiohttp.TCPConnector(**connector_kwargs)
        timeout = get_client_timeout()
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=True,
        )
        log.info(
            'Created shared aiohttp session pool (limit=%s, per_host=%s, dns_ttl=%d)',
            AIOHTTP_POOL_CONNECTIONS or 'unlimited',
            AIOHTTP_POOL_CONNECTIONS_PER_HOST or 'unlimited',
            AIOHTTP_POOL_DNS_TTL,
        )
    return _session


async def close_session():
    """Close the shared session.  Called during application shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        log.info('Closed shared aiohttp session pool')
        _session = None


async def cleanup_response(
    response: Optional[aiohttp.ClientResponse],
    session: Optional[aiohttp.ClientSession] = None,
):
    """Release and close an aiohttp response, optionally closing the session.

    When using the shared pool, ``session`` should be ``None`` (the pool
    session is never closed per-request).  When a caller creates its own
    one-off session, pass it here to close it after the response.
    """
    if response:
        if not response.closed:
            # aiohttp 3.9+ made ClientResponse.close() synchronous (returns None).
            # Older versions returned a coroutine.  Handle both gracefully.
            result = response.close()
            if result is not None:
                await result
    if session:
        if not session.closed:
            result = session.close()
            if result is not None:
                await result


class _PrefixedContent:
    """A response body that yields ``head`` (already read off the stream) before the rest."""

    def __init__(self, head: bytes, content: aiohttp.StreamReader):
        self.head = head
        self.content = content

    async def iter_any(self):
        yield self.head
        async for data in self.content.iter_any():
            yield data

    async def iter_chunks(self):
        yield self.head, False
        async for item in self.content.iter_chunks():
            yield item


async def stream_wrapper(response, session=None, passthrough=False, head=b''):
    """Wrap a stream to ensure cleanup happens even if streaming is interrupted.

    This is more reliable than BackgroundTask which may not run if the client
    disconnects.  When using the shared pool, ``session`` should be ``None``.

    ``passthrough=True`` yields raw network chunks (iter_any) instead of
    lines: byte-identical output without a buffer scan, slice and copy per
    line. Only for streams no internal consumer parses line-by-line.

    ``head`` is the start of the body the caller already read off the stream
    (see ``utils.retry.read_ahead``); it is sent first.
    """
    try:
        content = _PrefixedContent(head, response.content) if head else response.content
        if passthrough:
            stream = content.iter_any()
        else:
            stream = stream_chunks_handler(content)
        async for chunk in stream:
            yield chunk
    finally:
        await cleanup_response(response, session)
