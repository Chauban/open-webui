// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { autosaveWritingSession } from './index';
afterEach(() => {
	vi.unstubAllGlobals();
	vi.useRealTimers();
});
test('save errors retain HTTP status, retry delay, request reference and safe field path', async () => {
	vi.stubGlobal(
		'fetch',
		vi.fn(
			async () =>
				new Response(JSON.stringify({ detail: 'Invalid link' }), {
					status: 400,
					headers: {
						'content-type': 'application/json',
						'x-request-id': 'safe-id',
						'x-writing-error-field': 'content_json.content.0.marks.href',
						'retry-after': '3'
					}
				})
		)
	);
	await expect(
		autosaveWritingSession('test', 'session', { content_json: null, content_text: '' })
	).rejects.toMatchObject({
		status: 400,
		detail: 'Invalid link',
		requestId: 'safe-id',
		field: 'content_json.content.0.marks.href',
		retryAfterMs: 3000
	});
});
test('a malformed error body still retains the HTTP failure for retry classification', async () => {
	vi.stubGlobal(
		'fetch',
		vi.fn(
			async () =>
				new Response('upstream unavailable', {
					status: 503,
					headers: { 'content-type': 'application/json' }
				})
		)
	);
	await expect(
		autosaveWritingSession('test', 'session', { content_json: null, content_text: '' })
	).rejects.toMatchObject({ status: 503 });
});
test('a hanging save aborts after 20 seconds and releases its timer', async () => {
	vi.useFakeTimers();
	vi.stubGlobal(
		'fetch',
		vi.fn(
			(_url, options) =>
				new Promise((_resolve, reject) =>
					options.signal.addEventListener('abort', () =>
						reject(new DOMException('Timed out', 'AbortError'))
					)
				)
		)
	);
	const result = expect(
		autosaveWritingSession('test', 'session', { content_json: null, content_text: '' })
	).rejects.toMatchObject({ name: 'AbortError' });
	await vi.advanceTimersByTimeAsync(20000);
	await result;
	expect(vi.getTimerCount()).toBe(0);
});
