import { describe, expect, test } from 'vitest';

import {
	applySourceMapChange,
	provenanceSegmentsToSourceRuns,
	sourceRunsToProvenanceSegments,
	type SourceRun
} from './writing-source-map';

describe('writing source map', () => {
	test('attributes full assistant insertion to ai_inserted', () => {
		const runs = applySourceMapChange({
			previousText: '',
			nextText: 'AI draft',
			runs: [],
			source: { sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		});

		expect(runs).toEqual([
			{
				startOffset: 0,
				endOffset: 8,
				sourceType: 'ai_inserted',
				sourceMessageId: 'message-1'
			}
		]);
	});

	test('keeps original AI attribution when typed text is inserted in the middle', () => {
		const runs: SourceRun[] = [
			{ startOffset: 0, endOffset: 6, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		];

		const nextRuns = applySourceMapChange({
			previousText: 'abcdef',
			nextText: 'abcXXdef',
			runs,
			source: { sourceType: 'user_typed' }
		});

		expect(nextRuns).toEqual([
			{ startOffset: 0, endOffset: 3, sourceType: 'ai_inserted', sourceMessageId: 'message-1' },
			{ startOffset: 3, endOffset: 5, sourceType: 'user_typed', sourceMessageId: null },
			{ startOffset: 5, endOffset: 8, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		]);
	});

	test('attributes external paste replacement without double-counting replaced AI text', () => {
		const runs: SourceRun[] = [
			{ startOffset: 0, endOffset: 6, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		];

		const nextRuns = applySourceMapChange({
			previousText: 'abcdef',
			nextText: 'abPASTEef',
			runs,
			source: { sourceType: 'external_paste' }
		});

		expect(nextRuns).toEqual([
			{ startOffset: 0, endOffset: 2, sourceType: 'ai_inserted', sourceMessageId: 'message-1' },
			{ startOffset: 2, endOffset: 7, sourceType: 'external_paste', sourceMessageId: null },
			{ startOffset: 7, endOffset: 9, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		]);
	});

	test('does not change attribution for formatting-only updates', () => {
		const runs: SourceRun[] = [
			{ startOffset: 0, endOffset: 6, sourceType: 'user_typed', sourceMessageId: null }
		];

		const nextRuns = applySourceMapChange({
			previousText: 'abcdef',
			nextText: 'abcdef',
			runs,
			source: { sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		});

		expect(nextRuns).toEqual(runs);
	});

	test('serializes final source runs as exact provenance segments', () => {
		const segments = sourceRunsToProvenanceSegments('abcXXdef', [
			{ startOffset: 0, endOffset: 3, sourceType: 'ai_inserted', sourceMessageId: 'message-1' },
			{ startOffset: 3, endOffset: 5, sourceType: 'user_typed', sourceMessageId: null },
			{ startOffset: 5, endOffset: 8, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		]);

		expect(segments).toEqual([
			expect.objectContaining({
				segment_id: 'source-map-0',
				source_type: 'ai_inserted',
				segment_text: 'abc',
				start_offset: 0,
				end_offset: 3,
				source_message_id: 'message-1',
				metadata_json: { provenance_kind: 'source_map' }
			}),
			expect.objectContaining({
				segment_id: 'source-map-1',
				source_type: 'user_typed',
				segment_text: 'XX',
				start_offset: 3,
				end_offset: 5,
				source_message_id: null,
				metadata_json: { provenance_kind: 'source_map' }
			}),
			expect.objectContaining({
				segment_id: 'source-map-2',
				source_type: 'ai_inserted',
				segment_text: 'def',
				start_offset: 5,
				end_offset: 8,
				source_message_id: 'message-1',
				metadata_json: { provenance_kind: 'source_map' }
			})
		]);
	});

	test('restores source runs from saved source-map provenance segments', () => {
		const runs = provenanceSegmentsToSourceRuns('abcXXdef', [
			{
				segment_id: 'source-map-0',
				source_type: 'ai_inserted',
				segment_text: 'abc',
				start_offset: 0,
				end_offset: 3,
				source_message_id: 'message-1',
				metadata_json: { provenance_kind: 'source_map' }
			},
			{
				segment_id: 'source-map-1',
				source_type: 'user_typed',
				segment_text: 'XX',
				start_offset: 3,
				end_offset: 5,
				source_message_id: null,
				metadata_json: { provenance_kind: 'source_map' }
			},
			{
				segment_id: 'not-source-map',
				source_type: 'external_paste',
				segment_text: 'ignored',
				start_offset: 0,
				end_offset: 7,
				source_message_id: null,
				metadata_json: null
			},
			{
				segment_id: 'source-map-2',
				source_type: 'ai_inserted',
				segment_text: 'def',
				start_offset: 5,
				end_offset: 8,
				source_message_id: 'message-1',
				metadata_json: { provenance_kind: 'source_map' }
			}
		]);

		expect(runs).toEqual([
			{ startOffset: 0, endOffset: 3, sourceType: 'ai_inserted', sourceMessageId: 'message-1' },
			{ startOffset: 3, endOffset: 5, sourceType: 'user_typed', sourceMessageId: null },
			{ startOffset: 5, endOffset: 8, sourceType: 'ai_inserted', sourceMessageId: 'message-1' }
		]);
	});
});
