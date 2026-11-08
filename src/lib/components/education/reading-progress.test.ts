import { afterEach, expect, test, vi } from 'vitest';
import { pollReadingProgress } from './reading-progress';

afterEach(() => {
	vi.useRealTimers();
});

test('POST 未结束时更新阅读进度，停止后丢弃迟到结果', async () => {
	vi.useFakeTimers();
	let resolve!: (value: string) => void;
	const receive = vi.fn();
	const load = vi
		.fn()
		.mockResolvedValueOnce('retrying')
		.mockImplementationOnce(
			() =>
				new Promise<string>((done) => {
					resolve = done;
				})
		);
	const stop = pollReadingProgress(load, receive);
	await vi.advanceTimersByTimeAsync(2000);
	expect(receive).toHaveBeenCalledWith('retrying');
	await vi.advanceTimersByTimeAsync(2000);
	stop();
	resolve('stale running record');
	await vi.advanceTimersByTimeAsync(4000);
	expect(receive).toHaveBeenCalledTimes(1);
	expect(load).toHaveBeenCalledTimes(2);
});

test('进度 GET 暂时失败不停止后续轮询', async () => {
	vi.useFakeTimers();
	const receive = vi.fn();
	const load = vi
		.fn()
		.mockRejectedValueOnce(new Error('network'))
		.mockResolvedValueOnce('retrying');
	const stop = pollReadingProgress(load, receive);
	await vi.advanceTimersByTimeAsync(4000);
	expect(receive).toHaveBeenCalledWith('retrying');
	stop();
});
