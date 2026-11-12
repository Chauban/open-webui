// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import Page from './+page.svelte';

const api = vi.hoisted(() => ({ load: vi.fn(), update: vi.fn(), visibility: vi.fn() }));
vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		params: { assignmentId: 'assignment' },
		url: new URL('http://localhost/teacher/assignments/assignment/settings')
	})
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/apis/education', () => ({
	getTeacherAssignment: api.load,
	updateAssignment: api.update,
	setAssignmentVisibility: api.visibility,
	deleteAssignment: vi.fn(),
	getTeacherAssignmentAiSettings: vi.fn(async () => ({ steps: [], coaching_thinking: null })),
	getTeacherClassrooms: vi.fn(async () => [{ classroom: { id: 'classroom', name: '写作班' } }]),
	getTeacherReflectionQuestionSets: vi.fn(async () => []),
	getTeacherAssignmentDefaults: vi.fn(async () => ({
		allowed_task_modes: ['from_scratch'],
		teaching_configs: {}
	}))
}));

const context = new Map([['i18n', readable({ t: (key: string) => key, language: 'zh-CN' })]]);
let assignment;
beforeEach(() => {
	assignment = {
		id: 'assignment',
		title: '现有作业',
		description: null,
		classroom_id: 'classroom',
		hidden: false,
		due_at: 2000000001,
		score_max: 100,
		scoring_mode: 'total',
		rubric_schema: { criteria: [] },
		task_mode: 'from_scratch',
		coaching_style: 'balanced',
		photo_transcription_enabled: false,
		image_reading_enabled: false,
		challenge_enabled: false,
		challenge_rounds: 3,
		challenge_focus_keys: [],
		reflection_questions: [],
		model_params: { thinking: null, students_choose_thinking: false },
		config_revision: 1,
		teaching_config: { task_mode: 'from_scratch', version: 1, prompt: '辅导说明' }
	};
	localStorage.token = 'token';
	api.load.mockReset().mockImplementation(async () => ({
		assignment: structuredClone(assignment),
		submission_count: 1,
		writing_count: 1,
		task_mode_locked: true
	}));
	api.update.mockReset().mockImplementation(async (_, __, payload) => {
		assignment = { ...assignment, ...payload, config_revision: assignment.config_revision + 1 };
		return assignment;
	});
	api.visibility.mockReset();
});
afterEach(cleanup);

test('设置页隐藏与恢复直接生效，无需修改说明', async () => {
	api.visibility.mockImplementation(async (_, __, hidden) => ({ ...assignment, hidden }));
	render(Page, { context });
	await screen.findByDisplayValue('现有作业');
	await fireEvent.click(screen.getByRole('button', { name: 'Hide Assignment' }));
	await screen.findByRole('button', { name: 'Show Assignment' });
	expect(api.visibility).toHaveBeenCalledWith('token', 'assignment', true);
	expect(screen.queryByRole('dialog')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: 'Show Assignment' }));
	await screen.findByRole('button', { name: 'Hide Assignment' });
	expect(api.visibility).toHaveBeenLastCalledWith('token', 'assignment', false);
	expect(screen.queryByLabelText('修改说明（必填）')).toBeNull();
});

test('页面提示所有变更都需说明；未修改时不产生保存请求', async () => {
	render(Page, { context });
	await screen.findByDisplayValue('现有作业');
	expect(screen.getByText('修改作业设置需填写修改说明；隐藏和恢复显示除外。')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(api.update).not.toHaveBeenCalled();
});

test.each(['title', 'score', 'image'])(
	'%s 修改触发必填说明，成功后下一次修改不能复用旧说明',
	async (field) => {
		const { container } = render(Page, { context });
		await screen.findByDisplayValue('现有作业');
		if (field === 'title')
			await fireEvent.input(screen.getByDisplayValue('现有作业'), {
				target: { value: '新作业题目' }
			});
		if (field === 'score')
			await fireEvent.input(
				within(container.querySelector('#assignment-scoring')!).getByRole('spinbutton'),
				{ target: { value: '50' } }
			);
		if (field === 'image')
			await fireEvent.click(screen.getByRole('switch', { name: 'AI 读取参考图片' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
		const dialog = await screen.findByRole('dialog');
		const confirm = within(dialog).getByRole('button', { name: '确认保存' }) as HTMLButtonElement;
		expect(confirm.disabled).toBe(true);
		const reason = within(dialog).getByLabelText('修改说明（必填）');
		await fireEvent.input(reason, { target: { value: '  \n ' } });
		expect(confirm.disabled).toBe(true);
		expect(api.update).not.toHaveBeenCalled();
		await fireEvent.input(reason, { target: { value: '  根据课堂反馈调整  ' } });
		await fireEvent.click(confirm);
		await waitFor(() =>
			expect(api.update).toHaveBeenCalledWith(
				'token',
				'assignment',
				expect.objectContaining({ change_summary: '根据课堂反馈调整', due_at: 2000000001 })
			)
		);
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(screen.getByText(/最近修改说明/)).toBeTruthy();
		await fireEvent.input(screen.getByPlaceholderText('Academic Argument 1'), {
			target: { value: '另一次修改' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
		expect(((await screen.findByLabelText('修改说明（必填）')) as HTMLTextAreaElement).value).toBe(
			''
		);
	}
);

test('取消不保存，失败保留说明和修改并支持重试', async () => {
	api.update.mockRejectedValueOnce({ detail: 'Unable to save' });
	render(Page, { context });
	await fireEvent.input(await screen.findByDisplayValue('现有作业'), {
		target: { value: '修改后的题目' }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
	await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
	expect(api.update).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
	await fireEvent.input(screen.getByLabelText('修改说明（必填）'), {
		target: { value: '补充课堂要求' }
	});
	await fireEvent.click(screen.getByRole('button', { name: '确认保存' }));
	await screen.findByRole('alert');
	expect((screen.getByLabelText('修改说明（必填）') as HTMLTextAreaElement).value).toBe(
		'补充课堂要求'
	);
	await fireEvent.click(screen.getByRole('button', { name: '确认保存' }));
	await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	expect(api.update).toHaveBeenCalledTimes(2);
});
