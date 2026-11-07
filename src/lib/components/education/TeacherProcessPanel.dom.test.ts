// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
const getProcess = vi.fn();
vi.mock('$lib/apis/education', () => ({
	getSubmissionProcess: (...args: unknown[]) => getProcess(...args)
}));
import TeacherProcessPanel from './TeacherProcessPanel.svelte';
import { initialProcessState } from '$lib/utils/process-review';
afterEach(() => {
	cleanup();
	getProcess.mockReset();
});
const context = new Map([
	[
		'i18n',
		readable({
			t: (s: string, o: Record<string, unknown> = {}) =>
				Object.entries(o).reduce(
					(text, [key, value]) => text.replace(`{{${key}}}`, String(value)),
					s
				)
		})
	]
]);
const catalog = {
	final_version_id: 'final-v',
	round_no: 1,
	default_before_id: 'initial',
	default_after_id: 'final',
	event_snapshots: { 'prompt:a': 'v1' },
	snapshots: [
		{ id: 'initial', kind: 'initial', major: true, created_at: null },
		{ id: 'v1', kind: 'version', version_no: 1, major: true, used_by_ai: true, created_at: 2 },
		{ id: 'hidden', kind: 'version', version_no: 2, major: false, created_at: 3 },
		{ id: 'final', kind: 'final', major: true, created_at: 4 }
	]
};
test('交流定位实际稿件，版本对照和按期间看交流共享选择', async () => {
	getProcess.mockResolvedValue(catalog);
	const inspect = vi.fn().mockResolvedValue(undefined);
	render(TeacherProcessPanel, {
		props: {
			submissionId: 's',
			finalVersionId: 'final-v',
			onInspect: inspect,
			state: initialProcessState(),
			events: [
				{
					key: 'prompt:a',
					kind: 'prompt',
					role: 'assistant',
					meta: 'AI 回复',
					label: '反馈内容',
					created_at: 2,
					thinking_level: null,
					model_id: 'frozen-chat-model',
					ai_step: 'coaching_chat',
					inserted_length: null,
					source: null
				},
				{
					key: 'prompt:b',
					kind: 'prompt',
					role: 'user',
					meta: '学生',
					label: '稍后的交流',
					created_at: 3,
					thinking_level: null,
					model_id: null,
					ai_step: null,
					inserted_length: null,
					source: null
				}
			]
		},
		context
	});
	await screen.findByTestId('process-snapshot-v1');
	expect(screen.getByText('Model: frozen-chat-model')).toBeTruthy();
	expect(screen.getByText('Thinking level not recorded')).toBeTruthy();
	expect(screen.queryByTestId('process-snapshot-hidden')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: '查看稿件：AI 回复' }));
	expect(inspect).toHaveBeenLastCalledWith({ beforeId: 'v1', afterId: 'v1', mode: 'snapshot' });
	await fireEvent.click(screen.getByRole('button', { name: '版本对照' }));
	expect(inspect).toHaveBeenLastCalledWith({ beforeId: 'initial', afterId: 'v1', mode: 'compare' });
	await fireEvent.click(screen.getByRole('checkbox', { name: /显示中间自动保存版本/ }));
	await fireEvent.change(screen.getByRole('combobox', { name: '起点稿件' }), {
		target: { value: 'hidden' }
	});
	await fireEvent.change(screen.getByRole('combobox', { name: '终点稿件' }), {
		target: { value: 'final' }
	});
	await fireEvent.click(screen.getByRole('button', { name: '看这期间的交流' }));
	expect(screen.queryByText('反馈内容')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: '版本对照' }));
	await fireEvent.click(screen.getByRole('button', { name: '从起点到提交' }));
	await fireEvent.click(screen.getByRole('button', { name: '看这期间的交流' }));
	expect(screen.getByText('已按所选稿件的时间范围筛选交流。')).toBeTruthy();
	expect(screen.getByText('反馈内容')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: '查看稿件：AI 回复' }));
	expect(screen.getByText('反馈内容')).toBeTruthy();
	expect(screen.getByText('稍后的交流')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: '版本对照' }));
	expect((screen.getByRole('combobox', { name: '终点稿件' }) as HTMLSelectElement).value).toBe(
		'v1'
	);
	expect(getProcess).toHaveBeenCalledTimes(1);
});
test('读取失败有重试入口，不显示另一份提交的目录', async () => {
	getProcess.mockRejectedValue({
		detail: 'The submission changed. Reload it before viewing the writing process.'
	});
	render(TeacherProcessPanel, { props: { submissionId: 's', finalVersionId: 'old' }, context });
	await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
	expect(screen.queryByTestId('process-snapshot-v1')).toBeNull();
	expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
});
