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
	expect(screen.getByRole('status').textContent).toContain('暂时无法编辑或提交');
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
					overview: '整体意见'
				}
			},
			onRetry: retry
		},
		context
	});
	expect(screen.getByText('我读到你想说明什么')).toBeTruthy();
	expect(screen.getByText('这一处我还不明白')).toBeTruthy();
	expect(screen.getByText('整体意见')).toBeTruthy();
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

test('初读支持连续回复和超过两处反馈，不要求复述或肯定段落', async () => {
	const { rerender } = render(RevisionReadings, {
		props: {
			record: {
				...record('ready'),
				feedback: { understanding: '', strength: null, focus: [], overview: '老师指定的连续回复' }
			}
		},
		context
	});
	expect(screen.getByText('老师指定的连续回复')).toBeTruthy();
	await rerender({
		record: {
			...record('ready'),
			feedback: {
				understanding: '',
				strength: null,
				focus: [1, 2, 3].map((i) => ({ quote: '', feedback: `建议 ${i}` })),
				overview: ''
			}
		}
	});
	for (const i of [1, 2, 3]) expect(screen.getByText(`建议 ${i}`)).toBeTruthy();
});

test('连续阅读反馈渲染标题、强调、列表、引用、表格和链接', () => {
	const { container } = render(RevisionReadings, {
		props: {
			record: {
				...record('ready'),
				feedback: {
					understanding: '',
					strength: null,
					focus: [],
					overview: [
						'### 1. 诊断表格',
						'',
						'* **观点（Claim）：合格**',
						'  * 文本：围绕身体管理展开。',
						'',
						'> 请补充原始出处。',
						'',
						'| 项目 | 判断 |',
						'| --- | --- |',
						'| 证据 | 待核对 |',
						'',
						'[参考资料](https://example.com/source)'
					].join('\n')
				}
			}
		},
		context
	});
	expect(screen.getByRole('heading', { level: 3, name: '1. 诊断表格' })).toBeTruthy();
	expect(container.querySelector('strong')?.textContent).toBe('观点（Claim）：合格');
	expect(container.querySelector('ul ul li')?.textContent).toContain('文本：围绕身体管理展开。');
	expect(container.querySelector('blockquote')?.textContent).toContain('请补充原始出处。');
	expect(screen.getByRole('columnheader', { name: '项目' })).toBeTruthy();
	expect(screen.getByRole('cell', { name: '待核对' })).toBeTruthy();
	expect(screen.getByRole('link', { name: '参考资料' }).getAttribute('href')).toBe(
		'https://example.com/source'
	);
	expect(container.textContent).not.toContain('###');
	expect(container.textContent).not.toContain('**');
});

test('各段反馈均渲染格式，引用的学生原句仍按原文展示', () => {
	const { container } = render(RevisionReadings, {
		props: {
			record: {
				...record('ready'),
				feedback: {
					understanding: '**理解**',
					strength: { quote: '', feedback: '**优点**' },
					focus: [{ quote: '**学生原句**', feedback: '**建议**' }],
					overview: '**总结**'
				}
			}
		},
		context
	});
	expect(Array.from(container.querySelectorAll('strong'), (node) => node.textContent)).toEqual([
		'理解',
		'优点',
		'建议',
		'总结'
	]);
	expect(container.querySelector('blockquote')?.textContent?.trim()).toBe('**学生原句**');
});
