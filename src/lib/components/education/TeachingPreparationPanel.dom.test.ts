// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { AssignmentDraft } from '$lib/utils/assignment-form';
import type { TeachingConfig } from '$lib/apis/education';
import TeachingPreparationPanel from './TeachingPreparationPanel.svelte';

const api = vi.hoisted(() => vi.fn());
vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		url: new URL('http://localhost/teacher/assignments/new')
	})
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
vi.mock('$lib/apis/education/teaching', async (original) => ({
	...(await original<typeof import('$lib/apis/education/teaching')>()),
	teachingApi: api
}));

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const template: TeachingConfig = {
	task_mode: 'revise_argument',
	version: 1,
	created_at: 1,
	prompt: '完整推荐提示词',
	default_description: '',
	scoring_mode: 'total',
	score_max: 100,
	rubric_schema: { criteria: [] },
	reflection_questions: []
};
const draft: AssignmentDraft = {
	title: '论证题',
	description: '解释证据',
	taskMode: 'revise_argument',
	dueAt: '',
	scoreMax: '100',
	scoringMode: 'total',
	coachingStyle: 'balanced',
	rubricCriteria: [],
	reflectionQuestions: [],
	challengeEnabled: false,
	challengeRounds: 3,
	challengeFocusKeys: [],
	thinking: null,
	studentsChooseThinking: false
};
beforeEach(() => {
	api.mockReset();
	api.mockImplementation(async (path) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [
					{ id: 'A', name: '模型 A', capabilities: { reasoning: true }, thinking_support: {} }
				],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'medium'
			};
		throw new Error('unexpected request: ' + path);
	});
});
afterEach(cleanup);

test('资料搜索默认关闭，开关保存不修改教师提示词', async () => {
	let saved;
	api.mockImplementation(async (path, method, body) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [{ id: 'A', name: '模型 A', capabilities: {}, thinking_support: {} }],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'medium',
				search_available: true
			};
		if (method === 'POST' || method === 'PUT') {
			saved = {
				id: 'prep-search',
				revision: (saved?.revision ?? 0) + 1,
				assignment_id: null,
				payload: JSON.parse(JSON.stringify(body.payload)),
				published: null
			};
		}
		return { ...saved, coverage: { stages: [] }, trials: [] };
	});
	render(TeachingPreparationPanel, { props: { draft: structuredClone(draft), template }, context });
	await screen.findByRole('option', { name: '模型 A' });
	const checkbox = screen.getByRole('checkbox', { name: '允许按需搜索资料' }) as HTMLInputElement;
	expect(checkbox.checked).toBe(false);
	await fireEvent.click(checkbox);
	await fireEvent.click(screen.getByRole('button', { name: '保存准备稿' }));
	await screen.findByText('已保存');
	expect(saved.payload.ai.web_search).toBe(true);
	expect(saved.payload.ai.prompt).toBe(template.prompt);
	await fireEvent.click(checkbox);
	await fireEvent.click(screen.getByRole('button', { name: '保存准备稿' }));
	await waitFor(() => expect(saved.payload.ai.web_search).toBe(false));
	expect(saved.payload.ai.prompt).toBe(template.prompt);
});

test('准备稿允许缺少班级和截止，保存不发布作业', async () => {
	let saved;
	api.mockImplementation(async (path, method, body) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [{ id: 'A', name: '模型 A', capabilities: {}, thinking_support: {} }],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'medium'
			};
		if (method === 'POST') {
			saved = {
				id: 'prep-1',
				revision: 1,
				assignment_id: null,
				payload: body.payload,
				published: null
			};
			return saved;
		}
		return { ...saved, coverage: { stages: [] }, trials: [] };
	});
	render(TeachingPreparationPanel, { props: { draft: structuredClone(draft), template }, context });
	await screen.findByRole('option', { name: '模型 A' });
	await fireEvent.input(screen.getByLabelText('你希望 AI 怎样辅导学生'), {
		target: { value: '教师自己的完整提示词' }
	});
	await fireEvent.click(screen.getByRole('button', { name: '保存准备稿' }));
	await screen.findByText('已保存');
	expect(saved.payload.assignment.due_at).toBeNull();
	expect(saved.payload.assignment.classroom_ids).toEqual([]);
	expect(saved.payload.ai.prompt).toBe('教师自己的完整提示词');
	expect(api.mock.calls.some(([path]) => path.includes('/publish'))).toBe(false);
	expect((screen.getByRole('button', { name: '正式布置' }) as HTMLButtonElement).disabled).toBe(
		true
	);
});

test('保存失败保留提示词，进入试教前不发送旧配置', async () => {
	render(TeachingPreparationPanel, { props: { draft: structuredClone(draft), template }, context });
	await screen.findByRole('option', { name: '模型 A' });
	const input = screen.getByLabelText('你希望 AI 怎样辅导学生') as HTMLTextAreaElement;
	await fireEvent.input(input, { target: { value: '尚未保存的完整原文' } });
	api.mockRejectedValue({ detail: 'Preparation changed; reload before saving' });
	await fireEvent.click(screen.getByRole('button', { name: '用样稿试教' }));
	await waitFor(() =>
		expect(screen.getByRole('alert').textContent).toContain('Preparation changed')
	);
	expect(input.value).toBe('尚未保存的完整原文');
	expect(api.mock.calls.some(([path]) => path === '/teacher/teaching-trials')).toBe(false);
});

test('班级和截止修改保留试教覆盖，题目变化才使覆盖失效', async () => {
	let saved;
	api.mockImplementation(async (path, method, body) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [{ id: 'A', name: '模型 A', capabilities: {}, thinking_support: {} }],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'model_default'
			};
		if (method === 'POST') {
			saved = {
				id: 'prep',
				revision: 1,
				assignment_id: null,
				payload: body.payload,
				published: null
			};
			return saved;
		}
		return { ...saved, coverage: { stages: ['first_read', 'coaching_chat'] }, trials: [] };
	});
	const view = render(TeachingPreparationPanel, {
		props: { draft: structuredClone(draft), template },
		context
	});
	await screen.findByRole('option', { name: '模型 A' });
	await fireEvent.click(screen.getByRole('button', { name: '保存准备稿' }));
	await screen.findByText(/first_read、coaching_chat/);
	await view.rerender({
		draft: { ...draft, dueAt: '2026-12-01T23:59' },
		selectedClassroomIds: new Set(['class-1'])
	});
	expect(screen.getByText(/first_read、coaching_chat/)).toBeTruthy();
	await view.rerender({ draft: { ...draft, title: '另一道题' } });
	expect(screen.queryByText(/first_read、coaching_chat/)).toBeNull();
});

test('恢复作业辅导配置完成前禁止编辑，迟到响应不会覆盖用户输入', async () => {
	let finishVersions: (value: unknown) => void;
	const versions = new Promise((resolve) => {
		finishVersions = resolve;
	});
	api.mockImplementation(async (path) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [{ id: 'A', name: '模型 A', capabilities: {}, thinking_support: {} }],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'model_default'
			};
		if (path.endsWith('/ai-revisions')) return versions;
		if (path.endsWith('/teaching-trials')) return [];
		throw new Error('unexpected path');
	});
	render(TeachingPreparationPanel, {
		props: {
			draft: structuredClone(draft),
			template,
			assignment: { id: 'assignment-1', classroom_id: 'class-1', config_revision: 1 }
		},
		context
	});
	const input = screen.getByLabelText('你希望 AI 怎样辅导学生') as HTMLTextAreaElement;
	expect(input.disabled).toBe(true);
	expect((screen.getByRole('button', { name: '用样稿试教' }) as HTMLButtonElement).disabled).toBe(
		true
	);
	finishVersions!([
		{
			id: 'version-1',
			revision: 1,
			config: {
				ai: {
					prompt: '保存的教师提示词',
					model_id: 'A',
					thinking: 'model_default',
					template_version: 1
				}
			},
			change_summary: ''
		}
	]);
	await waitFor(() => expect(input.disabled).toBe(false));
	expect(input.value).toBe('保存的教师提示词');
	await fireEvent.input(input, { target: { value: '本次刚输入的新内容' } });
	await waitFor(() => expect(input.value).toBe('本次刚输入的新内容'));
});
