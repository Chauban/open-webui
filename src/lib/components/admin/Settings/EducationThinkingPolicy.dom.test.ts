// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

import type { AiStep, ThinkingPolicy } from '$lib/apis/education';
import EducationStudentLimits from './EducationStudentLimits.svelte';
import EducationThinkingPolicy from './EducationThinkingPolicy.svelte';

afterEach(cleanup);
const t = (key: string, options?: Record<string, string>) =>
	Object.entries(options ?? {}).reduce(
		(text, [name, value]) => text.replace(`{{${name}}}`, value),
		key
	);
const context = new Map([['i18n', readable({ t })]]);

const STEPS: AiStep[] = [
	{ key: 'coaching_chat', model_source: 'student_chat_model', teacher_controllable: true },
	{ key: 'first_read', model_source: 'student_chat_model', teacher_controllable: false },
	{ key: 'reader_check', model_source: 'student_chat_model', teacher_controllable: false },
	{ key: 'image_parsing', model_source: 'draft_image_model', teacher_controllable: false },
	{ key: 'class_insight', model_source: 'teacher_chat_model', teacher_controllable: false }
];
const POLICY: ThinkingPolicy = {
	coaching_chat: { control: 'admin', default: 'model_default' },
	first_read: 'model_default',
	reader_check: 'model_default',
	image_parsing: 'off',
	class_insight: 'model_default'
};

test('平台步骤一行一个,通读那行带试跑提醒,改了把整份设置交出去', async () => {
	const onChange = vi.fn();
	render(EducationThinkingPolicy, { props: { policy: POLICY, steps: STEPS, onChange }, context });

	for (const key of ['first_read', 'reader_check', 'image_parsing', 'class_insight']) {
		expect(screen.getByTestId(`thinking-row-${key}`)).toBeTruthy();
	}
	expect(screen.getByText(/turning thinking off here led to clearly more missed/)).toBeTruthy();
	expect(screen.getByRole('option', { name: 'Model default (recommended)' })).toBeTruthy();

	const imageSelect = screen.getByRole('combobox', {
		name: 'Draft image parsing'
	}) as HTMLSelectElement;
	expect(imageSelect.value).toBe('off');
	await fireEvent.change(imageSelect, { target: { value: 'low' } });
	expect(onChange).toHaveBeenCalledWith({ ...POLICY, image_parsing: 'low' });
});

test('辅导对话一行可以把思考交给老师', async () => {
	const onChange = vi.fn();
	render(EducationThinkingPolicy, { props: { policy: POLICY, steps: STEPS, onChange }, context });

	expect(screen.getByTestId('thinking-row-coaching_chat')).toBeTruthy();
	await fireEvent.change(
		screen.getByRole('combobox', { name: 'Who sets thinking in the coaching chat' }),
		{ target: { value: 'student' } }
	);
	expect(onChange).toHaveBeenCalledWith({
		...POLICY,
		coaching_chat: { control: 'student', default: 'model_default' }
	});
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
