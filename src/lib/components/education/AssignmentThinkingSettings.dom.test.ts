// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const getTeacherAssignmentAiSettings = vi.fn();
vi.mock('$lib/apis/education', () => ({
	getTeacherAssignmentAiSettings: (...args: unknown[]) => getTeacherAssignmentAiSettings(...args)
}));

import AssignmentAiSummary from './AssignmentAiSummary.svelte';
import AssignmentThinkingSettings from './AssignmentThinkingSettings.svelte';

afterEach(() => {
	cleanup();
	getTeacherAssignmentAiSettings.mockReset();
});
const t = (key: string, options?: Record<string, string>) =>
	Object.entries(options ?? {}).reduce(
		(text, [name, value]) => text.replace(`{{${name}}}`, value),
		key
	);
const context = new Map([['i18n', readable({ t })]]);

test('只下放给老师时没有学生开关,写明只作用于辅导对话', () => {
	render(AssignmentThinkingSettings, {
		props: { control: 'teacher', adminDefault: 'medium', value: null },
		context
	});

	expect(screen.getByText('Admin default (Medium)')).toBeTruthy();
	expect(screen.getByText(/^Coaching chat only\./)).toBeTruthy();
	expect(screen.queryByText('Let students switch thinking off')).toBeNull();
});

test('管理员允许时老师可以把思考交给学生开关', () => {
	render(AssignmentThinkingSettings, {
		props: { control: 'student', adminDefault: 'medium', value: 'low' },
		context
	});

	expect(screen.getByText('Let students switch thinking off')).toBeTruthy();
});

test('AI 设置卡按后端算出的生效值逐步骤列出', async () => {
	const view = (key, model_source, control, thinking, model = {}) => ({
		key,
		model_source,
		model_id: null,
		model_name: null,
		model_available: true,
		control,
		thinking,
		...model
	});
	getTeacherAssignmentAiSettings.mockResolvedValue({
		steps: [
			view('coaching_chat', 'student_chat_model', 'student', 'low'),
			view('first_read', 'student_chat_model', 'admin', 'model_default'),
			view('reader_check', 'student_chat_model', 'admin', 'low', {
				model_id: 'gone-model',
				model_name: 'gone-model',
				model_available: false
			}),
			view('image_parsing', 'admin_model', 'admin', 'off', {
				model_id: 'vision-model',
				model_name: 'Vision'
			}),
			view('class_insight', 'teacher_chat_model', 'admin', 'model_default')
		],
		coaching_thinking: {
			control: 'student',
			level: 'low',
			source: 'teacher',
			students_choose: true
		}
	});
	render(AssignmentAiSummary, { props: { assignmentId: 'a-1' }, context });

	await waitFor(() => expect(screen.getByTestId('assignment-ai-summary')).toBeTruthy());
	const coaching = screen.getByTestId('ai-summary-coaching_chat').textContent ?? '';
	expect(coaching).toContain('Set for this assignment');
	expect(coaching).toContain('Thinking: Low');
	expect(coaching).toContain('Students can switch it off');
	expect(screen.getByTestId('ai-summary-image_parsing').textContent).toContain('Thinking: Off');
	expect(screen.getByTestId('ai-summary-first_read').textContent).toContain(
		'Set by the administrator'
	);
	// 模型:没指定的写跟谁的,指定的写名称,指定的被删掉时写明回落
	expect(screen.getByTestId('ai-summary-first_read').textContent).toContain(
		'Model the student picked'
	);
	expect(screen.getByTestId('ai-summary-image_parsing').textContent).toContain('Vision');
	expect(screen.getByTestId('ai-summary-reader_check').textContent).toContain(
		'gone-model is no longer available; using: Model the student picked'
	);
	expect(screen.getByTestId('ai-summary-class_insight').textContent).toContain(
		'Model the teacher picked'
	);
});
