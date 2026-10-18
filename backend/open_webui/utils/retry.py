"""服务商一时出错时自动重发：限流 429、5xx、连接失败与超时。学生不用自己点重试。

教学的图片识别（services/education/draft_import.py）与作业辅导对话、各平台步骤
（经 routers/openai.py）共用这里的退避：1、2、4 秒，±25% 抖动，最多发 4 次。
只在服务商的响应还没往下游转发之前重发——流式回复已经开始送出的部分不能重来，否则会重复。
"""

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional

import aiohttp

log = logging.getLogger(__name__)

# 请求 metadata 里带这一项为真时才重发；作业辅导对话与平台步骤会带上。
RETRY_TRANSIENT_FLAG = 'retry_transient'

RETRY_DELAYS = (1.0, 2.0, 4.0)
RETRY_JITTER = 0.25
# 过了这么久就不再开始新的一次：学生不该为一条回复干等好几分钟。
RETRY_DEADLINE_SECONDS = 60.0

# 带重发的请求的超时：连上服务商最多等 10 秒；流式回复两段之间最多等 45 秒（含等第一段），
# 不流式的一次性回复（平台步骤，如第一次通读要 20～50 秒）最多等 180 秒。
STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=45)
NON_STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=180)


def is_transient_status(status: Optional[int]) -> bool:
    """429 与 5xx 重发；其余 4xx 是请求本身的问题（参数、鉴权、模型不存在），重发也没用。"""
    return status is not None and (status == 429 or status >= 500)


TRANSIENT_ERRORS = (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, asyncio.TimeoutError)


def retry_delay(attempt: int) -> float:
    return RETRY_DELAYS[attempt] * random.uniform(1 - RETRY_JITTER, 1 + RETRY_JITTER)


async def send_with_retry(
    send: Callable[[], Awaitable[aiohttp.ClientResponse]],
    release: Callable[[aiohttp.ClientResponse], Awaitable[None]],
    *,
    label: str,
) -> aiohttp.ClientResponse:
    """发出请求，状态是 429 / 5xx 或连接、超时出错时按退避重发；返回最后一次的响应或抛出最后的错误。

    只看状态码就决定，响应体还没读、也没往下游转发；重发前用 release 放掉这次的连接。
    """

    started = time.monotonic()
    for attempt in range(len(RETRY_DELAYS) + 1):
        last = attempt == len(RETRY_DELAYS)
        try:
            response = await send()
        except TRANSIENT_ERRORS as error:
            delay = None if last else retry_delay(attempt)
            if delay is None or time.monotonic() - started + delay > RETRY_DEADLINE_SECONDS:
                raise
            log.warning('%s: %s, retrying in %.1fs', label, type(error).__name__, delay)
            await asyncio.sleep(delay)
            continue
        if not is_transient_status(response.status) or last:
            return response
        delay = retry_delay(attempt)
        if time.monotonic() - started + delay > RETRY_DEADLINE_SECONDS:
            return response
        log.warning('%s: status %s, retrying in %.1fs', label, response.status, delay)
        await release(response)
        await asyncio.sleep(delay)
    raise AssertionError('unreachable')
