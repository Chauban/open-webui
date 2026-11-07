import type { ProcessSnapshot, ProcessComparison, SubmissionProcess } from '$lib/apis/education';
export type ProcessViewState = {
	mode: 'process' | 'compare';
	filter: 'all' | 'conversation' | 'changes';
	showAutosaves: boolean;
	beforeId: string;
	afterId: string;
	selectedKey: string;
	range: { beforeId: string; afterId: string } | null;
	expanded: string[];
};
export const initialProcessState = (): ProcessViewState => ({
	mode: 'process',
	filter: 'all',
	showAutosaves: false,
	beforeId: '',
	afterId: '',
	selectedKey: '',
	range: null,
	expanded: []
});
export type ProcessInspection = {
	mode: 'snapshot' | 'compare';
	loading: boolean;
	error: string;
	comparison: ProcessComparison | null;
};
export const snapshotLabel = (
	snapshot: ProcessSnapshot,
	t: (s: string, o?: Record<string, unknown>) => string
) => {
	const labels = {
		initial: '初稿',
		empty_start: '写作起点（空稿）',
		round_start: '上一轮提交稿',
		reading: '供 AI 阅读的稿件',
		final: '本次提交稿'
	};
	return snapshot.kind === 'version'
		? t('保存版本 {{number}}', { number: snapshot.version_no ?? '' })
		: t(labels[snapshot.kind]);
};
export const processSnapshots = (catalog: SubmissionProcess | null, state: ProcessViewState) =>
	(catalog?.snapshots ?? []).filter(
		(s) => s.major || state.showAutosaves || s.id === state.beforeId || s.id === state.afterId
	);
export const previousProcessSnapshot = (snapshots: ProcessSnapshot[], id: string) =>
	snapshots[Math.max(0, snapshots.findIndex((s) => s.id === id) - 1)]?.id ?? id;
export const conversationWithinRange = (
	createdAt: number,
	before: ProcessSnapshot,
	after: ProcessSnapshot
) => {
	const a = before.created_at ?? Number.NEGATIVE_INFINITY,
		b = after.created_at ?? Number.NEGATIVE_INFINITY;
	return createdAt >= Math.min(a, b) && createdAt <= Math.max(a, b);
};
