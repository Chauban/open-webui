// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import ReviewResultCard from './ReviewResultCard.svelte';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const assignment = {
	score_max: 40,
	rubric_schema: { criteria: [
		{ key: 'structure', label: '结构', max_score: 15 },
		{ key: 'evidence', label: '论据', max_score: 25 }
	] }
};

test('uses teacher labels, schema order and custom maxima, including zero scores', () => {
	render(ReviewResultCard, { props: { assignment, review: {
		round_no: 2, submitted_at: 1, reviewed_at: 2, review_status: 'reviewed',
		score: 12, rubric: { evidence: 0, structure: 12 }
	} }, context });
	expect(screen.getByText('12/40')).toBeTruthy();
	expect(screen.getByText('结构 12/15')).toBeTruthy();
	expect(screen.getByText('论据 0/25')).toBeTruthy();
	expect(screen.queryByText('structure: 12')).toBeNull();
});

test('does not fabricate scores for a reviewed submission without scores', () => {
	render(ReviewResultCard, { props: { assignment, review: {
		round_no: 1, submitted_at: 1, review_status: 'reviewed',
		score: null, rubric: null, overall_comment: '请补充例子'
	} }, context });
	expect(screen.getByText('请补充例子')).toBeTruthy();
	expect(screen.queryByText(/\/40/)).toBeNull();
});
