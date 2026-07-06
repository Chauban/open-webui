export type WritingSourceType =
	| 'ai_inserted'
	| 'ai_pasted'
	| 'user_typed'
	| 'external_paste'
	| 'suspected_unmarked_import'
	| 'unknown';

export type SourceRun = {
	startOffset: number;
	endOffset: number;
	sourceType: WritingSourceType;
	sourceMessageId?: string | null;
};

type SourceInput = {
	sourceType?: string | null;
	sourceMessageId?: string | null;
};

type ApplySourceMapChangeInput = {
	previousText: string;
	nextText: string;
	runs: SourceRun[];
	source?: SourceInput | null;
};

type ProvenanceSegmentLike = {
	source_type?: string | null;
	source_message_id?: string | null;
	segment_text?: string | null;
	start_offset?: number | null;
	end_offset?: number | null;
	metadata_json?: Record<string, unknown> | null;
};

const SOURCE_TYPES = new Set<WritingSourceType>([
	'ai_inserted',
	'ai_pasted',
	'user_typed',
	'external_paste',
	'suspected_unmarked_import',
	'unknown'
]);

const normalizeSourceType = (value?: string | null): WritingSourceType => {
	if (value === 'paste') return 'external_paste';
	if (value && SOURCE_TYPES.has(value as WritingSourceType)) return value as WritingSourceType;
	return 'user_typed';
};

const sameSource = (left: SourceRun, right: SourceRun) =>
	left.sourceType === right.sourceType &&
	(left.sourceMessageId ?? null) === (right.sourceMessageId ?? null);

export const normalizeSourceRuns = (runs: SourceRun[], textLength: number): SourceRun[] => {
	if (textLength <= 0) return [];

	const sorted = [...runs]
		.map((run) => ({
			...run,
			startOffset: Math.max(0, Math.min(textLength, run.startOffset)),
			endOffset: Math.max(0, Math.min(textLength, run.endOffset)),
			sourceMessageId: run.sourceMessageId ?? null
		}))
		.filter((run) => run.endOffset > run.startOffset)
		.sort((left, right) => left.startOffset - right.startOffset || left.endOffset - right.endOffset);

	const filled: SourceRun[] = [];
	let cursor = 0;

	for (const run of sorted) {
		if (run.endOffset <= cursor) continue;
		if (run.startOffset > cursor) {
			filled.push({
				startOffset: cursor,
				endOffset: run.startOffset,
				sourceType: 'unknown',
				sourceMessageId: null
			});
		}

		filled.push({
			...run,
			startOffset: Math.max(run.startOffset, cursor)
		});
		cursor = Math.max(cursor, run.endOffset);
	}

	if (cursor < textLength) {
		filled.push({
			startOffset: cursor,
			endOffset: textLength,
			sourceType: 'unknown',
			sourceMessageId: null
		});
	}

	return filled.reduce<SourceRun[]>((merged, run) => {
		const previous = merged.at(-1);
		if (previous && previous.endOffset === run.startOffset && sameSource(previous, run)) {
			previous.endOffset = run.endOffset;
			return merged;
		}
		merged.push({ ...run });
		return merged;
	}, []);
};

const diffTexts = (previousText: string, nextText: string) => {
	if (previousText === nextText) return null;

	let startOffset = 0;
	while (
		startOffset < previousText.length &&
		startOffset < nextText.length &&
		previousText[startOffset] === nextText[startOffset]
	) {
		startOffset += 1;
	}

	let previousEnd = previousText.length - 1;
	let nextEnd = nextText.length - 1;
	while (
		previousEnd >= startOffset &&
		nextEnd >= startOffset &&
		previousText[previousEnd] === nextText[nextEnd]
	) {
		previousEnd -= 1;
		nextEnd -= 1;
	}

	return {
		startOffset,
		previousEndOffset: previousEnd + 1,
		nextEndOffset: nextEnd + 1,
		insertedLength: Math.max(nextEnd - startOffset + 1, 0)
	};
};

export const applySourceMapChange = ({
	previousText,
	nextText,
	runs,
	source
}: ApplySourceMapChangeInput): SourceRun[] => {
	const diff = diffTexts(previousText, nextText);
	if (!diff) return normalizeSourceRuns(runs, nextText.length);

	const previousRuns = normalizeSourceRuns(runs, previousText.length);
	const delta = nextText.length - previousText.length;
	const transformed: SourceRun[] = [];

	for (const run of previousRuns) {
		if (run.endOffset <= diff.startOffset) {
			transformed.push({ ...run });
			continue;
		}

		if (run.startOffset >= diff.previousEndOffset) {
			transformed.push({
				...run,
				startOffset: run.startOffset + delta,
				endOffset: run.endOffset + delta
			});
			continue;
		}

		if (run.startOffset < diff.startOffset) {
			transformed.push({
				...run,
				endOffset: diff.startOffset
			});
		}

		if (run.endOffset > diff.previousEndOffset) {
			const retainedLength = run.endOffset - diff.previousEndOffset;
			transformed.push({
				...run,
				startOffset: diff.startOffset + diff.insertedLength,
				endOffset: diff.startOffset + diff.insertedLength + retainedLength
			});
		}
	}

	if (diff.insertedLength > 0) {
		transformed.push({
			startOffset: diff.startOffset,
			endOffset: diff.startOffset + diff.insertedLength,
			sourceType: normalizeSourceType(source?.sourceType),
			sourceMessageId: source?.sourceMessageId ?? null
		});
	}

	return normalizeSourceRuns(transformed, nextText.length);
};

export const sourceRunsToProvenanceSegments = (text: string, runs: SourceRun[]) => {
	return normalizeSourceRuns(runs, text.length).map((run, index) => ({
		segment_id: `source-map-${index}`,
		source_type: run.sourceType,
		segment_text: text.slice(run.startOffset, run.endOffset),
		source_message_id: run.sourceMessageId ?? null,
		start_offset: run.startOffset,
		end_offset: run.endOffset,
		metadata_json: {
			provenance_kind: 'source_map'
		}
	}));
};

export const provenanceSegmentsToSourceRuns = (
	text: string,
	segments: ProvenanceSegmentLike[] = []
): SourceRun[] => {
	const runs = segments
		.filter((segment) => segment.metadata_json?.provenance_kind === 'source_map')
		.map((segment) => ({
			startOffset: segment.start_offset ?? -1,
			endOffset: segment.end_offset ?? -1,
			sourceType: normalizeSourceType(segment.source_type),
			sourceMessageId: segment.source_message_id ?? null,
			segmentText: segment.segment_text ?? ''
		}))
		.filter(
			(run) =>
				run.startOffset >= 0 &&
				run.endOffset > run.startOffset &&
				run.endOffset <= text.length &&
				text.slice(run.startOffset, run.endOffset) === run.segmentText
		)
		.map(({ segmentText, ...run }) => run);

	return normalizeSourceRuns(runs, text.length);
};
