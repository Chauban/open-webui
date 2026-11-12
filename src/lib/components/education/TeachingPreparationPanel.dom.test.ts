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
vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}), replaceState: vi.fn() }));
vi.mock('$lib/stores', async () => ({
	user: (await import('svelte/store')).readable({ id: 'teacher-1' })
}));
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
	photoTranscriptionEnabled: false,
	imageReadingEnabled: false,
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

let saved;
let failSave = false;
let failPublish = false;
let searchAvailable = false;
beforeEach(() => {
	localStorage.clear();
	saved = undefined;
	failSave = failPublish = searchAvailable = false;
	api.mockReset();
	api.mockImplementation(async (path, method, body) => {
		if (path === '/teacher/teaching-models')
			return {
				models: [
					{ id: 'A', name: '模型 A', capabilities: { reasoning: true }, thinking_support: {} }
				],
				policy: { recommended_model_id: 'A' },
				recommended_thinking: 'medium',
				search_available: searchAvailable
			};
		if (path.endsWith('/ai-revisions')) return [];
		if (path.endsWith('/publish')) {
			if (failPublish) throw { detail: '发布暂时失败' };
			return [{ id: 'published-assignment' }];
		}
		if (path === '/teacher/teaching-trials') return { id: 'trial-1' };
		if (path.endsWith('/teaching-trials')) return [];
		if (method === 'POST' || method === 'PUT') {
			if (failSave) throw { detail: '暂时无法保存，请重试' };
			saved = {
				id: body.id ?? saved.id,
				revision: (saved?.revision ?? 0) + 1,
				assignment_id: body.assignment_id ?? saved?.assignment_id ?? null,
				payload: structuredClone(body.payload),
				published: null
			};
		}
		return saved;
	});
});
afterEach(() => {
	cleanup();
	localStorage.clear();
});
const complete = () => ({ ...structuredClone(draft), dueAt: '2026-12-01T23:59' });
function show(fields = {}) {
	return render(TeachingPreparationPanel, {
		props: { draft: structuredClone(draft), template, ...fields },
		context
	});
}
async function ready() {
	await waitFor(() =>
		expect(screen.getByRole('button', { name: '正式布置' }) as HTMLButtonElement).toBeTruthy()
	);
}
async function editPrompt(value = '教师新提示词') {
	await fireEvent.input(screen.getByLabelText('你希望 AI 怎样辅导学生'), { target: { value } });
}
async function confirmPublish() {
	await fireEvent.click(
		screen.getByRole('checkbox', { name: '已核对当前配置及试教覆盖情况，按当前配置发布。' })
	);
}

test('只打开页面不建立空草稿，首次编辑自动保存且不发布', async () => {
	show();
	await ready();
	expect(screen.queryByRole('button', { name: '保存准备稿' })).toBeNull();
	expect(api.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0);
	await editPrompt();
	expect(localStorage.length).toBe(1);
	await screen.findByText('已自动保存');
	expect(saved.payload.ai.prompt).toBe('教师新提示词');
	expect(saved.payload.assignment.due_at).toBeNull();
	expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(false);
	expect(localStorage.length).toBe(0);
});

test('提示词和模型未填也自动保存，试教时才校验', async () => {
	show();
	await ready();
	await editPrompt('');
	await fireEvent.change(screen.getByLabelText('本次作业的辅导模型'), { target: { value: '' } });
	await screen.findByText('已自动保存');
	expect(saved.payload.ai.prompt).toBe('');
	expect(saved.payload.ai.model_id).toBe('');
	await fireEvent.click(screen.getByRole('button', { name: '用样稿试教' }));
	expect(screen.getByRole('alert').textContent).toContain('请填写辅导提示词。');
	expect(screen.getByRole('alert').textContent).toContain('请选择本次作业的辅导模型。');
	expect(api.mock.calls.some(([path]) => path === '/teacher/teaching-trials')).toBe(false);
});

test.each([
	{ scoreMax: '' },
	{ scoringMode: 'dimensions', rubricCriteria: [{ key: 'c', label: '', maxScore: '-' }] },
	{
		reflectionQuestions: [
			{
				id: 'q',
				kind: 'text',
				prompt: '',
				options: [],
				required: true,
				allow_other: false,
				placeholder: null,
				show_when: 'always'
			}
		]
	}
])('不完整的评分和反思仍能保存并进入试教 %#', async (fields) => {
	show({ draft: { ...structuredClone(draft), ...fields } });
	await ready();
	await editPrompt();
	await screen.findByText('已自动保存');
	await fireEvent.click(screen.getByRole('button', { name: '用样稿试教' }));
	await waitFor(() =>
		expect(api.mock.calls.some(([path]) => path === '/teacher/teaching-trials')).toBe(true)
	);
	expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(false);
});

test('发布必须确认，自动保存不会撤销对当前内容的确认', async () => {
	show({ draft: complete(), selectedClassroomIds: new Set(['c']) });
	await ready();
	const button = screen.getByRole('button', { name: '正式布置' }) as HTMLButtonElement;
	expect(button.disabled).toBe(true);
	await editPrompt();
	await confirmPublish();
	await screen.findByText('已自动保存');
	expect(button.disabled).toBe(false);
	failPublish = true;
	await fireEvent.click(button);
	await screen.findByText('发布暂时失败');
	expect(api.mock.calls.filter(([path]) => path.endsWith('/publish'))).toHaveLength(1);
	failPublish = false;
	await fireEvent.click(button);
	await waitFor(() =>
		expect(api.mock.calls.filter(([path]) => path.endsWith('/publish'))).toHaveLength(2)
	);
});

test('修改内容撤销旧确认，发布等待最新自动保存完成', async () => {
	const view = show({ selectedClassroomIds: new Set(['c']) });
	await ready();
	await confirmPublish();
	expect(screen.getByText('Assignment due time is required.')).toBeTruthy();
	await view.rerender({ draft: complete() });
	const checkbox = screen.getByRole('checkbox', {
		name: '已核对当前配置及试教覆盖情况，按当前配置发布。'
	}) as HTMLInputElement;
	expect(checkbox.checked).toBe(false);
	await confirmPublish();
	await fireEvent.click(screen.getByRole('button', { name: '正式布置' }));
	await waitFor(() =>
		expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(true)
	);
	expect(saved.payload.assignment.due_at).toBe(new Date('2026-12-01T23:59').getTime() / 1000);
	const published = api.mock.calls.find(([path]) => path.endsWith('/publish'))!;
	expect(published[2].expected_revision).toBe(saved.revision);
});

test('保存失败保留输入和本地备份，不用旧配置试教', async () => {
	show();
	await ready();
	failSave = true;
	await editPrompt('断网前的修改');
	await fireEvent.click(screen.getByRole('button', { name: '用样稿试教' }));
	await screen.findByText('自动保存失败');
	expect((screen.getByLabelText('你希望 AI 怎样辅导学生') as HTMLTextAreaElement).value).toBe(
		'断网前的修改'
	);
	expect(JSON.parse(localStorage.getItem(localStorage.key(0)!)!).payload.ai.prompt).toBe(
		'断网前的修改'
	);
	expect(api.mock.calls.some(([path]) => path === '/teacher/teaching-trials')).toBe(false);
	failSave = false;
	await fireEvent.click(screen.getByRole('button', { name: '重试保存' }));
	await screen.findByText('已自动保存');
});

test('正式发布前保存失败不会发布旧稿', async () => {
	show({ draft: complete(), selectedClassroomIds: new Set(['c']) });
	await ready();
	await editPrompt();
	await confirmPublish();
	failSave = true;
	await fireEvent.click(screen.getByRole('button', { name: '正式布置' }));
	await screen.findByText('自动保存失败');
	expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(false);
});

test('发布前保存期间再编辑不会发布未经确认的新内容', async () => {
	const view = show({ draft: complete(), selectedClassroomIds: new Set(['c']) });
	await ready();
	await confirmPublish();
	const original = api.getMockImplementation()!;
	let finish!: () => void;
	api.mockImplementationOnce(async (...args) => {
		await new Promise<void>((resolve) => {
			finish = resolve;
		});
		return original(...args);
	});
	await fireEvent.click(screen.getByRole('button', { name: '正式布置' }));
	await view.rerender({ draft: { ...complete(), dueAt: '2026-12-03T23:59' } });
	finish();
	await screen.findByText('保存期间内容发生变化，请核对后重新确认发布。');
	expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(false);
	expect(saved.payload.assignment.due_at).toBe(new Date('2026-12-03T23:59').getTime() / 1000);
});

test.each(['from_scratch', 'revise_draft'] as const)(
	'普通作业 %s 也自动保存完整表单',
	async (taskMode) => {
		const view = show({
			draft: { ...draft, taskMode },
			template: { ...template, task_mode: taskMode }
		});
		await ready();
		expect(screen.queryByRole('button', { name: '用样稿试教' })).toBeNull();
		await view.rerender({
			draft: {
				...draft,
				taskMode,
				title: '普通作业草稿',
				photoTranscriptionEnabled: false,
				imageReadingEnabled: true,
				challengeRounds: 2,
				thinking: 'medium',
				studentsChooseThinking: true
			}
		});
		await screen.findByText('已自动保存');
		expect(saved.payload.assignment.title).toBe('普通作业草稿');
		expect(saved.payload.assignment.image_reading_enabled).toBe(true);
		expect(saved.payload.assignment.challenge_rounds).toBe(2);
		expect(saved.payload.assignment.model_params).toEqual({
			thinking: 'medium',
			students_choose_thinking: true
		});
	}
);

test('资料搜索仅管理员开放时出现，开关自动保存不改提示词', async () => {
	searchAvailable = true;
	show();
	await ready();
	await fireEvent.click(screen.getByRole('checkbox', { name: '允许按需搜索资料' }));
	await screen.findByText('已自动保存');
	expect(saved.payload.ai.web_search).toBe(true);
	expect(saved.payload.ai.prompt).toBe(template.prompt);
});

test('应用新版本仍需要调整说明与明确确认', async () => {
	show({ assignment: { id: 'a', classroom_id: 'c', config_revision: 1 } });
	await screen.findByRole('button', { name: '应用新版本' });
	expect(screen.getByText('Describe the teaching change')).toBeTruthy();
	await editPrompt();
	await screen.findByText('已自动保存');
	expect(api.mock.calls.some(([path]) => path.endsWith('/publish'))).toBe(false);
	await fireEvent.input(screen.getByLabelText('修改说明（必填）'), {
		target: { value: '调整证据阅读方式' }
	});
	await confirmPublish();
	expect((screen.getByRole('button', { name: '应用新版本' }) as HTMLButtonElement).disabled).toBe(
		false
	);
});

test('服务端字段错误转成可读提示', async () => {
	show();
	await ready();
	api.mockRejectedValue({
		detail: [
			{
				loc: ['body', 'payload', 'ai', 'prompt'],
				msg: 'String should have at most 65000 characters',
				type: 'string_too_long'
			}
		]
	});
	await editPrompt();
	await screen.findByText('自动保存失败');
	expect(screen.getByRole('alert').textContent).toContain('请检查');
	expect(screen.getByRole('alert').textContent).not.toContain('[object Object]');
});

test('模型不支持思考时初始化不生成空草稿', async () => {
	const original = api.getMockImplementation()!;
	api.mockImplementation(async (...args) => {
		const result = await original(...args);
		if (args[0] === '/teacher/teaching-models') result.models[0].capabilities.reasoning = false;
		return result;
	});
	show();
	await ready();
	expect(screen.getByRole('status').textContent).toBe('编辑后自动保存草稿，仅自己可见。');
	expect(localStorage.length).toBe(0);
});

test('恢复已有草稿保留提示词与试教覆盖，班级截止修改不使试教失效', async () => {
	const { preparationAssignment } = await import('$lib/apis/education/teaching');
	const prep = {
		id: 'restored',
		revision: 2,
		assignment_id: null,
		base_config_revision: null,
		published: null,
		payload: {
			assignment: preparationAssignment(draft, []),
			ai: {
				prompt: '已保存原文',
				model_id: 'A',
				thinking: 'medium',
				template_version: 1,
				web_search: false
			}
		},
		coverage: { stages: ['first_read'] },
		trials: []
	};
	saved = prep;
	const view = show({ initialPreparation: prep });
	await ready();
	expect((screen.getByLabelText('你希望 AI 怎样辅导学生') as HTMLTextAreaElement).value).toBe(
		'已保存原文'
	);
	expect(screen.getByText(/first_read/)).toBeTruthy();
	await view.rerender({ draft: complete(), selectedClassroomIds: new Set(['c']) });
	await screen.findByText('已自动保存');
	expect(screen.getByText(/first_read/)).toBeTruthy();
	await editPrompt('另一种辅导方式');
	expect(screen.queryByText(/first_read/)).toBeNull();
});
