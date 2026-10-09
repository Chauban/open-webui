#!/usr/bin/env python3
"""OpenAI 兼容的假模型端点，专供压测使用。

只依赖标准库，直接 `python3 mock_llm.py` 就能跑。它按固定节奏吐 SSE token，
让压测能压到真实的流式转发路径（worker 占用、Postgres 写入、Socket.IO 广播），
而不花一分钱模型费、也不会被上游限流干扰结论。

环境变量：
    MOCK_PORT       监听端口，默认 9099
    MOCK_MODEL_ID   对外暴露的模型 id，默认 loadtest-mock
    MOCK_TTFT_MS    首 token 延迟（毫秒），默认 600
    MOCK_TOKENS     每次回复吐多少个 token，默认 400
    MOCK_TPS        每秒吐几个 token，默认 25（即 400/25 = 16 秒一次回复）
    MOCK_API_KEY    非空时校验 Authorization: Bearer，默认不校验
"""

import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get('MOCK_PORT', '9099'))
MODEL_ID = os.environ.get('MOCK_MODEL_ID', 'loadtest-mock')
TTFT_MS = int(os.environ.get('MOCK_TTFT_MS', '600'))
TOKENS = int(os.environ.get('MOCK_TOKENS', '400'))
TPS = float(os.environ.get('MOCK_TPS', '25'))
API_KEY = os.environ.get('MOCK_API_KEY', '')

WORD = '这是一段用于压力测试的占位文本，它不代表任何真实的模型输出。'
INTERVAL = 1.0 / TPS if TPS > 0 else 0.0


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    # --- 工具 ---

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chunk(self, data: bytes):
        self.wfile.write(('%X\r\n' % len(data)).encode())
        self.wfile.write(data)
        self.wfile.write(b'\r\n')
        self.wfile.flush()

    def _authorized(self):
        if not API_KEY:
            return True
        return self.headers.get('Authorization', '') == 'Bearer ' + API_KEY

    # --- 路由 ---

    def do_GET(self):
        path = self.path.split('?', 1)[0].rstrip('/')
        if path.endswith('/health'):
            self._json({'status': True, 'model': MODEL_ID})
            return
        if path.endswith('/models'):
            if not self._authorized():
                self._json({'error': 'unauthorized'}, 401)
                return
            self._json(
                {
                    'object': 'list',
                    'data': [
                        {
                            'id': MODEL_ID,
                            'object': 'model',
                            'created': int(time.time()),
                            'owned_by': 'loadtest',
                        }
                    ],
                }
            )
            return
        self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = self.path.split('?', 1)[0].rstrip('/')
        if not path.endswith('/chat/completions'):
            self._json({'error': 'not found'}, 404)
            return
        if not self._authorized():
            self._json({'error': 'unauthorized'}, 401)
            return

        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        try:
            body = json.loads(raw or b'{}')
        except ValueError:
            body = {}

        stream = bool(body.get('stream'))
        include_usage = bool((body.get('stream_options') or {}).get('include_usage'))

        if stream:
            self._stream(include_usage)
        else:
            self._once()

    # --- 响应 ---

    def _once(self):
        time.sleep(TTFT_MS / 1000.0 + TOKENS * INTERVAL)
        text = (WORD * ((TOKENS // len(WORD)) + 1))[:TOKENS]
        self._json(
            {
                'id': 'chatcmpl-' + uuid.uuid4().hex[:24],
                'object': 'chat.completion',
                'created': int(time.time()),
                'model': MODEL_ID,
                'choices': [
                    {
                        'index': 0,
                        'message': {'role': 'assistant', 'content': text},
                        'finish_reason': 'stop',
                    }
                ],
                'usage': {
                    'prompt_tokens': 64,
                    'completion_tokens': TOKENS,
                    'total_tokens': 64 + TOKENS,
                },
            }
        )

    def _stream(self, include_usage: bool):
        cid = 'chatcmpl-' + uuid.uuid4().hex[:24]
        created = int(time.time())

        def frame(delta=None, finish=None, usage=None):
            payload = {
                'id': cid,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': MODEL_ID,
                'choices': []
                if usage is not None
                else [{'index': 0, 'delta': delta or {}, 'finish_reason': finish}],
            }
            if usage is not None:
                payload['usage'] = usage
            return b'data: ' + json.dumps(payload, ensure_ascii=False).encode() + b'\n\n'

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        try:
            time.sleep(TTFT_MS / 1000.0)
            self._chunk(frame(delta={'role': 'assistant', 'content': ''}))

            for i in range(TOKENS):
                self._chunk(frame(delta={'content': WORD[i % len(WORD)]}))
                if INTERVAL:
                    time.sleep(INTERVAL)

            self._chunk(frame(finish='stop'))
            if include_usage:
                self._chunk(
                    frame(
                        usage={
                            'prompt_tokens': 64,
                            'completion_tokens': TOKENS,
                            'total_tokens': 64 + TOKENS,
                        }
                    )
                )
            self._chunk(b'data: [DONE]\n\n')
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # 客户端提前断开是压测里的正常现象，不要刷屏
            pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    dur = TTFT_MS / 1000.0 + TOKENS * INTERVAL
    print(
        'mock LLM 已启动 http://127.0.0.1:%d/v1  model=%s  '
        '每次回复约 %.1fs（%d token @ %s/s）' % (PORT, MODEL_ID, dur, TOKENS, TPS),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止', flush=True)
        server.shutdown()


if __name__ == '__main__':
    sys.exit(main())
