// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import type { RevisionReading } from '$lib/apis/education';
import RevisionReadings from './RevisionReadings.svelte';
vi.mock('svelte/transition', () => ({ fade: () => ({ duration: 0 }) }));
vi.mock('$lib/utils/transitions', () => ({ flyAndScale: () => ({ duration: 0 }) }));
vi.mock('focus-trap', () => ({ createFocusTrap: () => ({ activate() {}, deactivate() {}, pause() {}, unpause() {} }) }));
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
	await rerender({ busy: true, records: [record('running')] });
	expect(screen.getAllByRole('status')).toHaveLength(1);
	await rerender({ busy: false, records: [record('running')] });
	expect(screen.getByRole('status').textContent).toContain('可以继续写作或提交');
	await rerender({ busy: false, records: [record('failed')] });
	expect(screen.queryByRole('status')).toBeNull();
	expect(screen.getByText('这次没能读完。你可以重试，也可以直接聊聊稿子或继续修改。')).toBeTruthy();
	await rerender({ busy: false, records: [record('ready')] });
	expect(screen.queryByRole('status')).toBeNull();
});

test('讨论快捷入口只交给输入框，不要求先完成阅读；只读时隐藏操作', async () => {
	const discuss = vi.fn();
	const edit = vi.fn();
	const { rerender } = render(RevisionReadings, {
		props: { busy: true, onDiscuss: discuss, onEdit: edit },
		context
	});
	await fireEvent.click(screen.getByRole('button', { name: '我想讨论其他地方' }));
	expect(discuss).toHaveBeenCalledWith('');
	await fireEvent.click(screen.getByRole('button', { name: '去修改稿件' }));
	expect(edit).toHaveBeenCalledOnce();
	await rerender({ readonly: true });
	expect(screen.queryByRole('button', { name: '我想讨论其他地方' })).toBeNull();
});

test('引用入口带上原文；完整反馈按需打开，不调用模型', async () => {
	const discuss = vi.fn();
	const read = vi.fn();
	const ready = {
		...record('ready'),
		feedback: {
			understanding: '我读到的观点',
			strength: null,
			focus: [{ quote: '具体句子', feedback: '这里的证据呢？' }],
			overview: '完整阅读意见'
		}
	};
	render(RevisionReadings, {
		props: { records: [ready], onDiscuss: discuss, onRead: read },
		context
	});
	await fireEvent.click(screen.getByRole('button', { name: '就这处聊聊' }));
	expect(discuss.mock.calls[0][0]).toContain('具体句子');
	await fireEvent.click(screen.getByRole('button', { name: '展开完整反馈' }));
	expect(await screen.findByText('完整阅读意见')).toBeTruthy();
	expect(read).not.toHaveBeenCalled();
});
