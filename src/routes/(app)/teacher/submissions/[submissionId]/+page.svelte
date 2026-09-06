<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';

	import {
		getSubmissionAnalysisSegmentDetail,
		getSubmissionRoundDiff,
		getSubmissionVersions,
		getTeacherReview,
		getSubmissionChallenge,
		getTeacherSubmissionDetail,
		recomputeSubmissionAnalysis,
		saveSubmissionReview
	} from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import SourceHighlightedText from '$lib/components/education/SourceHighlightedText.svelte';
	import EduEvidenceDisclaimer from '$lib/components/education/EduEvidenceDisclaimer.svelte';
	import ChallengeRounds from '$lib/components/education/ChallengeRounds.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import { buildSubmissionReviewOverview } from '$lib/utils/submission-review';
	import {
		formatDateTimeInput,
		formatEpoch,
		formatEpochTime,
		getAiHelpTypeLabel,
		resolveErrorMessage,
		toLocalDateTimeInput
	} from '$lib/utils/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduDateTimeField from '$lib/components/education/EduDateTimeField.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const DEFAULT_VISIBLE_VERSIONS = 10;
	const getReviewTriggerTypeLabel = (value: string) =>
		(
			({
				autosave: t('Autosave'),
				submit: t('Submit'),
				submit_preflight: t('Submit Preflight')
			}) as Record<string, string>
		)[value] || value;
	const getTimelineRoleLabel = (value: string) =>
		(
			({
				user: t('User'),
				assistant: t('AI'),
				system: t('System')
			}) as Record<string, string>
		)[value] || value;
	const reviewStatusOptions = [
		{ value: 'pending', label: 'Pending Review' },
		{ value: 'reviewed', label: 'Reviewed' },
		{ value: 'returned', label: 'Returned' }
	];

	let detail = null;
	let loaded = false;
	let loadError = '';
	let highlight = true;
	let reviewStatus = 'pending';
	let score = '';
	let overallComment = '';
	let rubricScores = {};
	let returnedComment = '';
	let saving = false;
	let showAllVersions = false;
	let showCoachingPrompt = false;
	let showUserTimeline = true;
	let showAssistantTimeline = true;
	let showAnalysisTimeline = true;
	let showAutosaveTimeline = false;
	let activeSegmentId = '';
	let activeSegmentDetail = null;

	// New state
	let activeTab: 'review' | 'analysis' | 'reflection' = 'review';
	let expandedSegmentId = '';
	let lastSavedAt: Date | null = null;
	let expandedTimelineIds: Set<number> = new Set();
	let resubmitDueLocal = '';
	let diffData: any = null;
	let diffLoading = false;
	let loadSeq = 0;
	let diffSeq = 0;

	// Pending-queue navigation (prev / next / save-and-next)
	let queueIds: string[] = [];
	let fullVersions = null;
	let loadingVersions = false;
	let recomputing = false;

	const toEpoch = (v: string) => (v ? Math.floor(new Date(v).getTime() / 1000) : null);
	// datetime-local expects a LOCAL "YYYY-MM-DDTHH:mm" string; toISOString() would shift to UTC.

	$: submissionId = $page.params.submissionId;
	$: resubmitDuePreview = formatDateTimeInput(resubmitDueLocal);
	$: isHistoricalRound = detail ? !detail.submission.is_current : false;

	$: queueIndex = queueIds.indexOf(submissionId);
	$: prevPendingId = queueIndex > 0 ? queueIds[queueIndex - 1] : null;
	$: nextPendingId =
		queueIds.length === 0
			? null
			: queueIndex === -1
				? queueIds[0]
				: (queueIds[queueIndex + 1] ?? null);

	$: totalVersionCount = detail?.version_count ?? detail?.versions?.length ?? 0;
	$: baseVersions = showAllVersions && fullVersions ? fullVersions : (detail?.versions ?? []);
	$: sortedVersions = [...baseVersions].sort((a, b) => b.version_no - a.version_no);
	$: visibleVersions = showAllVersions
		? sortedVersions
		: sortedVersions.slice(0, DEFAULT_VISIBLE_VERSIONS);
	$: hiddenVersionCount = Math.max(totalVersionCount - visibleVersions.length, 0);
	$: analysisSummary = detail?.analysis?.summary ?? {};
	$: analysisSegments = detail?.analysis?.segments ?? [];
	$: analysisTimeline = detail?.analysis?.timeline ?? [];
	$: analysisHighlights = detail?.analysis?.highlights ?? detail?.provenance_segments ?? [];
	// AI 的澄清追问：纯派生自聊天消息的 output，内置工具关掉时天然为空。
	// 模型拼错参数被后端拒掉的调用（status invalid）是噪声，不展示给教师。
	$: clarifications = (detail?.analysis?.clarifications ?? []).filter(
		(item) => item.status !== 'invalid'
	);
	$: clarificationSummary = analysisSummary?.process_summary ?? {};
	// 本轮提交时实际生效的辅导档位和原文（档位措辞管理员随时可改，所以随轮次冻存）。
	$: roundCoaching = detail?.submission?.stats_json?.coaching ?? null;
	$: coachingStyleLabel =
		{ socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' }[
			roundCoaching?.style
		] ?? null;
	$: segmentCharStats = (() => {
		if (!analysisHighlights.length) return null;
		let typed = 0, aiInserted = 0, aiPasted = 0, externalPaste = 0, unknown = 0;
		for (const seg of analysisHighlights) {
			const len = (seg.segment_text ?? '').length;
			if (seg.source_type === 'user_typed') typed += len;
			else if (seg.source_type === 'ai_inserted') aiInserted += len;
			else if (seg.source_type === 'ai_pasted') aiPasted += len;
			else if (seg.source_type === 'external_paste' || seg.source_type === 'suspected_unmarked_import') externalPaste += len;
			else if (seg.source_type === 'unknown') unknown += len;
		}
		return { typed, aiInserted, aiPasted, externalPaste, unknown };
	})();
	$: reviewOverview = buildSubmissionReviewOverview({
		analysisSummary: segmentCharStats
			? {
					...analysisSummary,
					typed_chars: segmentCharStats.typed,
					ai_inserted_chars: segmentCharStats.aiInserted,
					ai_pasted_chars: segmentCharStats.aiPasted,
					external_paste_chars: segmentCharStats.externalPaste,
					unknown_chars: segmentCharStats.unknown
				}
			: analysisSummary,
		stats: detail?.submission?.stats_json ?? {}
	});
	$: filteredPromptTimeline = (detail?.prompt_timeline ?? []).filter((item) => {
		if (item.role === 'user') return showUserTimeline;
		if (item.role === 'assistant') return showAssistantTimeline;
		return true;
	});
	$: unifiedTimeline = [
		...analysisTimeline
			.filter((item) => {
				const triggerType = item.source_type ?? item.trigger_type ?? item.event_type;
				if (triggerType === 'autosave') return showAutosaveTimeline;
				return showAnalysisTimeline;
			})
			.map((item) => ({
				kind: 'analysis',
				role: null,
				label: item.label ?? item.message ?? item.event_type,
				meta: item.source_type ?? item.trigger_type ?? item.event_type,
				created_at: item.created_at,
				inserted_length: item.inserted_length ?? null
			})),
		...filteredPromptTimeline.map((item) => ({
			kind: 'prompt',
			role: item.role,
			label: typeof item.content === 'string' ? item.content : JSON.stringify(item.content),
			meta: getTimelineRoleLabel(item.role),
			created_at: item.created_at,
			inserted_length: null
		}))
	].sort((a, b) => (a.created_at ?? 0) - (b.created_at ?? 0));

	$: lastSavedStr = lastSavedAt
		? formatEpochTime(Math.floor(lastSavedAt.getTime() / 1000))
		: null;

	// 维度分从高到低列出：批改时命中的多是接近满分的档位。
	const scoreOptions = (max: number) => Array.from({ length: max + 1 }, (_, index) => max - index);

	let challengeDetail = null;
	$: rubricCriteria = detail?.assignment?.rubric_schema?.criteria ?? [];
	$: criteriaLabels = Object.fromEntries(
		rubricCriteria.map((criterion) => [criterion.key, criterion.label])
	);
	$: rubricFilledCount = rubricCriteria.filter(
		(criterion) => (rubricScores[criterion.key] ?? '') !== ''
	).length;
	// 总分不再手填：评完全部维度才算出总分，否则留空（后端要求总分等于各维度之和）。
	$: score =
		rubricCriteria.length > 0 && rubricFilledCount === rubricCriteria.length
			? String(
					rubricCriteria.reduce((sum, criterion) => sum + Number(rubricScores[criterion.key]), 0)
				)
			: '';

	const syncReview = () => {
		const review = detail?.review;
		reviewStatus = review?.review_status || 'pending';
		overallComment = review?.overall_comment || '';
		rubricScores = Object.fromEntries(
			(detail?.assignment?.rubric_schema?.criteria ?? []).map((criterion) => [
				criterion.key,
				review?.rubric_scores?.[criterion.key] != null
					? String(review.rubric_scores[criterion.key])
					: ''
			])
		);
		returnedComment = review?.returned_comment || '';
		resubmitDueLocal = review?.resubmit_due_at ? toLocalDateTimeInput(review.resubmit_due_at) : '';
	};

	const saveReview = async (effectiveStatus: string) => {
		if (isHistoricalRound) return false;
		// 总分由各维度分求和得到，范围与「等于各维度之和」都无需再校验。
		const parsedScore = score === '' ? null : Number(score);
		// 下拉只能选出合法档位，这里只需分辨「全空 / 全填 / 填了一半」。
		const parsedRubricScores =
			rubricCriteria.length > 0 && rubricFilledCount === rubricCriteria.length
				? Object.fromEntries(
						rubricCriteria.map((criterion) => [
							criterion.key,
							Number(rubricScores[criterion.key])
						])
					)
				: null;
		if (rubricFilledCount > 0 && parsedRubricScores == null) {
			toast.error(t('Score every rubric criterion before saving.'));
			return false;
		}
		if (effectiveStatus === 'reviewed' && (parsedScore == null || parsedRubricScores == null)) {
			toast.error(t('Reviewed submissions require a total score and complete rubric scores.'));
			return false;
		}
		let resubmitDueAt: number | null = null;
		if (effectiveStatus === 'returned') {
			resubmitDueAt = toEpoch(resubmitDueLocal);
			if (!resubmitDueAt || resubmitDueAt <= Math.floor(Date.now() / 1000)) {
				toast.error(t('A future resubmit due time is required'));
				return false;
			}
		}

		saving = true;
		try {
			const response = await saveSubmissionReview(localStorage.token, $page.params.submissionId, {
				review_status: effectiveStatus,
				score: parsedScore,
				overall_comment: overallComment.trim(),
				rubric_scores: parsedRubricScores,
				returned_comment: returnedComment.trim(),
				resubmit_due_at: resubmitDueAt
			});
			detail.review = response;
			syncReview();
			lastSavedAt = new Date();
			toast.success(t('Review saved.'));
			return true;
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
			return false;
		} finally {
			saving = false;
		}
	};

	const saveReviewAndNext = async () => {
		const currentId = submissionId;
		const target = nextPendingId === currentId ? (queueIds[queueIndex + 1] ?? null) : nextPendingId;
		const saved = await saveReview('reviewed');
		if (!saved) return;
		queueIds = queueIds.filter((id) => id !== currentId);
		if (target) {
			goto(`/teacher/submissions/${target}`);
		} else {
			toast.success(t('Review queue is clear.'));
			goto('/teacher/review');
		}
	};

	const loadQueueContext = async () => {
		try {
			const res = await getTeacherReview(localStorage.token, {
				review_status: 'pending',
				sort: 'latest',
				limit: 200
			});
			queueIds = (res.items ?? []).map((item) => item.submission.id);
		} catch {
			queueIds = [];
		}
	};

	const recomputeAnalysis = async () => {
		if (recomputing || !detail) return;
		recomputing = true;
		try {
			await recomputeSubmissionAnalysis(localStorage.token, detail.submission.id);
			await loadDetail(detail.submission.id);
			toast.success(t('Analysis recomputed.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			recomputing = false;
		}
	};

	const toggleAllVersions = async () => {
		if (showAllVersions) {
			showAllVersions = false;
			return;
		}
		if (!fullVersions && totalVersionCount > (detail?.versions?.length ?? 0)) {
			loadingVersions = true;
			try {
				fullVersions = await getSubmissionVersions(localStorage.token, detail.submission.id);
			} catch (error) {
				toast.error(resolveErrorMessage(error, t));
				loadingVersions = false;
				return;
			}
			loadingVersions = false;
		}
		showAllVersions = true;
	};

	const loadDiff = async () => {
		if (diffLoading) return;
		const seq = ++diffSeq;
		diffLoading = true;
		try {
			const response = await getSubmissionRoundDiff(localStorage.token, detail.submission.id);
			if (seq !== diffSeq) return;
			diffData = response;
		} catch (error) {
			if (seq !== diffSeq) return;
			toast.error(resolveErrorMessage(error, t));
		} finally {
			diffLoading = false;
		}
	};

	const toggleTimelineItem = (idx: number) => {
		if (expandedTimelineIds.has(idx)) {
			expandedTimelineIds.delete(idx);
		} else {
			expandedTimelineIds.add(idx);
		}
		expandedTimelineIds = expandedTimelineIds;
	};

	const focusSegment = async (segmentId: string) => {
		if (expandedSegmentId === segmentId) {
			expandedSegmentId = '';
			activeSegmentId = '';
			activeSegmentDetail = null;
			return;
		}
		expandedSegmentId = segmentId;
		activeSegmentId = segmentId;
		activeSegmentDetail = null;
		try {
			activeSegmentDetail = await getSubmissionAnalysisSegmentDetail(
				localStorage.token,
				$page.params.submissionId,
				segmentId
			);
		} catch (error) {
			activeSegmentDetail = null;
			toast.error(resolveErrorMessage(error, t));
		}
		requestAnimationFrame(() => {
			const target = document.querySelector(`[data-segment-id="${segmentId}"]`);
			target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
		});
	};

	const loadDetail = async (id: string) => {
		const seq = ++loadSeq;
		++diffSeq; // invalidate any in-flight diff response for the previous round
		loaded = false;
		loadError = '';
		diffData = null;
		expandedSegmentId = '';
		activeSegmentId = '';
		activeSegmentDetail = null;
		expandedTimelineIds = new Set();
		fullVersions = null;
		try {
			const response = await getTeacherSubmissionDetail(localStorage.token, id);
			if (seq !== loadSeq) return;
			detail = response;
			showAllVersions = false;
			syncReview();
			try {
				const challenge = await getSubmissionChallenge(localStorage.token, id);
				if (seq === loadSeq) {
					challengeDetail = challenge;
				}
			} catch (error) {
				// 试读读不出来不该挡住整个批改页，这一块不渲染即可。
				if (seq === loadSeq) {
					challengeDetail = null;
				}
			}
		} catch (error) {
			if (seq !== loadSeq) return;
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			if (seq === loadSeq) {
				loaded = true;
			}
		}
	};

	$: if (submissionId) {
		loadDetail(submissionId);
	}

	onMount(() => {
		loadQueueContext();
	});
</script>

<TeacherPageShell
	crumbs={[
		{ label: $i18n.t('Teaching') },
		{ label: $i18n.t('Review'), href: '/teacher/review' }
	]}
	title={detail?.student_name ?? $i18n.t('Submission Review')}
>
	{#if loaded && detail}
		<!-- h-full + overflow-hidden prevents the shell's overflow-y-auto from activating -->
		<div class="flex h-full flex-col overflow-hidden">

			<!-- ── Compact fixed header ── -->
			<div class="shrink-0 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 px-6 py-3 space-y-3">
				<TeacherSectionNav />

				<div class="flex flex-wrap items-center justify-between gap-2">
					<button
						class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-800 dark:hover:text-gray-200"
						on:click={() => goto('/teacher/review')}
					>
						&larr; {$i18n.t('Back to review queue')}
					</button>
					<div class="flex items-center gap-1.5">
						<EduButton
							size="sm"
							disabled={!prevPendingId}
							on:click={() => prevPendingId && goto(`/teacher/submissions/${prevPendingId}`)}
						>
							&larr; {$i18n.t('Previous pending')}
						</EduButton>
						<EduButton
							size="sm"
							disabled={!nextPendingId}
							on:click={() => nextPendingId && goto(`/teacher/submissions/${nextPendingId}`)}
						>
							{$i18n.t('Next pending')} &rarr;
						</EduButton>
					</div>
				</div>

				<!-- Title row + 过程关注点 -->
				<div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
					<div>
						<div class="text-xs uppercase tracking-[0.2em] text-gray-400">
							{$i18n.t('Submission Review')}
						</div>
						<div class="mt-0.5 text-xl font-semibold text-gray-950 dark:text-gray-100">{detail.assignment.title}</div>
						<div class="mt-1.5 flex flex-wrap gap-1.5 text-xs text-gray-600 dark:text-gray-400">
							<span class="rounded-full bg-gray-100 dark:bg-gray-800 px-3 py-1">{detail.student_name}</span>
							<span class="rounded-full bg-gray-100 dark:bg-gray-800 px-3 py-1">
								{$i18n.t('Submitted At')}: {formatEpoch(detail.submission.submitted_at)}
							</span>
							<span
								class="rounded-full px-3 py-1 {reviewStatus === 'reviewed'
									? 'bg-emerald-100 text-emerald-700 dark:text-emerald-300'
									: reviewStatus === 'returned'
										? 'bg-amber-100 text-amber-700 dark:text-amber-300'
										: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}"
							>
								{$i18n.t(
									reviewStatusOptions.find((o) => o.value === reviewStatus)?.label ??
										'Pending Review'
								)}
							</span>
						</div>
						{#if detail?.rounds?.length > 1}
							<div class="mt-2 flex flex-wrap gap-1.5 items-center">
								{#each detail.rounds as round}
									<a
										href={`/teacher/submissions/${round.submission_id}`}
										class="px-2.5 py-1 rounded-lg text-sm border
											{round.submission_id === detail.submission.id
											? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
											: 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'}"
									>
										{$i18n.t('Round {{round}}', { round: round.round_no })}
										{#if !round.is_current}<span class="opacity-60"> · {$i18n.t('History')}</span>{/if}
									</a>
								{/each}
							</div>
						{/if}
					</div>
					<div class="shrink-0 rounded-2xl border border-cyan-100 bg-cyan-50 px-4 py-3 lg:min-w-60">
						<div class="text-[10px] uppercase tracking-[0.14em] text-cyan-600" title={$i18n.t('A heuristic pointer for where to look first, not a conclusion.')}>{$i18n.t('Process Focus')}</div>
						<div class="mt-0.5 text-base font-semibold text-cyan-950">{$i18n.t(reviewOverview.focusLabel)}</div>
						<div class="mt-1.5 flex flex-wrap gap-1.5">
							{#each reviewOverview.focusReasons as reason}
								<span class="rounded-full bg-white dark:bg-gray-850 px-2.5 py-0.5 text-xs text-cyan-800">{$i18n.t(reason)}</span>
							{/each}
						</div>
					</div>
				</div>

				<!-- Stats row -->
				<div class="grid grid-cols-2 gap-2 md:grid-cols-7">
					<div class="rounded-xl bg-gray-50 dark:bg-gray-800 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-gray-400">{$i18n.t('Total characters')}</div>
						<div class="mt-0.5 text-base font-semibold text-gray-950 dark:text-gray-100">{reviewOverview.totalChars}</div>
					</div>
					<div class="rounded-xl bg-emerald-50 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-emerald-500">{$i18n.t('Typed')}</div>
						<div class="mt-0.5 text-base font-semibold text-emerald-950">
							{reviewOverview.typedChars}
							<span class="text-xs font-medium text-emerald-500">({reviewOverview.typedPercent}%)</span>
						</div>
					</div>
					<div class="rounded-xl bg-amber-50 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-amber-500">{$i18n.t('AI inserted')}</div>
						<div class="mt-0.5 text-base font-semibold text-amber-950">
							{reviewOverview.aiInsertedChars}
							<span class="text-xs font-medium text-amber-500">({reviewOverview.aiInsertedPercent}%)</span>
						</div>
					</div>
					<div class="rounded-xl bg-sky-50 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-sky-500">{$i18n.t('AI pasted')}</div>
						<div class="mt-0.5 text-base font-semibold text-sky-950">
							{reviewOverview.aiPastedChars}
							<span class="text-xs font-medium text-sky-500">({reviewOverview.aiPastedPercent}%)</span>
						</div>
					</div>
					<div class="rounded-xl bg-rose-50 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-rose-500">{$i18n.t('External paste')}</div>
						<div class="mt-0.5 text-base font-semibold text-rose-950">
							{reviewOverview.externalPasteChars}
							<span class="text-xs font-medium text-rose-500">({reviewOverview.externalPastePercent}%)</span>
						</div>
					</div>
					<div class="rounded-xl bg-gray-50 dark:bg-gray-800 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-gray-400">{$i18n.t('Unknown source')}</div>
						<div class="mt-0.5 text-base font-semibold text-gray-700 dark:text-gray-300">
							{reviewOverview.unknownChars}
							<span class="text-xs font-medium text-gray-400">({reviewOverview.unknownPercent}%)</span>
						</div>
					</div>
					<div class="rounded-xl bg-indigo-50 px-3 py-2">
						<div class="text-[10px] uppercase tracking-[0.1em] text-indigo-500">{$i18n.t('Prompts')} / {$i18n.t('Versions')}</div>
						<div class="mt-0.5 text-base font-semibold text-indigo-950">{reviewOverview.promptCount} / {reviewOverview.versionCount}</div>
					</div>
				</div>
				<EduEvidenceDisclaimer class="mt-2" />
			</div>

			<!-- ── Main two-column body ── -->
			<div class="min-h-0 flex-1 grid grid-cols-1 gap-3 overflow-hidden p-4 lg:grid-cols-[1.2fr_0.8fr]">

				<!-- LEFT: Article panel (internal scroll) -->
				<div class="flex flex-col overflow-hidden rounded-3xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850">
					<!-- Article header (fixed) -->
					<div class="shrink-0 border-b border-gray-100 dark:border-gray-800 px-6 pt-5 pb-4">
						<div class="flex items-center justify-between">
							<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">{$i18n.t('Final Submission')}</div>
							<label class="flex cursor-pointer items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
								<input type="checkbox" bind:checked={highlight} class="accent-black dark:accent-white" />
								{$i18n.t('Highlight sources')}
							</label>
						</div>
						{#if highlight}
							<div class="mt-3 flex flex-wrap gap-2 text-xs">
								<EduBadge tone="amber" class="inline-flex items-center gap-1.5">
									<span class="inline-block h-2.5 w-2.5 rounded bg-amber-300"></span>
									{$i18n.t('AI inserted')}
								</EduBadge>
								<EduBadge tone="sky" class="inline-flex items-center gap-1.5">
									<span class="inline-block h-2.5 w-2.5 rounded bg-sky-300"></span>
									{$i18n.t('AI pasted')}
								</EduBadge>
								<EduBadge tone="emerald" class="inline-flex items-center gap-1.5">
									<span class="inline-block h-2.5 w-2.5 rounded bg-emerald-300"></span>
									{$i18n.t('Typed')}
								</EduBadge>
								<EduBadge tone="rose" class="inline-flex items-center gap-1.5">
									<span class="inline-block h-2.5 w-2.5 rounded bg-rose-300"></span>
									{$i18n.t('External paste / suspected import')}
								</EduBadge>
								<EduBadge class="inline-flex items-center gap-1.5">
									<span class="inline-block h-2.5 w-2.5 rounded bg-gray-300"></span>
									{$i18n.t('Unknown source')}
								</EduBadge>
							</div>
						{/if}
					</div>
					<!-- Article body (scrollable) -->
					<div class="flex-1 overflow-y-auto px-6 py-5">
						<div class="rounded-2xl bg-stone-50 dark:bg-gray-900 p-5">
							{#if highlight}
								<SourceHighlightedText
									json={detail.final_version.note_snapshot_json}
									text={detail.final_version.note_snapshot_text ?? detail.note?.data?.content?.md ?? ''}
									segments={analysisHighlights}
									{activeSegmentId}
								/>
							{:else}
								<SourceHighlightedText
									json={detail.final_version.note_snapshot_json}
									text={detail.final_version.note_snapshot_text ?? detail.note?.data?.content?.md ?? ''}
									segments={[]}
								/>
							{/if}
						</div>
					</div>
				</div>

				<!-- RIGHT: Tabbed review panel (internal scroll) -->
				<div class="flex flex-col overflow-hidden rounded-3xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850">

					<!-- Tab bar -->
					<div class="shrink-0 flex items-end gap-0.5 border-b border-gray-100 dark:border-gray-800 px-5 pt-4">
						{#each [
							{ key: 'review', label: t('Grading') },
							{ key: 'analysis', label: t('Analysis') },
							{ key: 'reflection', label: t('Reflection & Versions') }
						] as tab}
							<button
								class="relative px-4 pb-3 text-sm font-medium transition-colors {activeTab === tab.key
									? 'text-gray-950 dark:text-gray-100'
									: 'text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
								on:click={() => (activeTab = tab.key)}
							>
								{tab.label}
								{#if activeTab === tab.key}
									<span class="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-black dark:bg-gray-100"></span>
								{/if}
							</button>
						{/each}
					</div>

					<!-- Tab content (scrollable) -->
					<div class="min-h-0 flex-1 overflow-y-auto">

						<!-- ── 评分 tab ── -->
						{#if activeTab === 'review'}
							<div class="space-y-4 p-5">

								{#if isHistoricalRound}
									<div class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700 dark:text-amber-300">
										{$i18n.t('Historical round, read-only')}
									</div>
								{/if}

								<!-- Rubric: pick a score per criterion; the total below is derived -->
								<div>
									<div class="mb-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
										{$i18n.t('Rubric')}
									</div>
									<div class="divide-y divide-gray-100 dark:divide-gray-800 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
										{#each rubricCriteria as criterion}
											<div class="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
												<span class="flex-1 text-sm text-gray-700 dark:text-gray-300">
													{criterion.label} / {criterion.max_score}
												</span>
												<select
													value={rubricScores[criterion.key] ?? ''}
													on:change={(event) =>
														(rubricScores = {
															...rubricScores,
															[criterion.key]: event.currentTarget.value
														})}
													disabled={isHistoricalRound}
													class="w-24 rounded-xl border border-gray-200 dark:border-gray-800 dark:bg-gray-850 py-1.5 pl-3 pr-8 text-right text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
												>
													<option value="">—</option>
													{#each scoreOptions(criterion.max_score) as option}
														<option value={String(option)}>{option}</option>
													{/each}
												</select>
											</div>
										{/each}
									</div>
								</div>

								<!-- Total score: sum of the rubric scores above, read-only -->
								<div>
									<div class="mb-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
										{$i18n.t('Total Score')}
									</div>
									<div class="flex items-center justify-between gap-3 rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3">
										<span class="text-xs text-gray-400 dark:text-gray-500">
											{#if rubricFilledCount < rubricCriteria.length}
												{$i18n.t('Score every rubric criterion to get a total.')}
											{/if}
										</span>
										<span class="shrink-0 text-gray-700 dark:text-gray-300">
											<span class="text-lg font-semibold tabular-nums">{score === '' ? '—' : score}</span>
											<span class="text-sm text-gray-400"> / {detail.assignment.score_max}</span>
										</span>
									</div>
								</div>

								<!-- Overall comment -->
								<div>
									<label class="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
										{$i18n.t('Overall Comment')}
									</label>
									<textarea
										bind:value={overallComment}
										disabled={isHistoricalRound}
										class="min-h-24 w-full resize-none rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
										placeholder={$i18n.t('Overall Comment')}
									></textarea>
								</div>

								<!-- Returned comment -->
								<div>
									<label class="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
										{$i18n.t('Returned Comment')}
									</label>
									<textarea
										bind:value={returnedComment}
										disabled={isHistoricalRound}
										class="min-h-20 w-full resize-none rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
										placeholder={$i18n.t('Returned Comment')}
									></textarea>
								</div>

								<!-- Resubmit due at (required when returning for revision) -->
								<div>
									<label class="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
										{$i18n.t('Resubmit before')}
									</label>
									<EduDateTimeField
										bind:value={resubmitDueLocal}
										disabled={isHistoricalRound}
										className="w-full rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
									/>
									{#if resubmitDuePreview}
										<div class="mt-1.5 text-xs text-gray-400 dark:text-gray-500">{resubmitDuePreview}</div>
									{/if}
								</div>

								<!-- Actions + persistent save status -->
								<div class="flex flex-wrap items-center justify-between gap-3">
									<div class="flex flex-wrap gap-2">
										<EduButton
											disabled={saving || isHistoricalRound}
											on:click={() => saveReview('pending')}
										>
											{$i18n.t('Save Draft')}
										</EduButton>
										<EduButton
											variant="primary"
											disabled={saving || isHistoricalRound}
											on:click={() => saveReview('reviewed')}
										>
											{saving ? $i18n.t('Saving...') : $i18n.t('Save Review')}
										</EduButton>
										<EduButton
											disabled={saving || isHistoricalRound}
											on:click={() => saveReview('returned')}
										>
											{$i18n.t('Return for Revision')}
										</EduButton>
										<button
											class="rounded-full bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors"
											disabled={saving || isHistoricalRound}
											on:click={saveReviewAndNext}
										>
											{$i18n.t('Save & Next')}
										</button>
									</div>
									{#if lastSavedStr}
										<div class="text-xs text-gray-400">
											{$i18n.t('Last saved at {{time}}', { time: lastSavedStr })}
										</div>
									{/if}
								</div>
							</div>

						<!-- ── 分析 tab ── -->
						{:else if activeTab === 'analysis'}
							<div class="space-y-5 p-5">

								<!-- Segments -->
								<div>
									<div class="mb-3 flex items-center justify-between">
										<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">{$i18n.t('Segment Details')}</div>
										<EduButton size="sm" disabled={recomputing} on:click={recomputeAnalysis}>
											{recomputing ? $i18n.t('Recomputing...') : $i18n.t('Recompute Analysis')}
										</EduButton>
									</div>
									{#if analysisSegments.length === 0}
										<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4 text-sm text-gray-400">
											{$i18n.t('No tracked import segments yet.')}
										</div>
									{:else}
										<div class="space-y-2">
											{#each analysisSegments as segment}
												<button
													class="w-full rounded-2xl border px-4 py-3.5 text-left text-sm transition-colors {expandedSegmentId === segment.segment_id
														? 'border-gray-900 dark:border-gray-100 bg-stone-50 dark:bg-gray-900'
														: 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 hover:border-gray-300 dark:hover:border-gray-600'}"
													on:click={() => focusSegment(segment.segment_id)}
												>
													<!-- Segment header row -->
													<div class="flex items-center justify-between gap-2">
														<div class="font-medium text-gray-900 dark:text-gray-100">{segment.origin_type}</div>
														<div class="flex shrink-0 items-center gap-2">
															{#if segment.is_suspected_unmarked_import}
																<EduBadge soft tone="rose">{$i18n.t('Suspected')}</EduBadge>
															{/if}
															<!-- Chevron -->
															<svg
																class="h-4 w-4 text-gray-400 transition-transform {expandedSegmentId === segment.segment_id ? 'rotate-180' : ''}"
																fill="none" stroke="currentColor" viewBox="0 0 24 24"
															>
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
															</svg>
														</div>
													</div>

													<!-- Preview text -->
													<div class="mt-1.5 line-clamp-2 whitespace-pre-wrap break-words text-xs text-gray-400">
														{segment.content_initial}
													</div>

													<!-- Inline expanded detail -->
													{#if expandedSegmentId === segment.segment_id}
														<div class="mt-3 border-t border-gray-100 dark:border-gray-800 pt-3">
															<div class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Initial Length')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300">{segment.initial_length ?? 0}</span>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Final Length')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300">{segment.final_length ?? 0}</span>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Retained Ratio')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300">{segment.retained_ratio ?? 0}%</span>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Rewrite Ratio')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300">{segment.rewrite_ratio ?? 0}%</span>
																</div>
																<div class="col-span-2 flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Rewrite Level')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300">{segment.rewrite_level}</span>
																</div>
																{#if segment.suspicion_score}
																	<div class="col-span-2 flex items-center justify-between">
																		<span class="text-gray-400">{$i18n.t('Suspicion Score')}</span>
																		<span class="font-medium text-rose-600 dark:text-rose-400">{segment.suspicion_score}</span>
																	</div>
																{/if}
															</div>
															{#if segment.suspicion_reason}
																<div class="mt-2 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:text-rose-300">
																	{segment.suspicion_reason}
																</div>
															{/if}
														</div>
													{/if}
												</button>
											{/each}
										</div>
									{/if}
								</div>

								<!-- AI clarification questions -->
								<div>
									<div class="mb-3">
										<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">
											{$i18n.t('AI Clarification Questions')}
										</div>
										<div class="mt-0.5 text-xs text-gray-400">
											{$i18n.t(
												'Questions the AI paused to ask, and what the student answered. Recorded server-side from the chat itself.'
											)}
										</div>
									</div>
									{#if clarifications.length === 0}
										<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4 text-sm text-gray-400">
											{$i18n.t('The AI never paused to ask this student a question.')}
										</div>
									{:else}
										<div class="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
											<span>
												{$i18n.t('Asked: {{count}}', {
													count: clarificationSummary.clarification_question_count ?? 0
												})}
											</span>
											<span>
												{$i18n.t('Answered: {{count}}', {
													count: clarificationSummary.clarification_answered_count ?? 0
												})}
											</span>
											<span class="text-emerald-600 dark:text-emerald-400">
												{$i18n.t('In own words: {{count}}', {
													count: clarificationSummary.clarification_free_text_count ?? 0
												})}
											</span>
											{#if clarificationSummary.clarification_declined_count}
												<span>
													{$i18n.t('Dismissed: {{count}}', {
														count: clarificationSummary.clarification_declined_count
													})}
												</span>
											{/if}
										</div>
										<div class="space-y-2">
											{#each clarifications as exchange}
												<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-3 text-sm">
													{#if exchange.created_at}
														<div class="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-gray-400 tabular-nums">
															{formatEpochTime(exchange.created_at)}
														</div>
													{/if}
													<div class="space-y-2.5">
														{#each exchange.questions as question}
															<div>
																<div class="text-gray-800 dark:text-gray-200">{question.question}</div>
																{#if question.options.length}
																	<div class="mt-1 text-xs text-gray-400">
																		{question.options.join(' / ')}
																	</div>
																{/if}
																{#if question.answer === null}
																	<div class="mt-1.5 text-xs text-gray-400">
																		{$i18n.t('No answer')}
																	</div>
																{:else if question.answer.type === 'other'}
																	<div class="mt-1.5 rounded-xl bg-emerald-50 px-3 py-2 text-sm whitespace-pre-wrap break-words text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
																		{question.answer.text}
																	</div>
																{:else}
																	<div class="mt-1.5 text-sm text-gray-700 dark:text-gray-300">
																		{question.answer.label}
																	</div>
																{/if}
															</div>
														{/each}
													</div>
												</div>
											{/each}
										</div>
									{/if}
								</div>

								<!-- 提交前读者试读 -->
								<ChallengeRounds detail={challengeDetail} {criteriaLabels} />

								<!-- Timeline -->
								<div>
									<div class="mb-3 flex items-center justify-between">
										<div>
											<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">{$i18n.t('Writing Process Timeline')}</div>
											<div class="mt-0.5 text-xs text-gray-400">{$i18n.t('Prompts, text changes and analysis events combined')}</div>
										</div>
										<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
											<label class="inline-flex cursor-pointer items-center gap-1.5">
												<input type="checkbox" bind:checked={showUserTimeline} class="accent-blue-500" />
												<span class="text-blue-600">{$i18n.t('User')}</span>
											</label>
											<label class="inline-flex cursor-pointer items-center gap-1.5">
												<input type="checkbox" bind:checked={showAssistantTimeline} class="accent-purple-500" />
												<span class="text-purple-600">{$i18n.t('AI')}</span>
											</label>
											<label class="inline-flex cursor-pointer items-center gap-1.5">
												<input type="checkbox" bind:checked={showAnalysisTimeline} class="accent-gray-500" />
												<span>{$i18n.t('Writing Events')}</span>
											</label>
											<label class="inline-flex cursor-pointer items-center gap-1.5 opacity-60">
												<input type="checkbox" bind:checked={showAutosaveTimeline} class="accent-gray-400" />
												<span>{$i18n.t('Autosave')}</span>
											</label>
										</div>
									</div>
									{#if unifiedTimeline.length === 0}
										<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4 text-sm text-gray-400">
											{$i18n.t('No analysis timeline available yet.')}
										</div>
									{:else}
										<div class="space-y-2">
											{#each unifiedTimeline as item, i}
												{@const isUser = item.kind === 'prompt' && item.role === 'user'}
												{@const isAI = item.kind === 'prompt' && item.role === 'assistant'}
												{@const isExpanded = expandedTimelineIds.has(i)}
												{@const isLong = (item.label?.length ?? 0) > 200}
												<div class="rounded-r-2xl rounded-l-none border-l-[3px] bg-gray-50 dark:bg-gray-800 px-4 py-3 text-sm {isUser
													? 'border-blue-400'
													: isAI
														? 'border-purple-400'
														: 'border-gray-300 dark:border-gray-700'}">
													<div class="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.14em]">
														<span class="font-semibold {isUser ? 'text-blue-500' : isAI ? 'text-purple-500' : 'text-gray-400'}">
															{item.kind === 'prompt' ? item.meta : (item.meta ?? item.kind)}
														</span>
														{#if item.created_at}
															<span class="text-gray-400 tabular-nums">
																{formatEpochTime(item.created_at)}
															</span>
														{/if}
													</div>
													<div class="whitespace-pre-wrap break-words text-gray-800 dark:text-gray-200 {isExpanded ? '' : 'line-clamp-3'}">{item.label}</div>
													{#if item.inserted_length}
														<div class="mt-1 text-xs text-gray-400">
														{$i18n.t('+{{count}} chars', { count: item.inserted_length })}
													</div>
													{/if}
													{#if isLong}
														<button
															class="mt-1.5 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
															on:click={() => toggleTimelineItem(i)}
														>
															{isExpanded ? $i18n.t('Collapse') : $i18n.t('Expand full text')}
														</button>
													{/if}
												</div>
											{/each}
										</div>
									{/if}
								</div>

								<!-- Previous-round diff -->
								{#if detail?.submission?.round_no > 1}
									<div class="mt-4">
										<button
											class="text-sm font-medium underline disabled:opacity-50"
											disabled={diffLoading}
											on:click={loadDiff}
										>
											{diffLoading ? $i18n.t('Loading...') : $i18n.t('Compare with previous round')}
										</button>
										{#if diffData}
											{#if diffData.has_previous}
												<div class="mt-2 p-3 rounded-lg border border-gray-200 dark:border-gray-800 text-sm leading-7 whitespace-pre-wrap">
													{#each diffData.blocks as block}
														{#if block.op === 'equal'}<span>{block.new_text}</span>
														{:else if block.op === 'insert'}<span class="bg-emerald-100 dark:bg-emerald-900/50">{block.new_text}</span>
														{:else if block.op === 'delete'}<span class="bg-rose-100 dark:bg-rose-900/50 line-through">{block.old_text}</span>
														{:else}<span class="bg-rose-100 dark:bg-rose-900/50 line-through">{block.old_text}</span><span class="bg-emerald-100 dark:bg-emerald-900/50">{block.new_text}</span>{/if}
													{/each}
												</div>
											{:else}
												<div class="mt-2 text-sm text-gray-400">{$i18n.t('No previous round to compare.')}</div>
											{/if}
										{/if}
									</div>
								{/if}
							</div>

						<!-- ── 反思 & 版本 tab ── -->
						{:else if activeTab === 'reflection'}
							<div class="space-y-4 p-5">

								<!-- Coaching style in force for this round -->
								{#if roundCoaching}
									<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
										<div class="mb-2 text-[11px] uppercase tracking-[0.14em] text-gray-400">
											{$i18n.t('AI Coaching Style')}
										</div>
										<div class="flex flex-wrap items-center gap-2">
											<span class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300">
												{coachingStyleLabel ? $i18n.t(coachingStyleLabel) : roundCoaching.style}
											</span>
											{#if roundCoaching.prompt}
												<button
													class="text-xs text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
													on:click={() => (showCoachingPrompt = !showCoachingPrompt)}
												>
													{showCoachingPrompt
														? $i18n.t('Hide the wording used')
														: $i18n.t('Show the wording used')}
												</button>
											{/if}
										</div>
										{#if roundCoaching.prompt && showCoachingPrompt}
											<pre class="mt-2 whitespace-pre-wrap break-words rounded-xl bg-white dark:bg-gray-850 px-3 py-2 font-sans text-xs leading-6 text-gray-600 dark:text-gray-400">{roundCoaching.prompt}</pre>
										{/if}
										<div class="mt-2 text-[11px] text-gray-400">
											{$i18n.t('Frozen at submission time; later edits to this style do not change it.')}
										</div>
									</div>
								{/if}

								<!-- AI help types -->
								<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
									<div class="mb-2 text-[11px] uppercase tracking-[0.14em] text-gray-400">
										{$i18n.t('AI Help Types')}
									</div>
									<div class="flex flex-wrap gap-2">
										{#if !detail.micro_reflection.ai_used}
											<span class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300">
												{$i18n.t('Did not use AI')}
											</span>
										{:else}
											{#each detail.micro_reflection.ai_help_types as item}
												<span class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300">
													{getAiHelpTypeLabel(item, t)}
												</span>
											{/each}
										{/if}
									</div>
								</div>

								<!-- Structured reflection evidence -->
								<div class="grid gap-3 md:grid-cols-2">
									{#each [
										['What did you change?', detail.micro_reflection.reflection_json.action],
										['Where did you make this change?', detail.micro_reflection.reflection_json.location],
										['Why did you make this judgement?', detail.micro_reflection.reflection_json.judgement],
										['What will you do next time?', detail.micro_reflection.reflection_json.next_step]
									] as [label, value]}
										<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
											<div class="mb-2 text-[11px] uppercase tracking-[0.14em] text-gray-400">
												{$i18n.t(label)}
											</div>
											<div class="whitespace-pre-wrap text-sm leading-7 text-gray-700 dark:text-gray-300">
												{value}
											</div>
										</div>
									{/each}
								</div>

								<!-- Version history -->
								<div>
									<div class="mb-3 flex items-center justify-between">
										<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">{$i18n.t('Versions')}</div>
										<div class="text-xs text-gray-400">
											{#if hiddenVersionCount > 0 && !showAllVersions}
												{$i18n.t('Latest {{visible}} / {{total}}', {
													visible: visibleVersions.length,
													total: totalVersionCount
												})}
											{:else}
												{totalVersionCount} {$i18n.t('total')}
											{/if}
										</div>
									</div>
									<div class="space-y-1.5">
										{#each visibleVersions as version}
											{@const isAutosave = version.trigger_type === 'autosave'}
											<div class="flex items-center justify-between gap-3 rounded-2xl border px-4 text-sm transition-colors {isAutosave
												? 'border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40 py-2 opacity-55'
												: 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 py-3'}">
												<span class="{isAutosave ? 'text-xs text-gray-500 dark:text-gray-400' : 'font-medium text-gray-900 dark:text-gray-100'}">
													{$i18n.t('Version')} {version.version_no}
												</span>
												<div class="flex items-center gap-2 text-right">
													{#if !isAutosave}
														<EduBadge soft tone="emerald">
															{getReviewTriggerTypeLabel(version.trigger_type)}
														</EduBadge>
													{/if}
													<span class="text-xs text-gray-400 tabular-nums">
														{isAutosave
															? formatEpochTime(version.created_at)
															: formatEpoch(version.created_at)}
													</span>
												</div>
											</div>
										{/each}
									</div>
									{#if hiddenVersionCount > 0 || showAllVersions}
										<EduButton class="mt-3" disabled={loadingVersions} on:click={toggleAllVersions}>
											{loadingVersions
												? $i18n.t('Loading...')
												: showAllVersions
													? $i18n.t('Show Less')
													: `${$i18n.t('Show All')} (${hiddenVersionCount} ${$i18n.t('more')})`}
										</EduButton>
									{/if}
								</div>
							</div>
						{/if}

					</div>
				</div>
			</div>
		</div>

	{:else if loaded && loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<LoadingState messageKey="Loading submission..." />
	{/if}
</TeacherPageShell>
