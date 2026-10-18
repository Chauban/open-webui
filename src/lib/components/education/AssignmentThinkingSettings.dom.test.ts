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
	getTeacherAssignmentAiSettings.mockResolvedValue({
		steps: [
			{
				key: 'coaching_chat',
				model_source: 'student_chat_model',
				control: 'student',
				thinking: 'low'
			},
			{
				key: 'first_read',
				model_source: 'student_chat_model',
				control: 'admin',
				thinking: 'model_default'
			},
			{ key: 'image_parsing', model_source: 'draft_image_model', control: 'admin', thinking: 'off' }
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
});
