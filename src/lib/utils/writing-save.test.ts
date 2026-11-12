import { afterEach, expect, test, vi } from 'vitest';
import { waitForWritingSave, writingSaveProblem } from './writing-save';
afterEach(() => {
	vi.useRealTimers();
});
test.each([400, 401, 403, 404, 409, 413, 422])(
	'does not automatically repeat an HTTP %i rejection',
	(status) => {
		expect(writingSaveProblem({ status }).retryable).toBe(false);
	}
);
test.each([408, 429, 500, 502, 503, 504])('can retry transient HTTP %i failures', (status) => {
	expect(writingSaveProblem({ status }).retryable).toBe(true);
});
test('preserves authentication, review, format and diagnostic distinctions', () => {
	expect(writingSaveProblem({ status: 401 }).login).toBe(true);
	expect(
		writingSaveProblem({ status: 409, detail: 'Submission has already been reviewed' }).message
	).toContain('已批改');
	expect(
		writingSaveProblem({
			status: 400,
			detail: 'Invalid paragraph alignment',
			requestId: 'abc',
			field: 'content_json'
		})
	).toMatchObject({ requestId: 'abc', field: 'content_json', retryable: false });
	expect(writingSaveProblem(new TypeError('Failed to fetch')).retryable).toBe(true);
});
test('a hanging save does not permit chat; completed waits leave no timers', async () => {
	vi.useFakeTimers();
	const result = waitForWritingSave(new Promise<void>(() => {}));
	await vi.advanceTimersByTimeAsync(5000);
	expect(await result).toBe(false);
	expect(await waitForWritingSave(Promise.resolve())).toBe(true);
	expect(vi.getTimerCount()).toBe(0);
});
