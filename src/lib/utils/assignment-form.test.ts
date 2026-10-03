import { describe, expect, it } from 'vitest';

import {
	buildAssignmentPayload,
	getDefaultRubricCriteria,
	isSameRubric,
	rubricTotal,
	type AssignmentDraft
} from './assignment-form';

const t = (key: string) => key;

const draft = (overrides: Partial<AssignmentDraft> = {}): AssignmentDraft => ({
	title: '  Essay 1 ',
	description: ' Argue a point. ',
	dueAt: '2030-01-01T23:59',
	scoreMax: '10',
	coachingStyle: 'balanced',
	taskMode: 'from_scratch',
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

	it('drops the reader check for revise-draft assignments', () => {
		const { payload } = buildAssignmentPayload(
			draft({ taskMode: 'revise_draft', challengeEnabled: true }),
			t
		);
		expect(payload?.task_mode).toBe('revise_draft');
		expect(payload?.challenge_enabled).toBe(false);
		expect(payload?.challenge_focus_keys).toEqual([]);
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

describe('getDefaultRubricCriteria', () => {
	it('falls back to the built-in three criteria when the instance set none', () => {
		const criteria = getDefaultRubricCriteria({ revise_draft: [] }, 'revise_draft', t);
		expect(criteria.map((criterion) => criterion.label)).toEqual(['Ideas', 'Structure', 'Evidence']);
		expect(rubricTotal(criteria)).toBe('100');
	});

	it('uses the instance default for that assignment type, with fresh keys', () => {
		const criteria = getDefaultRubricCriteria(
			{ revise_draft: [{ label: '综述只写已有研究', max_score: 10 }, { label: '出处与参考文献', max_score: 15 }] },
			'revise_draft',
			t
		);
		expect(criteria).toEqual([
			{ key: 'criterion_1', label: '综述只写已有研究', maxScore: '10' },
			{ key: 'criterion_2', label: '出处与参考文献', maxScore: '15' }
		]);
		expect(rubricTotal(criteria)).toBe('25');
		expect(isSameRubric(criteria, getDefaultRubricCriteria(undefined, 'revise_draft', t))).toBe(false);
	});
});
