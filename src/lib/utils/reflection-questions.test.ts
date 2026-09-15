import { describe, expect, test } from 'vitest';

import type { ReflectionQuestion } from '$lib/apis/education/types';
import {
	buildReflectionAnswers,
	cloneReflectionQuestions,
	createReflectionQuestion,
	getDefaultReflectionQuestions,
	getReflectionAnswersError,
	getReflectionQuestionsError,
	normalizeReflectionQuestions,
	reflectionQuestionsFingerprint
} from './reflection-questions';

const t = (key: string) => key;

const question = (patch: Partial<ReflectionQuestion>): ReflectionQuestion => ({
	...createReflectionQuestion('text'),
	prompt: 'Prompt',
	...patch
});

describe('teacher reflection questions', () => {
	test('default set is valid and starts with the AI-help question for AI users', () => {
		const defaults = getDefaultReflectionQuestions(t);
		expect(defaults.length).toBe(5);
		expect(defaults[0].show_when).toBe('ai_used');
		expect(getReflectionQuestionsError(normalizeReflectionQuestions(defaults))).toBeNull();
	});

	test('normalizing drops blank options and fields that do not fit the kind', () => {
		const [normalized] = normalizeReflectionQuestions([
			question({ kind: 'single_choice', options: [' A ', '', 'B'], placeholder: 'x' })
		]);
		expect(normalized.options).toEqual(['A', 'B']);
		expect(normalized.placeholder).toBeNull();
	});

	test.each([
		[{ prompt: '' }, 'Reflection question {{number}} needs a prompt.'],
		[
			{ kind: 'multi_choice', options: ['Only'] },
			'Reflection question {{number}} needs at least two options.'
		],
		[
			{ kind: 'multi_choice', options: ['Same', 'Same'] },
			'Reflection question {{number}} has duplicate options.'
		]
	] as const)('rejects %o', (patch, key) => {
		expect(getReflectionQuestionsError([question(patch as Partial<ReflectionQuestion>)])?.key).toBe(
			key
		);
	});

	test('one option plus Other is enough for a choice question', () => {
		expect(
			getReflectionQuestionsError([
				question({ kind: 'single_choice', options: ['Yes'], allow_other: true })
			])
		).toBeNull();
	});

	test('fingerprint ignores ids so cloned sets compare equal', () => {
		const defaults = getDefaultReflectionQuestions(t);
		expect(reflectionQuestionsFingerprint(cloneReflectionQuestions(defaults))).toBe(
			reflectionQuestionsFingerprint(defaults)
		);
	});
});

describe('student reflection answers', () => {
	const choice = question({
		id: 'help',
		kind: 'multi_choice',
		options: ['Outline', 'Polish'],
		allow_other: true,
		show_when: 'ai_used'
	});
	const text = question({ id: 'change', prompt: 'What changed?' });
	const questions = [choice, text];

	test('requires the AI usage answer first', () => {
		expect(getReflectionAnswersError(questions, null, {})?.key).toBe('Choose whether AI was used.');
	});

	test('hidden questions are neither required nor submitted', () => {
		const drafts = {
			change: { selected: [], otherChosen: false, otherText: '', text: ' Rewrote the claim ' }
		};
		expect(getReflectionAnswersError(questions, 'none', drafts)).toBeNull();
		expect(buildReflectionAnswers(questions, 'none', drafts)).toEqual([
			{ question_id: 'change', selected: [], other_text: null, text: 'Rewrote the claim' }
		]);
	});

	test('Other needs a note once it is ticked', () => {
		const drafts = {
			help: { selected: [], otherChosen: true, otherText: '', text: '' },
			change: { selected: [], otherChosen: false, otherText: '', text: 'x' }
		};
		expect(getReflectionAnswersError(questions, 'used', drafts)?.key).toBe(
			'Please describe your "Other" answer to: {{prompt}}'
		);
	});

	test('required questions must be answered', () => {
		expect(getReflectionAnswersError(questions, 'used', {})?.params).toEqual({
			prompt: 'Prompt'
		});
	});

	test('stale options no longer on the question are dropped', () => {
		const drafts = {
			help: { selected: ['Outline', 'Removed'], otherChosen: false, otherText: '', text: '' }
		};
		expect(buildReflectionAnswers([choice], 'used', drafts)[0].selected).toEqual(['Outline']);
	});
});
