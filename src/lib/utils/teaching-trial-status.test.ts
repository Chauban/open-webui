import { expect, test } from 'vitest';
import type { Trial } from '$lib/apis/education/teaching';
import { teachingTrialStatus } from './teaching-trial-status';

const fixture = (call: Record<string, unknown> | null, running: string | null = null): Trial => ({
	id: 'trial',
	preparation_id: 'prep',
	sequence: 1,
	config: {
		title: 'test',
		description: 'task',
		ai: { prompt: 'prompt', model_id: 'A', thinking: 'model_default', template_version: 1 }
	},
	state: {
		baseline: 'draft',
		draft: 'draft',
		status: 'active',
		running_event_id: running,
		dialogue: []
	},
	events: call
		? [{ id: 'event', sequence: 1, action: 'confirm', state: {} as Trial['state'], call }]
		: []
});

test('persisted provider timeout is distinguishable from an unstarted trial', () => {
	const trial = fixture({
		status: 'failed',
		error_type: 'HTTPException',
		attempts: [{ error_type: 'SocketTimeoutError' }, { error_type: 'SocketTimeoutError' }]
	});
	const before = JSON.stringify(trial);
	expect(teachingTrialStatus(trial).message).toContain('响应超时');
	expect(teachingTrialStatus(trial).status).toBe('failed');
	expect(teachingTrialStatus(fixture(null)).status).toBe('idle');
	expect(JSON.stringify(trial)).toBe(before);
});

test('final format failure takes precedence over an earlier network timeout', () => {
	expect(
		teachingTrialStatus(
			fixture({
				status: 'failed',
				error_type: 'ValidationError',
				attempts: [{ error_type: 'SocketTimeoutError' }, { http_status: 200 }],
				outputs: [{ valid: false }]
			})
		).message
	).toContain('格式检查');
});

test('stopping and non-call save events retain the last completed call outcome', () => {
	const trial = fixture({ status: 'stopped' });
	trial.events.push({ ...trial.events[0], id: 'stop', sequence: 2, action: 'stop', call: null });
	expect(teachingTrialStatus(trial).status).toBe('stopped');
	expect(teachingTrialStatus(fixture({ status: 'ready' })).status).toBe('ready');
	expect(teachingTrialStatus(fixture({ status: 'failed' }, 'active-event')).status).toBe('running');
});

test('plain feedback failures are not mislabeled as JSON format problems', () => {
	for (const [code, expected] of [
		['empty_response', '没有返回反馈正文'],
		['incomplete_response', '未完整生成']
	]) {
		const result = teachingTrialStatus(
			fixture({ status: 'failed', error_code: code, outputs: [{ valid: false }] })
		);
		expect(result.message).toContain(expected);
		expect(result.message).not.toContain('格式检查');
	}
});
