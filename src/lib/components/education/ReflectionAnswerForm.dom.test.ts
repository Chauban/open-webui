// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

import type { ReflectionQuestion } from '$lib/apis/education/types';
import ReflectionAnswerForm from './ReflectionAnswerForm.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const questions: ReflectionQuestion[] = [
	{
		id: 'help',
		kind: 'multi_choice',
		prompt: 'AI 帮了你什么？',
		options: ['列提纲', '润色'],
		allow_other: true,
		placeholder: null,
		required: true,
		show_when: 'ai_used'
	},
	{
		id: 'why_not',
		kind: 'single_choice',
		prompt: '为什么没用 AI？',
		options: ['用不上', '想自己练'],
		allow_other: false,
		placeholder: null,
		required: false,
		show_when: 'ai_not_used'
	},
	{
		id: 'change',
		kind: 'text',
		prompt: '你改了什么？',
		options: [],
		allow_other: false,
		placeholder: '具体一处',
		required: true,
		show_when: 'always'
	}
];

test('题目随「是否用了 AI」出现或隐藏', async () => {
	render(ReflectionAnswerForm, { props: { questions }, context });

	expect(screen.getByText('你改了什么？')).toBeTruthy();
	expect(screen.queryByText('AI 帮了你什么？')).toBeNull();
	expect(screen.queryByText('为什么没用 AI？')).toBeNull();

	await fireEvent.click(screen.getByText('Used AI'));
	expect(screen.getByText('AI 帮了你什么？')).toBeTruthy();
	expect(screen.queryByText('为什么没用 AI？')).toBeNull();

	await fireEvent.click(screen.getByText('Did not use AI'));
	expect(screen.queryByText('AI 帮了你什么？')).toBeNull();
	expect(screen.getByText('为什么没用 AI？')).toBeTruthy();
	expect(screen.getByText('Optional')).toBeTruthy();
});

test('勾选「其他」才出现说明框，每次作答都通知外层存草稿', async () => {
	const onChange = vi.fn();
	render(ReflectionAnswerForm, {
		props: { questions, aiUsage: 'used', onChange },
		context
	});

	expect(screen.queryByPlaceholderText('Briefly describe your answer')).toBeNull();
	await fireEvent.click(screen.getByText('Other'));
	const note = screen.getByPlaceholderText('Briefly describe your answer');
	await fireEvent.input(note, { target: { value: '查资料' } });
	await fireEvent.input(screen.getByPlaceholderText('具体一处'), {
		target: { value: '改了结论' }
	});

	expect(onChange).toHaveBeenCalledTimes(3);
});
