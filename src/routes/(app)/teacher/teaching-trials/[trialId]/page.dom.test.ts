// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import Page from './+page.svelte';
const { api, action } = vi.hoisted(() => ({ api: vi.fn(), action: vi.fn() }));
vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		params: { trialId: 'seed' },
		url: new URL('http://localhost/teacher/teaching-trials/seed')
	})
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: api, trialAction: action }));
const ai = {
	prompt: 'original prompt',
	model_id: 'A',
	thinking: 'model_default',
	template_version: 1
};
const payload = {
	title: 'Test title',
	description: 'Test requirements',
	candidates: [ai],
	sample: 'sample'
};
const seed = {
	id: 'seed',
	preparation_id: 'prep',
	sequence: 0,
	config: { title: payload.title, description: payload.description, ai },
	state: { draft: 'sample', baseline: null, dialogue: [], status: 'draft', running_event_id: null },
	events: []
};
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
beforeEach(() => {
	api.mockReset();
	action.mockReset();
	api.mockImplementation(async (path, method, body) => {
		if (path === '/teacher/teaching-trials/seed') return structuredClone(seed);
		if (path === '/teacher/teaching-preparations/prep')
			return {
				id: 'prep',
				revision: 1,
				assignment_id: null,
				published: null,
				payload: { assignment: { title: payload.title, description: payload.description }, ai }
			};
		if (path === '/teacher/teaching-models')
			return {
				models: ['A', 'B'].map((id) => ({
					id,
					name: 'Model ' + id,
					capabilities: {},
					thinking_support: {}
				}))
			};
		if (path === '/teacher/teaching-workbenches')
			return { id: 'work', revision: 1, payload: structuredClone(payload) };
		if (path === '/teacher/teaching-workbenches/work' && method === 'PUT')
			return { id: 'work', revision: 2, payload: body.payload };
		if (path.endsWith('/comparisons') || path === '/teacher/saved-teaching-plans') return [];
		throw new Error('unexpected ' + path);
	});
});
afterEach(cleanup);
test('editable inputs and shared prompt persist without publication', async () => {
	render(Page, { context });
	await screen.findByLabelText('作业题目');
	expect(screen.queryByText('整段复看')).toBeNull();
	expect(screen.queryByText('试教评价与调用记录')).toBeNull();
	expect(screen.queryByText('自主结束并查看提交预览')).toBeNull();
	expect(screen.queryByText('本结果使用的配置')).toBeNull();
	expect(screen.queryByText('重新初读（新的调用）')).toBeNull();
	expect(screen.queryByText('仅发送到此模型')).toBeNull();
	await fireEvent.input(screen.getByLabelText('辅导提示词'), {
		target: { value: 'modified prompt' }
	});
	await fireEvent.click(screen.getByLabelText('Model B'));
	await fireEvent.click(screen.getByText('保存试教工作稿'));
	await screen.findByText('已保存');
	const saved = api.mock.calls.find(
		([p, m]) => p === '/teacher/teaching-workbenches/work' && m === 'PUT'
	)![2];
	expect(saved.payload.candidates.map((c: { prompt: string }) => c.prompt)).toEqual([
		'modified prompt',
		'modified prompt'
	]);
	expect(api.mock.calls.some(([p]) => p.includes('/publish') || p.includes('/adopt'))).toBe(false);
});
test('failed save retains edits and never starts stale calls', async () => {
	render(Page, { context });
	await screen.findByLabelText('作业题目');
	await fireEvent.input(screen.getByLabelText('作业题目'), { target: { value: 'unsaved title' } });
	const original = api.getMockImplementation()!;
	api.mockImplementation((path, ...rest) =>
		path === '/teacher/teaching-workbenches/work'
			? Promise.reject({ detail: 'revision conflict' })
			: original(path, ...rest)
	);
	await fireEvent.click(screen.getByText('开始测试'));
	await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('revision conflict'));
	expect((screen.getByLabelText('作业题目') as HTMLInputElement).value).toBe('unsaved title');
	expect(action).not.toHaveBeenCalled();
});

test('model panels collapse without changing generation or losing feedback; missing table separator renders', async () => {
	const table = '诊断表格\n| 要素 | 评分 |\n| 观点 | 合格 |\n| 理由 | 不合格 |';
	const first = {
		...structuredClone(seed),
		state: { ...seed.state, baseline: 'sample', dialogue: [{ role: 'assistant', content: table }] }
	};
	const second = {
		...structuredClone(first),
		id: 'second',
		config: { ...first.config, ai: { ...ai, model_id: 'B' } },
		state: { ...first.state, dialogue: [{ role: 'assistant', content: '模型 B 的反馈' }] }
	};
	const original = api.getMockImplementation()!;
	api.mockImplementation((path, ...rest) =>
		path.endsWith('/comparisons')
			? Promise.resolve([{ id: 'group', payload, trials: [first, second] }])
			: original(path, ...rest)
	);
	render(Page, { context });
	await screen.findByRole('table');
	expect(screen.getByRole('table').textContent).toContain('不合格');
	await fireEvent.click(screen.getByRole('button', { name: '收起 Model A' }));
	expect(screen.queryByRole('table')).toBeNull();
	expect(screen.getByText('模型 B 的反馈')).toBeTruthy();
	expect(action).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: '展开 Model A' }));
	expect(screen.getByRole('table')).toBeTruthy();
	expect(action).not.toHaveBeenCalled();
});

test('reopening failed or stopped results shows their persisted reason, never an unstarted prompt', async () => {
	const failed = {
		...structuredClone(seed),
		state: { ...seed.state, baseline: 'sample' },
		events: [
			{
				id: 'failed',
				sequence: 1,
				action: 'confirm',
				state: seed.state,
				call: {
					status: 'failed',
					error_type: 'HTTPException',
					attempts: [{ error_type: 'SocketTimeoutError' }]
				}
			}
		]
	};
	const original = api.getMockImplementation()!;
	api.mockImplementation((path, ...rest) =>
		path.endsWith('/comparisons')
			? Promise.resolve([{ id: 'group', payload, trials: [failed] }])
			: original(path, ...rest)
	);
	const view = render(Page, { context });
	await screen.findByRole('alert');
	expect(screen.getByRole('alert').textContent).toContain('响应超时');
	expect(screen.queryByText('点击上方「开始测试」，查看这个模型的反馈。')).toBeNull();
	view.unmount();
	failed.events[0].call.status = 'stopped';
	render(Page, { context });
	await screen.findByText('已停止');
	expect(screen.getByRole('status').textContent).toContain('生成已停止');
	expect(screen.queryByText('点击上方「开始测试」，查看这个模型的反馈。')).toBeNull();
});

test('switching comparison history keeps responses fetched after generation', async () => {
	const initial = { ...structuredClone(seed), state: { ...seed.state, baseline: 'sample' } };
	const other = { ...structuredClone(initial), id: 'other' };
	let server = { ...structuredClone(initial), state: { ...initial.state, dialogue: [] as { role: string; content: string }[] } };
	const original = api.getMockImplementation()!;
	api.mockImplementation((path, ...rest) => {
		if (path === '/teacher/teaching-trials/seed') return Promise.resolve(server);
		if (path.endsWith('/comparisons'))
			return Promise.resolve([
				{ id: 'first', payload, trials: [initial] },
				{ id: 'second', payload, trials: [other] }
			]);
		return original(path, ...rest);
	});
	action.mockImplementation(async () => {
		server = {
			...initial,
			state: { ...initial.state, dialogue: [{ role: 'assistant', content: '这次生成已经完成' }] }
		};
	});
	render(Page, { context });
	await screen.findByLabelText('扮演学生交流');
	await fireEvent.input(screen.getByLabelText('扮演学生交流'), { target: { value: '请回应' } });
	await fireEvent.click(screen.getByRole('button', { name: '发送' }));
	await screen.findByText('这次生成已经完成');
	await fireEvent.change(screen.getByLabelText('查看试教结果'), { target: { value: 'second' } });
	await fireEvent.change(screen.getByLabelText('查看试教结果'), { target: { value: 'first' } });
	expect(screen.getByText('这次生成已经完成')).toBeTruthy();
});
