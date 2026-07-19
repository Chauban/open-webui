type NumericRecord = Record<string, number | null | undefined>;

type SubmissionReviewOverviewInput = {
	analysisSummary?: NumericRecord;
	stats?: NumericRecord;
};

export type SubmissionReviewOverview = {
	totalChars: number;
	typedChars: number;
	aiInsertedChars: number;
	aiPastedChars: number;
	externalPasteChars: number;
	unknownChars: number;
	suspectedUnmarkedImportCount: number;
	burstCount: number;
	averageRewriteRatio: number;
	promptCount: number;
	versionCount: number;
	typedPercent: number;
	aiInsertedPercent: number;
	aiPastedPercent: number;
	externalPastePercent: number;
	unknownPercent: number;
	focusLabel: string;
	focusReasons: string[];
};

const numberFrom = (...values: Array<number | null | undefined>) => {
	for (const value of values) {
		if (typeof value === 'number' && Number.isFinite(value)) {
			return value;
		}
	}

	return 0;
};

const percentOf = (value: number, total: number) => {
	if (total <= 0) {
		return 0;
	}

	return Math.round((value / total) * 100);
};

export const buildSubmissionReviewOverview = ({
	analysisSummary = {},
	stats = {}
}: SubmissionReviewOverviewInput): SubmissionReviewOverview => {
	const totalChars = numberFrom(analysisSummary.total_chars, stats.total_chars);
	const typedChars = numberFrom(analysisSummary.typed_chars, stats.user_typed_chars);
	const aiInsertedChars = numberFrom(analysisSummary.ai_inserted_chars, stats.ai_inserted_chars);
	const aiPastedChars = numberFrom(analysisSummary.ai_pasted_chars, stats.ai_pasted_chars);
	const externalPasteChars = numberFrom(
		analysisSummary.external_paste_chars,
		stats.external_paste_chars,
		analysisSummary.suspected_unmarked_import_chars,
		stats.suspected_unmarked_import_chars
	);
	const unknownChars = numberFrom(analysisSummary.unknown_chars, stats.unknown_chars);
	const suspectedUnmarkedImportCount = numberFrom(analysisSummary.suspected_unmarked_import_count);
	const burstCount = numberFrom(analysisSummary.burst_count);
	const averageRewriteRatio = numberFrom(analysisSummary.average_rewrite_ratio);
	const promptCount = numberFrom(analysisSummary.prompt_count, stats.prompt_count);
	const versionCount = numberFrom(analysisSummary.version_count, stats.version_count);
	const aiParticipationPercent = percentOf(aiInsertedChars + aiPastedChars, totalChars);

	const focusReasons: string[] = [];

	if (totalChars <= 0) {
		focusReasons.push('No process data available yet');
	} else {
		if (aiParticipationPercent >= 50) {
			focusReasons.push('High AI participation');
		}
		if (suspectedUnmarkedImportCount > 0) {
			focusReasons.push('Unmarked imported segments present');
		}
		if (burstCount > 0) {
			focusReasons.push('Large text bursts present');
		}
		if (averageRewriteRatio > 0 && averageRewriteRatio < 25) {
			focusReasons.push('Low average rewrite ratio');
		}
		if (promptCount >= 8) {
			focusReasons.push('Many prompt interactions');
		}
	}

	let focusLabel = 'No notable focus points';

	if (totalChars <= 0) {
		focusLabel = 'Insufficient data';
	} else if (
		suspectedUnmarkedImportCount > 0 ||
		aiParticipationPercent >= 60 ||
		(averageRewriteRatio > 0 && averageRewriteRatio < 20)
	) {
		focusLabel = 'Needs close review';
	} else if (focusReasons.length > 0) {
		focusLabel = 'Worth reviewing';
	}

	return {
		totalChars,
		typedChars,
		aiInsertedChars,
		aiPastedChars,
		externalPasteChars,
		unknownChars,
		suspectedUnmarkedImportCount,
		burstCount,
		averageRewriteRatio,
		promptCount,
		versionCount,
		typedPercent: percentOf(typedChars, totalChars),
		aiInsertedPercent: percentOf(aiInsertedChars, totalChars),
		aiPastedPercent: percentOf(aiPastedChars, totalChars),
		externalPastePercent: percentOf(externalPasteChars, totalChars),
		unknownPercent: percentOf(unknownChars, totalChars),
		focusLabel,
		focusReasons: focusReasons.slice(0, 4)
	};
};
