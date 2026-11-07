// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import ProcessDraftView from './ProcessDraftView.svelte';
import type { ProcessComparison } from '$lib/apis/education';
afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (s: string) => s })]]);
const comparison = {
	before: { id: 'initial', kind: 'initial', text: '旧稿。' },
	after: { id: 'final', kind: 'final', text: '新稿。' },
	blocks: [{ op: 'replace', old_text: '旧稿。', new_text: '新稿。' }],
	unchanged: false,
	final_version_id: 'v'
} as ProcessComparison;
test('稿件对照只读；加载或失败时不继续显示上一份稿件', async () => {
	const { rerender } = render(ProcessDraftView, {
		props: { inspection: { mode: 'compare', loading: false, error: '', comparison } },
		context
	});
	expect(screen.getAllByText('旧稿。').length).toBeGreaterThan(0);
	expect(screen.getAllByText('新稿。').length).toBeGreaterThan(0);
	expect(screen.queryByRole('textbox')).toBeNull();
	await rerender({ inspection: { mode: 'compare', loading: true, error: '', comparison: null } });
	expect(screen.getByRole('status')).toBeTruthy();
	expect(screen.queryByText('旧稿。')).toBeNull();
	await rerender({
		inspection: { mode: 'compare', loading: false, error: '提交已更新', comparison: null }
	});
	expect(screen.getByRole('alert').textContent).toContain('提交已更新');
});
test('查看某次读稿时保留空稿事实', () => {
	render(ProcessDraftView, {
		props: {
			inspection: {
				mode: 'snapshot',
				loading: false,
				error: '',
				comparison: { ...comparison, after: { ...comparison.after, text: '' } }
			}
		},
		context
	});
	expect(screen.getByText('当时正文为空。')).toBeTruthy();
});
