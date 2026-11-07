// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import type { RevisionReading } from '$lib/apis/education';
import RevisionReadings from './RevisionReadings.svelte';
vi.mock('svelte/transition', () => ({ fade: () => ({ duration: 0 }) }));
vi.mock('$lib/utils/transitions', () => ({ flyAndScale: () => ({ duration: 0 }) }));
vi.mock('focus-trap', () => ({
	createFocusTrap: () => ({ activate() {}, deactivate() {}, pause() {}, unpause() {} })
}));
afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const record = (status: RevisionReading['status']) =>
	({
		id: 'reading-1',
		purpose: 'first_read',
		status,
		created_at: 1,
		context: { description_version: 1 },
		source_text: '',
		feedback: null
	}) as RevisionReading;
test('请求中及刷新恢复的阅读都有等待状态，不重复提示', async () => {
	const { rerender } = render(RevisionReadings, { props: { busy: true }, context });
	expect(screen.getAllByRole('status')).toHaveLength(1);
	await rerender({ busy: true, record: record('running') });
	expect(screen.getAllByRole('status')).toHaveLength(1);
	await rerender({ busy: false, record: record('running') });
	expect(screen.getByRole('status').textContent).toContain('可以继续写作或提交');
	await rerender({ busy: false, record: record('failed') });
	expect(screen.queryByRole('status')).toBeNull();
	expect(screen.getByText('这次没能读完。你可以重试，也可以直接聊聊稿子或继续修改。')).toBeTruthy();
	await rerender({ busy: false, record: record('ready') });
	expect(screen.queryByRole('status')).toBeNull();
});

test('阅读直接展示且没有流程选择；失败可重试，只读时不可重试', async () => {
	const retry = vi.fn();
	const { rerender } = render(RevisionReadings, {
		props: {
			record: {
				...record('ready'),
				feedback: {
					understanding: '我读到你想说明什么',
					strength: null,
					focus: [{ quote: '原句', feedback: '这一处我还不明白' }],
					overview: '不重复显示的整体意见'
				}
			},
			onRetry: retry
		},
		context
	});
	expect(screen.getByText('我读到你想说明什么')).toBeTruthy();
	expect(screen.getByText('这一处我还不明白')).toBeTruthy();
	for (const label of [
		'就这处聊聊',
		'展开完整反馈',
		'整段复看',
		'我想讨论其他地方',
		'去修改稿件',
		'此前的阅读记录'
	])
		expect(screen.queryByText(label)).toBeNull();
	await rerender({ record: record('failed') });
	await fireEvent.click(screen.getByRole('button', { name: '重试阅读' }));
	expect(retry).toHaveBeenCalledWith('first_read');
	await rerender({ readonly: true });
	expect(screen.queryByRole('button', { name: '重试阅读' })).toBeNull();
});
