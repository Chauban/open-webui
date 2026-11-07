import type { TaskMode } from '$lib/apis/education';

export const TASK_TYPES = [
	{
		key: 'from_scratch',
		title: '从零写作',
		hint: '从空白开始，在写作与讨论中完成作业。',
		requiresBaseline: false,
		readerCheck: true
	},
	{
		key: 'revise_draft',
		title: '修订初稿（文献综述）',
		hint: '确认文献综述初稿后，按需讨论、修改并自主提交。',
		requiresBaseline: true,
		readerCheck: false
	},
	{
		key: 'revise_argument',
		title: '修订初稿（段落论证）',
		hint: '确认论证初稿后，围绕观点、理由、证据与回应讨论，自主决定提交。',
		requiresBaseline: true,
		readerCheck: false
	}
] as const;

export const isRevision = (mode?: string | null) =>
	TASK_TYPES.some((type) => type.key === mode && type.requiresBaseline);
export const taskTypeLabel = (mode: TaskMode) =>
	TASK_TYPES.find((type) => type.key === mode)!.title;
