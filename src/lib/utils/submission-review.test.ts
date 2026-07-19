import { describe, expect, test } from 'vitest';

import { buildSubmissionReviewOverview } from './submission-review';

describe('buildSubmissionReviewOverview', () => {
	test('summarizes teacher-facing metrics and uses neutral process focus wording', () => {
		const overview = buildSubmissionReviewOverview({
			analysisSummary: {
				total_chars: 1000,
				typed_chars: 320,
				ai_inserted_chars: 420,
				ai_pasted_chars: 180,
				external_paste_chars: 80,
				unknown_chars: 0,
				suspected_unmarked_import_count: 2,
				burst_count: 3,
				average_rewrite_ratio: 18,
				prompt_count: 9,
				version_count: 14
			},
			stats: {}
		});

		expect(overview.totalChars).toBe(1000);
		expect(overview.typedPercent).toBe(32);
		expect(overview.aiInsertedPercent).toBe(42);
		expect(overview.aiPastedPercent).toBe(18);
		expect(overview.externalPasteChars).toBe(80);
		expect(overview.externalPastePercent).toBe(8);
		expect(overview.unknownChars).toBe(0);
		expect(overview.focusLabel).toBe('Needs close review');
		expect(overview.focusReasons).toEqual([
			'High AI participation',
			'Unmarked imported segments present',
			'Large text bursts present',
			'Low average rewrite ratio'
		]);
	});

	test('returns an information state when there is no measurable text', () => {
		const overview = buildSubmissionReviewOverview({
			analysisSummary: {},
			stats: {}
		});

		expect(overview.totalChars).toBe(0);
		expect(overview.focusLabel).toBe('Insufficient data');
		expect(overview.focusReasons).toEqual(['No process data available yet']);
	});
});
