import { describe, expect, it } from 'vitest';
import { buildAssignmentPayload, type AssignmentDraft } from './assignment-form';
import { isRevision } from './task-types';
import {
	retainApplicableReflectionDrafts,
	type ReflectionAnswerDrafts
} from './reflection-questions';
import type { ReflectionQuestion } from '$lib/apis/education';

const question: ReflectionQuestion = {
	id: 'q',
	kind: 'text',
	prompt: 'Why?',
	options: [],
	allow_other: false,
	placeholder: null,
	required: true,
	show_when: 'always'
};
const answers: ReflectionAnswerDrafts = {
	q: { selected: [], otherChosen: false, otherText: '', text: 'My reasoning' }
};

describe('revision submission configuration', () => {
	it('uses baseline capability for both revision types', () => {
		expect(isRevision('revise_argument')).toBe(true);
		expect(isRevision('revise_draft')).toBe(true);
		expect(isRevision('from_scratch')).toBe(false);
	});
	it('retains answers when only required status or placeholder changes', () => {
		expect(
			retainApplicableReflectionDrafts(
				[question],
				[{ ...question, required: false, placeholder: 'Optional' }],
				answers
			)
		).toEqual(answers);
	});
	it('clears answers when question meaning or options change', () => {
		expect(
			retainApplicableReflectionDrafts(
				[question],
				[{ ...question, prompt: 'A different question' }],
				answers
			)
		).toEqual({});
		expect(retainApplicableReflectionDrafts([question], [], answers)).toEqual({});
	});
	it.each(['from_scratch', 'revise_argument'] as const)(
		'sends no rubric or reader check for total-only %s',
		(taskMode) => {
			const draft: AssignmentDraft = {
				imageReadingEnabled: false,
				title: 'Argument',
				description: '',
				dueAt: '2030-01-01T12:00',
				scoreMax: '100',
				scoringMode: 'total',
				taskMode,
				coachingStyle: 'balanced',
				challengeEnabled: true,
				challengeRounds: 3,
				challengeFocusKeys: ['one'],
				rubricCriteria: [{ key: 'one', label: 'Old criterion', maxScore: '5' }],
				reflectionQuestions: [],
				thinking: null,
				studentsChooseThinking: false
			};
			const result = buildAssignmentPayload(draft, (key) => key);
			expect(result.error).toBeUndefined();
			expect(result.payload?.rubric_schema.criteria).toEqual([]);
			expect(result.payload?.challenge_enabled).toBe(false);
			expect(result.payload?.score_max).toBe(100);
		}
	);
});
