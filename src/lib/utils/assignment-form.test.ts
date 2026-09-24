import { describe, expect, it } from 'vitest';

import { buildAssignmentPayload, type AssignmentDraft } from './assignment-form';

const t = (key: string) => key;

const draft = (overrides: Partial<AssignmentDraft> = {}): AssignmentDraft => ({
	title: '  Essay 1 ',
	description: ' Argue a point. ',
	dueAt: '2030-01-01T23:59',
	scoreMax: '10',
	coachingStyle: 'balanced',
	challengeEnabled: false,
	challengeRounds: 3,
	challengeFocusKeys: ['criterion_1'],
	reflectionQuestions: [],
	rubricCriteria: [
		{ key: 'criterion_1', label: 'Ideas', maxScore: '6' },
		{ key: 'criterion_2', label: 'Structure', maxScore: '4' }
	],
	...overrides
});

describe('buildAssignmentPayload', () => {
	it('trims text and drops challenge focus when the reader check is off', () => {
		const { payload, error } = buildAssignmentPayload(draft(), t);
		expect(error).toBeUndefined();
		expect(payload?.title).toBe('Essay 1');
		expect(payload?.description).toBe('Argue a point.');
		expect(payload?.score_max).toBe(10);
		expect(payload?.challenge_focus_keys).toEqual([]);
		expect(payload?.rubric_schema.criteria.map((criterion) => criterion.max_score)).toEqual([6, 4]);
	});

	it('keeps challenge focus when the reader check is on', () => {
		const { payload } = buildAssignmentPayload(draft({ challengeEnabled: true }), t);
		expect(payload?.challenge_focus_keys).toEqual(['criterion_1']);
	});

	it('reports the first problem in form order', () => {
		expect(buildAssignmentPayload(draft({ title: ' ' }), t).error).toBe(
			'Assignment title is required.'
		);
		expect(buildAssignmentPayload(draft({ dueAt: '' }), t).error).toBe(
			'Assignment due time is required.'
		);
		expect(buildAssignmentPayload(draft({ scoreMax: '9.5' }), t).error).toBe(
			'Maximum score must be a positive whole number.'
		);
		expect(buildAssignmentPayload(draft({ scoreMax: '12' }), t).error).toBe(
			'Rubric maximum scores must add up to the assignment maximum.'
		);
	});
});
