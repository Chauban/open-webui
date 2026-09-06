import { describe, expect, test } from 'vitest';
import { getWritingComposition } from './writing-composition';
import {
	applySourceMapChange,
	provenanceSegmentsToSourceRuns,
	sourceRunsToProvenanceSegments,
	type SourceRun
} from './writing-source-map';

describe('current draft composition', () => {
	test('keeps external and unrecorded sources separate from typed and AI text', () => {
		const sources = [
			'user_typed', 'ai_inserted', 'ai_pasted', 'external_paste',
			'unknown', 'suspected_unmarked_import'
		] as const;
		const runs = sources.map((sourceType, i) => ({
			startOffset: i * 10, endOffset: (i + 1) * 10, sourceType
		}));
		const result = getWritingComposition(runs);
		expect(result.total).toBe(60);
		expect(result.categories.map(({ key, count, percent }) => ({ key, count, percent }))).toEqual([
			{ key: 'user_typed', count: 10, percent: 16.7 },
			{ key: 'ai_inserted', count: 10, percent: 16.7 },
			{ key: 'ai_pasted', count: 10, percent: 16.7 },
			{ key: 'external_paste', count: 10, percent: 16.7 },
			{ key: 'unknown', count: 20, percent: 33.3 }
		]);
	});

	test('recalculates after replacement, survives reload, and clears after deletion', () => {
		const initial: SourceRun[] = [
			{ startOffset: 0, endOffset: 10, sourceType: 'ai_inserted' }
		];
		const next = applySourceMapChange({
			previousText: 'abcdefghij', nextText: 'abcd自写', runs: initial,
			source: { sourceType: 'user_typed' }
		});
		const composition = getWritingComposition(next);
		expect(composition.categories.map(({ count }) => count)).toEqual([2, 4, 0]);
		expect(getWritingComposition(provenanceSegmentsToSourceRuns(
			'abcd自写', sourceRunsToProvenanceSegments('abcd自写', next)
		))).toEqual(composition);
		const cleared = getWritingComposition(applySourceMapChange({
			previousText: 'abcd自写', nextText: '', runs: next
		}));
		expect(cleared.total).toBe(0);
		expect(cleared.categories.every(({ percent }) => percent === 0)).toBe(true);
	});
});
