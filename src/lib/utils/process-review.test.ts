import { expect, test } from 'vitest';
import {
	initialProcessState,
	processSnapshots,
	previousProcessSnapshot,
	conversationWithinRange
} from './process-review';
import type { SubmissionProcess } from '$lib/apis/education';
const catalog = {
	snapshots: [
		{ id: 'initial', major: true, created_at: null },
		{ id: 'v1', major: false, created_at: 2 },
		{ id: 'v2', major: true, created_at: 4 },
		{ id: 'final', major: true, created_at: 8 }
	]
} as SubmissionProcess;
test('隐藏中间自动保存，但保留当前选中版本；逐步对照跟随可见节点', () => {
	const state = initialProcessState();
	expect(processSnapshots(catalog, state).map((s) => s.id)).toEqual(['initial', 'v2', 'final']);
	state.afterId = 'v1';
	expect(processSnapshots(catalog, state).map((s) => s.id)).toContain('v1');
	state.showAutosaves = true;
	expect(processSnapshots(catalog, state)).toHaveLength(4);
	expect(previousProcessSnapshot(catalog.snapshots, 'v2')).toBe('v1');
});
test('交流范围可从初稿开始，也支持反向选择，边界内才展示', () => {
	expect(conversationWithinRange(1, catalog.snapshots[0], catalog.snapshots[2])).toBe(true);
	expect(conversationWithinRange(7, catalog.snapshots[2], catalog.snapshots[1])).toBe(false);
	expect(conversationWithinRange(3, catalog.snapshots[2], catalog.snapshots[1])).toBe(true);
});
