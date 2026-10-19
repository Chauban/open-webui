// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

import type { AiStep, AiStepPolicy, AiStepView } from '$lib/apis/education';
import EducationStudentLimits from './EducationStudentLimits.svelte';
import EducationAiStepSettings from './EducationAiStepSettings.svelte';

afterEach(cleanup);
const t = (key: string, options?: Record<string, string>) =>
	Object.entries(options ?? {}).reduce(
		(text, [name, value]) => text.replace(`{{${name}}}`, value),
		key
	);
const context = new Map([['i18n', readable({ t })]]);

const step = (key: AiStep['key'], model_source: AiStep['model_source']): AiStep => ({
	key,
	model_source,
	model_configurable: key !== 'coaching_chat',
	teacher_controllable: key === 'coaching_chat'
});
const STEPS: AiStep[] = [
	step('coaching_chat', 'student_chat_model'),
	step('first_read', 'student_chat_model'),
	step('reader_check', 'student_chat_model'),
	step('image_parsing', 'admin_model'),
	step('class_insight', 'teacher_chat_model')
];
const POLICY: AiStepPolicy = {
	coaching_chat: { control: 'admin', default: 'model_default' },
	first_read: { model: null, thinking: 'model_default' },
	reader_check: { model: null, thinking: 'model_default' },
	image_parsing: { model: 'vision-model', thinking: 'off' },
	class_insight: { model: null, thinking: 'model_default' }
};
const MODELS = [
	{ id: 'vision-model', name: 'Vision', info: { meta: { capabilities: { vision: true } } } },
	{ id: 'text-only', name: 'Text only', info: { meta: { capabilities: { vision: false } } } },
	{ id: 'arena-model', name: 'Arena', owned_by: 'arena' },
	{
		id: 'glm-5.3',
		name: 'GLM-5.3',
		info: { meta: { capabilities: { vision: false } } },
		thinking_support: { can_turn_off: false, graded: true }
	},
	{
		id: 'kimi-k2.6',
		name: 'Kimi K2.6',
		info: { meta: { capabilities: { vision: false } } },
		thinking_support: { can_turn_off: true, graded: false }
	}
];

const render_ = (props: Record<string, unknown> = {}) =>
	render(EducationAiStepSettings, {
		props: { policy: POLICY, steps: STEPS, models: MODELS, ...props },
		context
	});
const optionLabels = (name: string) =>
	[...(screen.getByRole('combobox', { name }) as HTMLSelectElement).options].map((option) =>
		option.textContent?.trim()
	);

test('每个平台步骤一行:模型与思考各一个下拉,通读那行带试跑提醒', async () => {
	const onChange = vi.fn();
	render_({ onChange });

	for (const key of ['first_read', 'reader_check', 'image_parsing', 'class_insight']) {
		expect(screen.getByTestId(`ai-step-row-${key}`)).toBeTruthy();
	}
	expect(screen.getByText(/turning thinking off here led to clearly more missed/)).toBeTruthy();
	expect(screen.getAllByRole('option', { name: 'Model default (recommended)' }).length).toBe(1);

	// 不指定时的说法按步骤:通读跟学生、归纳跟老师、图片识别即关闭导入;竞技场模型不列
	expect(optionLabels('Model for First read and follow-up review')).toEqual([
		'Follow the student’s selected model',
		'Vision',
		'Text only',
		'GLM-5.3',
		'Kimi K2.6'
	]);
	expect(optionLabels('Model for Class argument summary')[0]).toBe(
		'Follow the teacher’s selected model'
	);
	// 图片识别只列能看图的
	expect(optionLabels('Model for Draft image parsing')).toEqual([
		'Off (no image import)',
		'Vision'
	]);

	await fireEvent.change(screen.getByRole('combobox', { name: 'Model for AI reader check' }), {
		target: { value: 'text-only' }
	});
	expect(onChange).toHaveBeenCalledWith({
		...POLICY,
		reader_check: { model: 'text-only', thinking: 'model_default' }
	});
	await fireEvent.change(screen.getByRole('combobox', { name: 'Draft image parsing' }), {
		target: { value: 'low' }
	});
	expect(onChange).toHaveBeenLastCalledWith({
		...POLICY,
		image_parsing: { model: 'vision-model', thinking: 'low' }
	});
});

test('辅导对话的模型始终是学生选的,只能定思考由谁设', async () => {
	const onChange = vi.fn();
	render_({ onChange });

	expect(screen.queryByRole('combobox', { name: 'Model for Coaching chat' })).toBeNull();
	await fireEvent.change(
		screen.getByRole('combobox', { name: 'Who sets thinking in the coaching chat' }),
		{ target: { value: 'student' } }
	);
	expect(onChange).toHaveBeenCalledWith({
		...POLICY,
		coaching_chat: { control: 'student', default: 'model_default' }
	});
});

test('指定的模型被删掉时标红说明回落方式,原值仍保留在下拉里', () => {
	const views: AiStepView[] = [
		{
			key: 'reader_check',
			model_source: 'student_chat_model',
			model_id: 'gone-model',
			model_name: 'gone-model',
			model_available: false,
			control: 'admin',
			thinking: 'model_default'
		}
	];
	render_({ policy: { ...POLICY, reader_check: { model: 'gone-model', thinking: 'low' } }, views });

	expect(screen.getByTestId('ai-step-missing-reader_check').textContent).toContain(
		'uses the student’s model'
	);
	expect(optionLabels('Model for AI reader check')).toContain('gone-model');
	expect(screen.queryByTestId('ai-step-missing-first_read')).toBeNull();
});

test('作业外的学生权限按后端算出的结果如实显示', () => {
	render(EducationStudentLimits, {
		props: { overrides: { params: true, system_prompt: false } },
		context
	});

	expect(screen.getByTestId('student-permission-status').textContent).toContain(
		'students in the student group can change model parameters and cannot add a system prompt'
	);
	expect(
		screen.getByText(/cannot change model parameters or add their own system prompt/)
	).toBeTruthy();
});

test('选到只有开 / 关的模型时,那一行写明各档都只是开着', () => {
	render_({ policy: { ...POLICY, reader_check: { model: 'kimi-k2.6', thinking: 'high' } } });

	expect(screen.getByTestId('ai-step-thinking-note-reader_check').textContent).toContain(
		'only turns thinking on or off'
	);
	expect(screen.queryByTestId('ai-step-thinking-note-first_read')).toBeNull();
});

test('选到关不掉思考的模型时,那一行写明「关」会退到最低档', () => {
	render_({ policy: { ...POLICY, first_read: { model: 'glm-5.3', thinking: 'off' } } });

	expect(screen.getByTestId('ai-step-thinking-note-first_read').textContent).toContain(
		'cannot turn thinking off'
	);
});
