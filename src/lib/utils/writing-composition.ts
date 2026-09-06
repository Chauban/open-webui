import type { SourceRun, WritingSourceType } from './writing-source-map';

export const getWritingComposition = (runs: SourceRun[]) => {
	const counts: Record<WritingSourceType, number> = {
		user_typed: 0,
		ai_inserted: 0,
		ai_pasted: 0,
		external_paste: 0,
		suspected_unmarked_import: 0,
		unknown: 0
	};
	for (const run of runs) {
		counts[run.sourceType] += run.endOffset - run.startOffset;
	}
	const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
	const categories = [
		{ key: 'user_typed', label: 'Typed by you', count: counts.user_typed },
		{ key: 'ai_inserted', label: 'AI inserted', count: counts.ai_inserted },
		{ key: 'ai_pasted', label: 'AI pasted', count: counts.ai_pasted },
		{ key: 'external_paste', label: 'External paste', count: counts.external_paste },
		{
			key: 'unknown',
			label: 'Source not recorded',
			count: counts.unknown + counts.suspected_unmarked_import
		}
	];
	return {
		total,
		categories: categories
			.filter((category, index) => index < 3 || category.count > 0)
			.map((category) => ({
				...category,
				percent: total === 0 ? 0 : Math.round((category.count / total) * 1000) / 10
			}))
	};
};
