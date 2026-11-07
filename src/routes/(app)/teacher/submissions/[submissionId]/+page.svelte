<script lang="ts">
	import { isRevision } from '$lib/utils/task-types';
	import TeacherProcessPanel from '$lib/components/education/TeacherProcessPanel.svelte';
	import TeacherModelSummary from '$lib/components/education/TeacherModelSummary.svelte';
	import ProcessDraftView from '$lib/components/education/ProcessDraftView.svelte';
	import { initialProcessState, type ProcessInspection } from '$lib/utils/process-review';
	import type { AiStepKey, SubmissionProcess } from '$lib/apis/education';
	import { teacherConversationEvents, teacherModelUsage } from '$lib/utils/teacher-writing-process';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import TextDiffBlocks from '$lib/components/education/TextDiffBlocks.svelte';
	import { page } from '$app/stores';
	import { createLatestRequestGate } from '$lib/utils/latest-request';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { config, user } from '$lib/stores';

	import {
		getSubmissionAnalysisSegmentDetail,
		compareSubmissionProcess,
		getSubmissionRoundDiff,
		getSubmissionDraftDiff,
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
	import RevisionItemsReview from '$lib/components/education/RevisionItemsReview.svelte';
	import {
		buildSubmissionReviewOverview,
		getReviewQueueNavigation
	} from '$lib/utils/submission-review';
	import {
		formatEpoch,
		formatEpochTime,
		getEditorOperationLabel,
		getRewriteLevelLabel,
		getVersionTriggerLabel,
		getWritingSourceLabel,
		resolveErrorMessage,
		toLocalDateTimeInput
	} from '$lib/utils/education';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduDateTimeField from '$lib/components/education/EduDateTimeField.svelte';
	import { THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const DEFAULT_VISIBLE_VERSIONS = 10;
	// 后端时间线条目只带结构化字段（外加一条调试用的英文 label/message），
	// 展示文案一律在这里按 event_type 翻译，不显示后端拼的英文串。
	const describeAnalysisEvent = (item) => {
		if (item.event_type === 'version') {
			return {
				meta: getVersionTriggerLabel(item.trigger_type, t),
				label: t('Version {{number}}', { number: item.version_no }),
				inserted_length: null
			};
		}
		// 连续的手动输入/删除/替换在后端已合并成一段，这里只报增删字数，写了什么、删了什么展开看。
		if (item.event_type === 'typing_run') {
			return {
				meta: t('Edited text'),
				label: [
					item.inserted_length ? t('+{{count}} chars', { count: item.inserted_length }) : null,
					item.deleted_length ? t('−{{count}} chars', { count: item.deleted_length }) : null,
					t('{{count}} edits', { count: item.operation_count })
				]
					.filter(Boolean)
					.join(' · '),
				inserted_length: null,
				run: {
					ended_at: item.ended_at,
					inserted_text: item.inserted_text ?? '',
					deleted_text: item.deleted_text ?? ''
				}
			};
		}
		if (item.event_type === 'source_operation') {
			return {
				meta: getWritingSourceLabel(item.source_type, t),
				// 学生在编辑器里导入的文件或照片,记为外部粘贴,这里注明是导入的。
				label:
					item.import_kind === 'images'
						? t('Imported text from images')
						: item.import_kind === 'document'
							? t('Imported text from a file')
							: getEditorOperationLabel(item.op_type, t),
				inserted_length: item.inserted_length ?? null
			};
		}
		if (item.event_type === 'large_burst') {
			return {
				meta: t('Large insertion'),
				label: t('Added a large block of text at once'),
				inserted_length: item.inserted_length ?? null
			};
		}
		if (item.event_type === 'submit') {
			return { meta: t('Submit'), label: t('Submitted this round'), inserted_length: null };
		}
		return { meta: item.event_type, label: item.label ?? '', inserted_length: null };
	};
	const reviewStatusOptions = [
		{ value: 'pending', label: 'Pending Review' },
		{ value: 'reviewed', label: 'Reviewed' },
		{ value: 'returned', label: 'Returned' }
	];

	let conflictDraft: { round_no: number; version_no: number; text: string } | null = null;
	const conflictKey = () => `education:review-conflict:${$user?.id}:${detail?.writing_session?.id}`;
	const clearConflictDraft = () => {
		sessionStorage.removeItem(conflictKey());
		conflictDraft = null;
	};
	const preserveReviewDraft = () => {
		conflictDraft = {
			round_no: detail.submission.round_no,
			version_no: detail.final_version.version_no,
			text: [
				`${t('Total Score')}: ${score || '—'}`,
				...rubricCriteria.map((c) => `${c.label}: ${rubricScores[c.key] ?? '—'}`),
				`${t('Reflection Quality')}: ${reflectionScore || '—'}`,
				`${t('Prompt Quality')}: ${promptScore || '—'}`,
				overallComment,
				returnedComment
			]
				.filter(Boolean)
				.join('\n')
		};
		try {
			sessionStorage.setItem(conflictKey(), JSON.stringify(conflictDraft));
		} catch {
			toast.warning(t('无法保存本地参考草稿，请先复制当前评语。'));
		}
	};
	const reloadCurrentReview = async () => {
		try {
			const fresh = await getTeacherSubmissionDetail(localStorage.token, submissionId);
			const latest = fresh.rounds?.find((round) => round.is_current);
			if (latest && latest.submission_id !== submissionId)
				await goto(`/teacher/submissions/${latest.submission_id}`);
			else await loadDetail(submissionId);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};
	let detail = null;
	let loaded = false;
	let loadError = '';
	let highlight = true;
	let reviewStatus = 'pending';
	let score = '';
	let reflectionScore = '';
	let promptScore = '';
	let overallComment = '';
	let rubricScores = {};
	let returnedComment = '';
	let saving = false;
	let showAllVersions = false;
	let showCoachingPrompt = false;
	let activeSegmentId = '';
	let activeSegmentDetail = null;

	// New state
	let activeTab: 'review' | 'analysis' | 'reflection' = 'review';
	let expandedSegmentId = '';
	let lastSavedAt: Date | null = null;
	let processState = initialProcessState();
	let processCatalog: SubmissionProcess | null = null;
	let processInspection: ProcessInspection | null = null;
	let processPanel: TeacherProcessPanel;
	let timelineSection: HTMLDivElement;
	let documentPanel: HTMLDivElement;
	const processRequests = createLatestRequestGate();
	const inspectProcess = async ({
		beforeId,
		afterId,
		mode
	}: {
		beforeId: string;
		afterId: string;
		mode: 'snapshot' | 'compare';
	}) => {
		const request = processRequests.next();
		const id = detail.submission.id,
			version = detail.submission.final_version_id;
		processInspection = { mode, loading: true, error: '', comparison: null };
		docView = 'process';
		try {
			const comparison = await compareSubmissionProcess(
				localStorage.token,
				id,
				version,
				beforeId,
				afterId
			);
			if (
				!processRequests.isLatest(request) ||
				detail?.submission.id !== id ||
				detail.submission.final_version_id !== version
			)
				return;
			processInspection = { mode, loading: false, error: '', comparison };
			if (activeTab === 'analysis' && docView === 'process' && window.innerWidth < 1024)
				await tick().then(() =>
					documentPanel?.scrollIntoView({ block: 'start', behavior: 'smooth' })
				);
		} catch (error) {
			if (processRequests.isLatest(request))
				processInspection = {
					mode,
					loading: false,
					error: resolveErrorMessage(error, t),
					comparison: null
				};
		}
	};
	const openWritingProcess = async (overall = false) => {
		activeTab = 'analysis';
		await tick();
		timelineSection?.scrollIntoView({ block: 'start', behavior: 'smooth' });
		if (overall) await processPanel?.showOverall();
	};
	$: overallSelected =
		docView === 'process' &&
		processInspection?.mode === 'compare' &&
		processState.beforeId === processCatalog?.default_before_id &&
		processState.afterId === processCatalog?.default_after_id;
	let resubmitDueLocal = '';
	let challengeFollowup = false;
	let returnMode = false;
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
		{ socratic: 'Socratic', balanced: 'Balanced', hands_off: 'Hands-off' }[roundCoaching?.style] ??
		null;
	// 本轮辅导对话的思考档位(提交时冻存)。学生可开关时每条回复另记实际档位,时间线上逐条标出。
	$: roundThinking = roundCoaching?.thinking ?? null;
	$: showReplyThinking = Boolean(roundThinking?.students_choose);
	// 模型标识取提交时的事实，不用当前模型列表重新解释历史记录。
	$: roundStepModels = [
		{
			step: 'first_read',
			model_id: detail?.submission?.stats_json?.revision_items?.models?.first_read
		},
		{
			step: 'revision_review',
			model_id: detail?.submission?.stats_json?.revision_items?.models?.follow_up
		},
		...(detail?.submission?.stats_json?.challenge?.models ?? []).map((model) => ({
			step: 'reader_check',
			model_id: model
		}))
	].filter((item) => item.model_id) as Array<{ step: AiStepKey; model_id: string }>;
	const THINKING_SOURCE_TEXT = {
		admin: 'Administrator default',
		teacher: 'Set for this assignment',
		student: 'Switched off by the student'
	};
	$: segmentCharStats = (() => {
		if (!analysisHighlights.length) return null;
		let typed = 0,
			aiInserted = 0,
			aiPasted = 0,
			externalPaste = 0,
			unknown = 0,
			declaredDraft = 0;
		for (const seg of analysisHighlights) {
			const len = (seg.segment_text ?? '').length;
			if (seg.source_type === 'user_typed') typed += len;
			else if (seg.source_type === 'ai_inserted') aiInserted += len;
			else if (seg.source_type === 'ai_pasted') aiPasted += len;
			else if (
				seg.source_type === 'external_paste' ||
				seg.source_type === 'suspected_unmarked_import'
			)
				externalPaste += len;
			else if (seg.source_type === 'unknown') unknown += len;
			else if (seg.source_type === 'declared_draft') declaredDraft += len;
		}
		return { typed, aiInserted, aiPasted, externalPaste, unknown, declaredDraft };
	})();
	$: reviewOverview = buildSubmissionReviewOverview({
		analysisSummary: segmentCharStats
			? {
					...analysisSummary,
					typed_chars: segmentCharStats.typed,
					ai_inserted_chars: segmentCharStats.aiInserted,
					ai_pasted_chars: segmentCharStats.aiPasted,
					external_paste_chars: segmentCharStats.externalPaste,
					unknown_chars: segmentCharStats.unknown,
					declared_draft_chars: segmentCharStats.declaredDraft
				}
			: analysisSummary,
		stats: detail?.submission?.stats_json ?? {}
	});
	$: sourceSegments = [
		{
			label: 'Typed',
			chars: reviewOverview.typedChars,
			percent: reviewOverview.typedPercent,
			bar: 'bg-emerald-300',
			swatch: 'bg-emerald-300'
		},
		{
			label: 'AI inserted',
			chars: reviewOverview.aiInsertedChars,
			percent: reviewOverview.aiInsertedPercent,
			bar: 'bg-amber-300',
			swatch: 'bg-amber-300'
		},
		{
			label: 'AI pasted',
			chars: reviewOverview.aiPastedChars,
			percent: reviewOverview.aiPastedPercent,
			bar: 'bg-sky-300',
			swatch: 'bg-sky-300'
		},
		{
			label: 'External paste / suspected import',
			chars: reviewOverview.externalPasteChars,
			percent: reviewOverview.externalPastePercent,
			bar: 'bg-rose-300',
			swatch: 'bg-rose-300'
		},
		{
			label: 'Unknown source',
			chars: reviewOverview.unknownChars,
			percent: reviewOverview.unknownPercent,
			bar: 'bg-gray-300',
			swatch: 'bg-gray-300'
		},
		// 修订初稿作业里学生声明的初稿:来源明确，不用风险色；其他作业没有这一行。
		...(reviewOverview.declaredDraftChars > 0
			? [
					{
						label: 'Declared first draft',
						chars: reviewOverview.declaredDraftChars,
						percent: reviewOverview.declaredDraftPercent,
						bar: 'bg-violet-300',
						swatch: 'bg-violet-300'
					}
				]
			: [])
	];
	$: isReviseDraft = isRevision(detail?.assignment?.task_mode);
	$: conversationEvents = teacherConversationEvents(
		detail?.prompt_timeline ?? [],
		detail?.submission?.stats_json?.revision_readings ?? [],
		detail?.submission?.stats_json?.chat_contexts ?? [],
		t
	);
	$: roundModelUsage = teacherModelUsage(conversationEvents, roundStepModels);
	$: editingEvents = analysisTimeline
		.filter((item) => item.event_type !== 'version')
		.map((item, index) => ({
			key: `analysis:${index}`,
			...describeAnalysisEvent(item),
			created_at: item.created_at
		}));

	$: lastSavedStr = lastSavedAt ? formatEpochTime(Math.floor(lastSavedAt.getTime() / 1000)) : null;

	// 维度分从高到低列出：批改时命中的多是接近满分的档位。
	const scoreOptions = (max: number) => Array.from({ length: max + 1 }, (_, index) => max - index);

	let challengeDetail = null;
	$: rubricCriteria = detail?.assignment?.rubric_schema?.criteria ?? [];
	$: criteriaLabels = Object.fromEntries(
		rubricCriteria.map((criterion) => [criterion.key, criterion.label])
	);
	// 修订初稿作业:第一次通读按评分维度逐项下的结论和学生的处理,打分时就排在每一行下面。
	$: firstReadByKey = Object.fromEntries(
		(isReviseDraft ? (detail?.submission?.stats_json?.revision_items?.items ?? []) : []).map(
			(item) => [item.criterion_key, item]
		)
	);
	const FIRST_READ_STATUS_LABELS = {
		problem: 'Needs changing',
		minor: 'Could be better',
		ok: 'Meets the standard',
		deferred: 'Not looked at yet'
	};
	const FIRST_READ_DECISION_LABELS = {
		revised: 'Changed it',
		partly: 'Changed part of it',
		kept: 'Left it as is'
	};
	$: rubricFilledCount = rubricCriteria.filter(
		(criterion) => (rubricScores[criterion.key] ?? '') !== ''
	).length;
	// 总分不再手填：评完全部维度才算出总分，否则留空（后端要求总分等于各维度之和）。
	$: if (detail?.assignment?.scoring_mode !== 'total')
		score =
			rubricCriteria.length > 0 && rubricFilledCount === rubricCriteria.length
				? String(
						rubricCriteria.reduce((sum, criterion) => sum + Number(rubricScores[criterion.key]), 0)
					)
				: '';

	// 本轮没和 AI 对话过就没有提问可评，提问质量这一项不显示也不提交。
	$: hasReflectionAnswers = (detail?.micro_reflection?.reflection_json?.items ?? []).some(
		(item) => item.text?.trim() || item.selected?.length || item.other_text?.trim()
	);
	$: hasRoundPrompts = (detail?.round_prompt_count ?? 0) > 0;

	const syncReview = () => {
		const review = detail?.review;
		reviewStatus = review?.review_status || 'pending';
		if (detail?.assignment?.scoring_mode === 'total')
			score = review?.score != null ? String(review.score) : '';
		reflectionScore = review?.reflection_score != null ? String(review.reflection_score) : '';
		promptScore = review?.prompt_score != null ? String(review.prompt_score) : '';
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
		challengeFollowup = review?.challenge_followup ?? false;
		returnMode = review?.review_status === 'returned';
	};

	const saveReview = async (effectiveStatus: string) => {
		if (isHistoricalRound) return false;
		// 总分由各维度分求和得到，范围与「等于各维度之和」都无需再校验。
		const parsedScore = score === '' ? null : Number(score);
		// 下拉只能选出合法档位，这里只需分辨「全空 / 全填 / 填了一半」。
		const parsedRubricScores =
			rubricCriteria.length > 0 && rubricFilledCount === rubricCriteria.length
				? Object.fromEntries(
						rubricCriteria.map((criterion) => [criterion.key, Number(rubricScores[criterion.key])])
					)
				: null;
		if (rubricFilledCount > 0 && parsedRubricScores == null) {
			toast.error(t('Score every rubric criterion before saving.'));
			return false;
		}
		if (
			effectiveStatus === 'reviewed' &&
			(parsedScore == null ||
				(detail.assignment.scoring_mode !== 'total' && parsedRubricScores == null))
		) {
			toast.error(t('Reviewed submissions require a total score and complete rubric scores.'));
			return false;
		}
		const parsedReflectionScore =
			!hasReflectionAnswers || reflectionScore === '' ? null : Number(reflectionScore);
		if (effectiveStatus === 'reviewed' && hasReflectionAnswers && parsedReflectionScore == null) {
			toast.error(t('Rate the reflection before marking this submission reviewed.'));
			return false;
		}
		const parsedPromptScore = hasRoundPrompts && promptScore !== '' ? Number(promptScore) : null;
		if (effectiveStatus === 'reviewed' && hasRoundPrompts && parsedPromptScore == null) {
			toast.error(t('Rate the AI prompts before marking this submission reviewed.'));
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
				expected_final_version_id: detail.submission.final_version_id,
				expected_review_revision: detail.review_revision,
				review_status: effectiveStatus,
				score: parsedScore,
				reflection_score: parsedReflectionScore,
				prompt_score: parsedPromptScore,
				overall_comment: overallComment.trim(),
				rubric_scores: parsedRubricScores,
				returned_comment: returnedComment.trim(),
				resubmit_due_at: resubmitDueAt,
				// 只在真的退回时带上：换个状态保存不该把这个意图留在记录里。
				challenge_followup: effectiveStatus === 'returned' && challengeFollowup
			});
			detail.review_revision = response.review_revision;
			detail.review = response;
			syncReview();
			lastSavedAt = new Date();
			toast.success(t('Review saved.'));
			return true;
		} catch (error) {
			if (
				String(error?.detail ?? '').includes('The submission or review changed') ||
				String(error?.detail ?? '').includes('Historical submission rounds')
			)
				preserveReviewDraft();
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
		const queue = await loadQueueContext();
		if (!queue) {
			goto('/teacher/review');
			return;
		}
		const { nextId, isEmpty } = getReviewQueueNavigation(
			{ ids: queueIds, total: queue.total },
			target
		);
		if (nextId) {
			goto(`/teacher/submissions/${nextId}`);
		} else {
			if (isEmpty) toast.success(t('Review queue is clear.'));
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
			return res;
		} catch {
			queueIds = [];
			return null;
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

	// 初稿 → 终稿:老师要看的是从第一稿到这一轮的完整修改，退回重交后起点仍是最初那份初稿。
	// 修订初稿作业批改时最常看的就是它，所以放在左栏正文上方切换，进页面就取回。
	let docView: 'final' | 'process' = 'final';
	let draftDiffFor = '';
	$: if (
		isReviseDraft &&
		detail?.submission?.id &&
		draftDiffFor !== `${detail.submission.id}:${detail.submission.final_version_id}`
	) {
		draftDiffFor = `${detail.submission.id}:${detail.submission.final_version_id}`;
		draftDiffData = null;
		docView = 'final';
		loadDraftDiff();
	}
	let draftDiffData = null;
	let draftDiffLoading = false;
	let draftDiffSeq = 0;
	const loadDraftDiff = async () => {
		const seq = ++draftDiffSeq;
		draftDiffLoading = true;
		try {
			const response = await getSubmissionDraftDiff(localStorage.token, detail.submission.id);
			if (seq !== draftDiffSeq) return;
			draftDiffData = response;
		} catch (error) {
			if (seq !== draftDiffSeq) return;
			toast.error(resolveErrorMessage(error, t));
		} finally {
			draftDiffLoading = false;
		}
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
		processRequests.next();
		processState = initialProcessState();
		processCatalog = null;
		processInspection = null;
		docView = 'final';
		fullVersions = null;
		try {
			const response = await getTeacherSubmissionDetail(localStorage.token, id);
			if (seq !== loadSeq) return;
			detail = response;
			try {
				conflictDraft = JSON.parse(sessionStorage.getItem(conflictKey()) || 'null');
			} catch {
				conflictDraft = null;
			}
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
	width="full"
	crumbs={[
		{ label: $i18n.t('Review'), href: '/teacher/review' },
		...(detail
			? [
					{
						label: detail.assignment.title,
						href: `/teacher/assignments/${detail.assignment.id}/submissions`
					}
				]
			: [])
	]}
	title={detail?.student_name ?? ''}
>
	<svelte:fragment slot="nav-actions">
		{#if loaded && detail}
			<EduButton
				disabled={!prevPendingId}
				on:click={() => prevPendingId && goto(`/teacher/submissions/${prevPendingId}`)}
			>
				&larr; {$i18n.t('Previous pending')}
			</EduButton>
			<EduButton
				disabled={!nextPendingId}
				on:click={() => nextPendingId && goto(`/teacher/submissions/${nextPendingId}`)}
			>
				{$i18n.t('Next pending')} &rarr;
			</EduButton>
		{/if}
	</svelte:fragment>

	{#if loaded && detail}
		<!-- Desktop panels scroll independently; narrow screens use the shell's page scroll. -->
		<div class="flex flex-col lg:h-full lg:overflow-hidden">
			{#if conflictDraft}
				<section
					class="mb-3 shrink-0 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-gray-850"
				>
					<p>{$i18n.t('稿件或评阅已更新，你的批改草稿已保留供参考。请重新核对后保存。')}</p>
					<details class="my-2">
						<summary
							>{$i18n.t('查看保留的批改草稿')} · {$i18n.t('Round {{round}}', {
								round: conflictDraft.round_no
							})} · {$i18n.t('稿件版本')}
							{conflictDraft.version_no}</summary
						>
						<pre
							class="max-h-40 overflow-auto whitespace-pre-wrap font-sans">{conflictDraft.text}</pre>
					</details>
					<div class="flex gap-4">
						<button type="button" class="underline" on:click={reloadCurrentReview}
							>{$i18n.t('重新载入最新提交')}</button
						><button type="button" class="underline" on:click={clearConflictDraft}
							>{$i18n.t('清除参考草稿')}</button
						>
					</div>
				</section>
			{/if}

			<!--
				固定头部此前叠了五层(分区导航、返回与上下份、标题与关注点、7 格来源统计、免责声明),
				笔记本屏上原文区被压得很矮。导航交给顶栏;7 格统计收成一条来源比例条,
				同时充当原文高亮的图例。
			-->
			<div
				class="shrink-0 space-y-2 border-b border-gray-100 bg-white px-6 py-3 dark:border-gray-800 dark:bg-gray-850"
			>
				<div class="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
					<span
						class="rounded-full px-2.5 py-0.5 {reviewStatus === 'reviewed'
							? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
							: reviewStatus === 'returned'
								? 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300'
								: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}"
					>
						{$i18n.t(
							reviewStatusOptions.find((o) => o.value === reviewStatus)?.label ?? 'Pending Review'
						)}
					</span>
					<span>{$i18n.t('Submitted At')}: {formatEpoch(detail.submission.submitted_at)}</span>
					<span
						>{$i18n.t('Round {{round}}', { round: detail.submission.round_no })} · {$i18n.t(
							'稿件版本'
						)}
						{detail.final_version.version_no}</span
					>
					{#if detail?.rounds?.length > 1}
						<span class="text-gray-300 dark:text-gray-600">|</span>
						{#each detail.rounds as round}
							<a
								href={`/teacher/submissions/${round.submission_id}`}
								class="rounded-lg border px-2 py-0.5 {round.submission_id === detail.submission.id
									? 'border-gray-900 bg-gray-900 text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
									: 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'}"
							>
								{$i18n.t('Round {{round}}', { round: round.round_no })}{#if !round.is_current}<span
										class="opacity-60"
									>
										· {$i18n.t('History')}</span
									>{/if}
							</a>
						{/each}
					{/if}
					<span
						class="ml-auto inline-flex items-center gap-1.5 rounded-full border border-cyan-100 bg-cyan-50 px-2.5 py-0.5 text-cyan-800 dark:border-cyan-900 dark:bg-cyan-950/40 dark:text-cyan-200"
						title={[
							$i18n.t('A heuristic pointer for where to look first, not a conclusion.'),
							...reviewOverview.focusReasons.map((reason) => $i18n.t(reason))
						].join('\n')}
					>
						<span class="opacity-70">{$i18n.t('Process Focus')}</span>
						<span class="font-semibold">{$i18n.t(reviewOverview.focusLabel)}</span>
					</span>
					<!-- 修订初稿:和初稿比改了多少。只是提示，不是判定，所以用灰色。 -->
					{#if isReviseDraft && draftDiffData?.has_baseline}
						<span
							class="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
						>
							{draftDiffData.same_as_draft
								? $i18n.t('Same as first draft')
								: $i18n.t(
										'First draft {{total}} sentences: {{changed}} changed or removed; {{added}} newly written sentences in the final',
										{
											total: draftDiffData.draft_sentence_count,
											changed: draftDiffData.changed_sentence_count,
											added: draftDiffData.added_sentence_count
										}
									)}
						</span>
					{/if}
				</div>

				<div>
					<div class="flex h-2.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
						{#each sourceSegments as segment}
							{#if segment.chars > 0}
								<div
									class={segment.bar}
									style={`width: ${segment.percent}%`}
									title={`${$i18n.t(segment.label)} ${segment.chars} (${segment.percent}%)`}
								></div>
							{/if}
						{/each}
					</div>
					<div
						class="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400"
					>
						{#each sourceSegments as segment}
							<span class="inline-flex items-center gap-1.5">
								<span class="inline-block size-2.5 rounded {segment.swatch}"></span>
								{$i18n.t(segment.label)}
								<span class="tabular-nums text-gray-900 dark:text-gray-100">{segment.chars}</span>
								<span class="tabular-nums text-gray-400">({segment.percent}%)</span>
							</span>
						{/each}
						<span class="text-gray-400">
							{$i18n.t('Total characters')}
							{reviewOverview.totalChars} · {$i18n.t('Prompts')}
							{reviewOverview.promptCount} · {$i18n.t('Versions')}
							{reviewOverview.versionCount}
						</span>
					</div>
					<EduEvidenceDisclaimer class="mt-1" />
				</div>
			</div>

			<!-- ── Main two-column body ── -->
			<div
				class="grid grid-cols-1 gap-3 p-4 lg:min-h-0 lg:flex-1 lg:overflow-hidden lg:grid-cols-[1.2fr_0.8fr]"
			>
				<!-- LEFT: Article panel (internal scroll) -->
				<div
					bind:this={documentPanel}
					class="flex flex-col overflow-hidden rounded-3xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
				>
					<!-- Article header (fixed) -->
					<div class="shrink-0 border-b border-gray-100 dark:border-gray-800 px-6 pt-5 pb-4">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<div class="flex flex-wrap gap-2 text-sm">
								<EduButton
									size="sm"
									variant={docView === 'final' ? 'primary' : 'secondary'}
									on:click={() => (docView = 'final')}>{$i18n.t('Final Submission')}</EduButton
								>
								<EduButton
									size="sm"
									variant={overallSelected ? 'primary' : 'secondary'}
									on:click={() => openWritingProcess(true)}
									>{$i18n.t(isReviseDraft ? 'First draft → final' : '从起点到提交')}</EduButton
								>
								{#if processInspection && !overallSelected}<EduButton
										size="sm"
										variant={docView === 'process' ? 'primary' : 'secondary'}
										on:click={() => (docView = 'process')}>{$i18n.t('当前过程稿件')}</EduButton
									>{/if}
								{#if docView === 'process'}<span class="lg:hidden"
										><EduButton size="sm" on:click={() => openWritingProcess()}
											>{$i18n.t('回到过程记录')}</EduButton
										></span
									>{/if}
							</div>
							{#if docView === 'final'}
								<label
									class="flex cursor-pointer items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
								>
									<input
										type="checkbox"
										bind:checked={highlight}
										class="accent-black dark:accent-white"
									/>
									{$i18n.t('Highlight sources')}
								</label>
							{/if}
						</div>
					</div>
					<!-- Article body (scrollable) -->
					<div class="px-6 py-5 lg:flex-1 lg:overflow-y-auto">
						<div class="rounded-2xl bg-stone-50 dark:bg-gray-900 p-5">
							{#if docView === 'process'}
								<ProcessDraftView
									inspection={processInspection}
									source={conversationEvents.find((event) => event.key === processState.selectedKey)
										?.source ?? null}
								/>
							{:else if highlight}
								<SourceHighlightedText
									json={detail.final_version.note_snapshot_json}
									text={detail.final_version.note_snapshot_text ?? ''}
									segments={analysisHighlights}
									{activeSegmentId}
								/>
							{:else}
								<SourceHighlightedText
									json={detail.final_version.note_snapshot_json}
									text={detail.final_version.note_snapshot_text ?? ''}
									segments={[]}
								/>
							{/if}
						</div>
					</div>
				</div>

				<!-- RIGHT: Tabbed review panel (internal scroll) -->
				<div
					class="flex flex-col overflow-hidden rounded-3xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
				>
					<!-- Tab bar -->
					<div
						class="shrink-0 flex items-end gap-0.5 border-b border-gray-100 dark:border-gray-800 px-5 pt-4"
					>
						{#each [{ key: 'review' as const, label: t('Grading') }, { key: 'analysis' as const, label: t('Analysis') }, { key: 'reflection' as const, label: t('Reflection & Versions') }] as tab}
							<button
								class="relative px-4 pb-3 text-sm font-medium transition-colors {activeTab ===
								tab.key
									? 'text-gray-950 dark:text-gray-100'
									: 'text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
								on:click={() => {
									activeTab = tab.key;
									if (tab.key === 'review') docView = 'final';
									else if (tab.key === 'analysis' && processInspection) docView = 'process';
								}}
							>
								{tab.label}
								{#if activeTab === tab.key}
									<span
										class="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-black dark:bg-gray-100"
									></span>
								{/if}
							</button>
						{/each}
					</div>

					<!-- Tab content (scrollable) -->
					<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
						<!-- ── 评分 tab ── -->
						{#if activeTab === 'review'}
							<div class="space-y-4 p-5">
								<EduButton variant="link" on:click={() => openWritingProcess()}
									>{$i18n.t('查看写作过程')}</EduButton
								>
								{#if isHistoricalRound}
									<div
										class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700 dark:text-amber-300"
									>
										{$i18n.t('Historical round, read-only')}
									</div>
								{/if}

								{#if detail.assignment.scoring_mode === 'dimensions'}
									<!-- Rubric: pick a score per criterion; the total below is derived -->
									<div>
										<div class="mb-1.5 text-xs font-medium text-gray-400">
											{$i18n.t('Rubric')}
										</div>
										<div
											class="divide-y divide-gray-100 dark:divide-gray-800 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden"
										>
											{#each rubricCriteria as criterion}
												<div
													class="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
												>
													<div class="flex-1 min-w-0">
														<div class="text-sm text-gray-700 dark:text-gray-300">
															{criterion.label} / {criterion.max_score}
														</div>
														{#if firstReadByKey[criterion.key]}
															{@const firstRead = firstReadByKey[criterion.key]}
															<div class="mt-0.5 text-[11px] text-gray-400">
																{firstRead.follow_up_at && !firstRead.is_blocking
																	? $i18n.t('Follow-up read')
																	: $i18n.t('First read-through')}: {$i18n.t(
																	FIRST_READ_STATUS_LABELS[firstRead.status]
																)}{#if firstRead.follow_up_at && firstRead.is_blocking}
																	· {$i18n.t(
																		'Fixed, confirmed on follow-up'
																	)}{/if}{#if firstRead.decision}
																	· {$i18n.t('Student')}: {$i18n.t(
																		FIRST_READ_DECISION_LABELS[firstRead.decision]
																	)}{/if}{#if firstRead.decision && firstRead.decision !== 'kept' && firstRead.quote_unchanged}
																	· <span class="text-rose-600 dark:text-rose-400"
																		>{$i18n.t('Quoted sentence unchanged')}</span
																	>{/if}
															</div>
														{/if}
													</div>
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
								{/if}
								{#if detail.review_history?.length}
									<details class="text-xs text-gray-500">
										<summary>{$i18n.t('评阅历史')}</summary>
										{#each detail.review_history as event}
											<p class="mt-1">
												v{event.review_revision} · {new Date(
													event.created_at * 1000
												).toLocaleString()} · {$i18n.t(
													reviewStatusOptions.find((option) => option.value === event.review_status)
														?.label ?? event.review_status
												)} · {event.score ?? '—'}<br />{event.overall_comment ||
													event.returned_comment ||
													''}
											</p>
										{/each}
									</details>
								{/if}
								<!-- Total score: sum of the rubric scores above, read-only -->
								<div>
									<div class="mb-1.5 text-xs font-medium text-gray-400">
										{$i18n.t('Total Score')}
									</div>
									<div
										class="flex items-center justify-between gap-3 rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3"
									>
										<span class="text-xs text-gray-400 dark:text-gray-500">
											{#if rubricFilledCount < rubricCriteria.length}
												{$i18n.t('Score every rubric criterion to get a total.')}
											{/if}
										</span>
										<span class="shrink-0 text-gray-700 dark:text-gray-300">
											{#if detail.assignment.scoring_mode === 'total'}<input
													aria-label={$i18n.t('Total Score')}
													type="number"
													min="0"
													max={detail.assignment.score_max}
													step="1"
													disabled={isHistoricalRound}
													bind:value={score}
													class="w-24 rounded-lg dark:bg-gray-800"
												/>{:else}<span class="text-lg font-semibold tabular-nums"
													>{score === '' ? '—' : score}</span
												>{/if}
											<span class="text-sm text-gray-400"> / {detail.assignment.score_max}</span>
										</span>
									</div>
								</div>

								{#if hasReflectionAnswers}
									<!-- Reflection quality: the only source of this metric; character counts never were one -->
									<div>
										<div class="mb-1.5 text-xs font-medium text-gray-400">
											{$i18n.t('Reflection Quality')}
										</div>
										<div class="rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3">
											<div class="flex items-center gap-1.5">
												{#each [1, 2, 3, 4, 5] as option}
													<button
														type="button"
														disabled={isHistoricalRound}
														on:click={() => (reflectionScore = String(option))}
														class="h-9 flex-1 rounded-xl border text-sm font-semibold tabular-nums transition-colors disabled:opacity-50 {reflectionScore ===
														String(option)
															? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
															: 'border-gray-200 text-gray-500 hover:border-gray-400 dark:border-gray-800 dark:text-gray-400'}"
													>
														{option}
													</button>
												{/each}
											</div>
											<p class="mt-2 text-xs text-gray-400 dark:text-gray-500">
												{$i18n.t(
													'Rate how well the reflection names what the student actually did and judged. 1 = perfunctory, 5 = specific and self-aware.'
												)}
											</p>
										</div>
									</div>
								{:else}<p class="text-xs text-gray-500">
										{$i18n.t('反思质量：不适用（本轮没有反思回答）')}
									</p>{/if}
								<!-- Prompt quality: replaces counting prompts, which only rewarded asking more -->
								{#if hasRoundPrompts}
									<div>
										<div class="mb-1.5 text-xs font-medium text-gray-400">
											{$i18n.t('Prompt Quality')}
										</div>
										<div class="rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3">
											<div class="flex items-center gap-1.5">
												{#each [1, 2, 3, 4, 5] as option}
													<button
														type="button"
														disabled={isHistoricalRound}
														on:click={() => (promptScore = String(option))}
														class="h-9 flex-1 rounded-xl border text-sm font-semibold tabular-nums transition-colors disabled:opacity-50 {promptScore ===
														String(option)
															? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
															: 'border-gray-200 text-gray-500 hover:border-gray-400 dark:border-gray-800 dark:text-gray-400'}"
													>
														{option}
													</button>
												{/each}
											</div>
											<p class="mt-2 text-xs text-gray-400 dark:text-gray-500">
												{$i18n.t(
													'Rate how the student questioned the AI this round, not how often. 1 = asked it to write for them, 5 = specific questions that pushed their own thinking.'
												)}
											</p>
										</div>
									</div>
								{:else}
									<p class="text-xs text-gray-500">
										{$i18n.t('提问质量：不适用（本轮没有学生提问）')}
									</p>
								{/if}

								<!-- Overall comment -->
								<div>
									<label
										for="review-overall-comment"
										class="mb-1.5 block text-xs font-medium text-gray-400"
									>
										{$i18n.t('Overall Comment')}
									</label>
									<textarea
										id="review-overall-comment"
										bind:value={overallComment}
										disabled={isHistoricalRound}
										class="min-h-24 w-full resize-none rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
										placeholder={$i18n.t('Overall Comment')}
									></textarea>
								</div>

								<!--
									操作分主次:「完成并下一份」是批改的主路径;「保存」停在本份;
									「存草稿」不改状态。退回是另一条路,点开才出现退回意见和重交截止,
									此前这两栏无论退不退回都常驻,占掉半屏。
								-->
								<div class="space-y-3 border-t border-gray-100 pt-4 dark:border-gray-800">
									<div class="flex flex-wrap items-center gap-2">
										<EduButton
											variant="primary"
											disabled={saving || isHistoricalRound}
											on:click={saveReviewAndNext}
										>
											{saving
												? $i18n.t('Saving...')
												: nextPendingId && nextPendingId !== submissionId
													? $i18n.t('Mark Reviewed & Next')
													: $i18n.t('Mark Reviewed')}
										</EduButton>
										{#if nextPendingId && nextPendingId !== submissionId}
											<EduButton
												disabled={saving || isHistoricalRound}
												on:click={() => saveReview('reviewed')}
											>
												{$i18n.t('Mark Reviewed & Stay')}
											</EduButton>
										{/if}
										<EduButton
											variant="link"
											disabled={saving || isHistoricalRound}
											on:click={() =>
												saveReview(
													reviewStatus === 'reviewed'
														? 'reviewed'
														: reviewStatus === 'returned'
															? 'returned'
															: 'pending'
												)}
										>
											{$i18n.t(reviewStatus === 'pending' ? 'Save Draft' : '保存更正')}
										</EduButton>
										{#if lastSavedStr}
											<span class="ml-auto text-xs text-gray-400">
												{$i18n.t('Last saved at {{time}}', { time: lastSavedStr })}
											</span>
										{/if}
									</div>

									<!-- 退回重写由管理员按实例开关；关着时批完即结束，学生直接看批改结果。 -->
									{#if $config?.features?.enable_education_return}
										<div class="rounded-2xl border border-amber-200 dark:border-amber-900/60">
											<button
												type="button"
												class="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-amber-800 dark:text-amber-300"
												aria-expanded={returnMode}
												disabled={isHistoricalRound}
												on:click={() => (returnMode = !returnMode)}
											>
												{$i18n.t('Return for Revision')}
												<span aria-hidden="true" class="text-xs">{returnMode ? '▲' : '▼'}</span>
											</button>
											{#if returnMode}
												<div
													class="space-y-4 border-t border-amber-100 px-4 pb-4 pt-3 dark:border-amber-900/60"
												>
													<div>
														<label
															for="review-returned-comment"
															class="mb-1.5 block text-xs font-medium text-gray-400"
														>
															{$i18n.t('Returned Comment')}
														</label>
														<textarea
															id="review-returned-comment"
															bind:value={returnedComment}
															disabled={isHistoricalRound}
															class="min-h-20 w-full resize-none rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
															placeholder={$i18n.t('Returned Comment')}
														></textarea>
													</div>

													<!--
													让质疑读者就这条意见追问。退回意见此前写完就没下文了，学生看不看、
													改不改全凭自觉；勾上之后，下一轮提交前的质疑会围绕这条展开。
													作业没启用质疑时不显示 —— 不在这里替教师悄悄打开那个环节。
												-->
													{#if detail?.assignment?.challenge_enabled}
														<label
															class="flex cursor-pointer items-start gap-2 rounded-2xl bg-gray-50 px-4 py-3 dark:bg-gray-800"
														>
															<input
																type="checkbox"
																class="mt-0.5 size-3.5 shrink-0 accent-black dark:accent-gray-100"
																bind:checked={challengeFollowup}
																disabled={isHistoricalRound}
															/>
															<span
																class="text-xs leading-relaxed text-gray-700 dark:text-gray-200"
															>
																{$i18n.t('Have the reader follow up on this comment next round')}
															</span>
														</label>
													{/if}

													<!-- Resubmit due at (required when returning for revision) -->
													<div>
														<div class="mb-1.5 block text-xs font-medium text-gray-400">
															{$i18n.t('Resubmit before')}
														</div>
														<EduDateTimeField
															bind:value={resubmitDueLocal}
															disabled={isHistoricalRound}
															className="w-full rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm outline-none focus:border-gray-400 transition-colors disabled:opacity-50"
														/>
													</div>

													<div class="flex justify-end">
														<button
															class="rounded-full bg-amber-600 px-4 py-2 text-sm text-white transition-colors hover:bg-amber-700 disabled:opacity-60"
															disabled={saving || isHistoricalRound}
															on:click={() => saveReview('returned')}
														>
															{$i18n.t('Return to Student')}
														</button>
													</div>
												</div>
											{/if}
										</div>
									{/if}
								</div>
							</div>

							<!-- ── 分析 tab ── -->
						{:else if activeTab === 'analysis'}
							<div class="space-y-5 p-5">
								<TeacherModelSummary usage={roundModelUsage} />
								<!-- Segments -->
								<div>
									<div class="mb-3 flex items-center justify-between">
										<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">
											{$i18n.t('Segment Details')}
										</div>
										<EduButton size="sm" disabled={recomputing} on:click={recomputeAnalysis}>
											{recomputing ? $i18n.t('Recomputing...') : $i18n.t('Recompute Analysis')}
										</EduButton>
									</div>
									{#if analysisSegments.length === 0}
										<div
											class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4 text-sm text-gray-400"
										>
											{$i18n.t('No tracked import segments yet.')}
										</div>
									{:else}
										<div class="space-y-2">
											{#each analysisSegments as segment}
												<button
													class="w-full rounded-2xl border px-4 py-3.5 text-left text-sm transition-colors {expandedSegmentId ===
													segment.segment_id
														? 'border-gray-900 dark:border-gray-100 bg-stone-50 dark:bg-gray-900'
														: 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 hover:border-gray-300 dark:hover:border-gray-600'}"
													on:click={() => focusSegment(segment.segment_id)}
												>
													<!-- Segment header row -->
													<div class="flex items-center justify-between gap-2">
														<div class="font-medium text-gray-900 dark:text-gray-100">
															{getWritingSourceLabel(segment.origin_type, t)}
														</div>
														<div class="flex shrink-0 items-center gap-2">
															{#if segment.is_suspected_unmarked_import}
																<EduBadge soft tone="rose">{$i18n.t('Suspected')}</EduBadge>
															{/if}
															<!-- Chevron -->
															<svg
																class="h-4 w-4 text-gray-400 transition-transform {expandedSegmentId ===
																segment.segment_id
																	? 'rotate-180'
																	: ''}"
																fill="none"
																stroke="currentColor"
																viewBox="0 0 24 24"
															>
																<path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	stroke-width="2"
																	d="M19 9l-7 7-7-7"
																/>
															</svg>
														</div>
													</div>

													<!-- Preview text -->
													<div
														class="mt-1.5 line-clamp-2 whitespace-pre-wrap break-words text-xs text-gray-400"
													>
														{segment.content_initial}
													</div>

													<!-- Inline expanded detail -->
													{#if expandedSegmentId === segment.segment_id}
														<div class="mt-3 border-t border-gray-100 dark:border-gray-800 pt-3">
															<div class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Initial Length')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300"
																		>{segment.initial_length ?? 0}</span
																	>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Final Length')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300"
																		>{segment.final_length ?? 0}</span
																	>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Retained Ratio')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300"
																		>{segment.retained_ratio ?? 0}%</span
																	>
																</div>
																<div class="flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Rewrite Ratio')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300"
																		>{segment.rewrite_ratio ?? 0}%</span
																	>
																</div>
																<div class="col-span-2 flex items-center justify-between">
																	<span class="text-gray-400">{$i18n.t('Rewrite Level')}</span>
																	<span class="font-medium text-gray-700 dark:text-gray-300"
																		>{getRewriteLevelLabel(segment.rewrite_level, t)}</span
																	>
																</div>
																{#if segment.suspicion_score}
																	<div class="col-span-2 flex items-center justify-between">
																		<span class="text-gray-400">{$i18n.t('Suspicion Score')}</span>
																		<span class="font-medium text-rose-600 dark:text-rose-400"
																			>{segment.suspicion_score}</span
																		>
																	</div>
																{/if}
															</div>
															{#if segment.suspicion_reason}
																<div
																	class="mt-2 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:text-rose-300"
																>
																	{$i18n.t(segment.suspicion_reason)}
																</div>
															{/if}
														</div>
													{/if}
												</button>
											{/each}
										</div>
									{/if}
								</div>

								<!-- AI clarification questions：没有就不摆这一块(哈工深关了「询问用户」，永远是空的) -->
								{#if clarifications.length > 0}
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
											<div
												class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4 text-sm text-gray-400"
											>
												{$i18n.t('The AI never paused to ask this student a question.')}
											</div>
										{:else}
											<div
												class="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400"
											>
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
															<div class="mb-1.5 text-[10px] text-gray-400 tabular-nums">
																{formatEpochTime(exchange.created_at)}
															</div>
														{/if}
														<div class="space-y-2.5">
															{#each exchange.questions as question}
																<div>
																	<div class="text-gray-800 dark:text-gray-200">
																		{question.question}
																	</div>
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
																		<div
																			class="mt-1.5 rounded-xl bg-emerald-50 px-3 py-2 text-sm whitespace-pre-wrap break-words text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
																		>
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
								{/if}

								<!-- 提交前读者试读 -->
								<ChallengeRounds detail={challengeDetail} {criteriaLabels} />

								<div bind:this={timelineSection}>
									<TeacherProcessPanel
										bind:this={processPanel}
										submissionId={detail.submission.id}
										finalVersionId={detail.submission.final_version_id}
										events={conversationEvents}
										{editingEvents}
										bind:state={processState}
										bind:catalog={processCatalog}
										onInspect={inspectProcess}
									/>
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
												<TextDiffBlocks blocks={diffData.blocks} />
											{:else}
												<div class="mt-2 text-sm text-gray-400">
													{$i18n.t('No previous round to compare.')}
												</div>
											{/if}
										{/if}
									</div>
								{/if}
							</div>

							<!-- ── 反思 & 版本 tab ── -->
						{:else if activeTab === 'reflection'}
							<div class="space-y-4 p-5">
								<!-- 修订初稿作业:第一次通读的逐项结论与学生的处理 -->
								{#if isReviseDraft}
									<RevisionItemsReview
										sheet={detail?.submission?.stats_json?.revision_items ?? null}
										{criteriaLabels}
									/>
								{/if}

								<!-- Coaching style in force for this round (none when the admin turned coaching styles off) -->
								{#if roundCoaching?.style}
									<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
										<div class="mb-2 text-[11px] text-gray-400">
											{$i18n.t('AI Coaching Style')}
										</div>
										<div class="flex flex-wrap items-center gap-2">
											<span
												class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
											>
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
											<pre
												class="mt-2 whitespace-pre-wrap break-words rounded-xl bg-white dark:bg-gray-850 px-3 py-2 font-sans text-xs leading-6 text-gray-600 dark:text-gray-400">{roundCoaching.prompt}</pre>
										{/if}
										<div class="mt-2 text-[11px] text-gray-400">
											{$i18n.t(
												'Frozen at submission time; later edits to this style do not change it.'
											)}
										</div>
									</div>
								{/if}

								<!-- Coaching-chat thinking in force for this round, frozen at submission time -->
								{#if roundThinking}
									<div
										class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4"
										data-testid="round-thinking"
									>
										<div class="mb-2 text-[11px] text-gray-400">
											{$i18n.t('AI thinking in the coaching chat')}
										</div>
										<div class="flex flex-wrap items-center gap-2">
											<span
												class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
											>
												{$i18n.t(THINKING_SETTING_TEXT[roundThinking.level])}
											</span>
											<span class="text-xs text-gray-400">
												{$i18n.t(THINKING_SOURCE_TEXT[roundThinking.source])}
											</span>
										</div>
										<div class="mt-2 text-[11px] text-gray-400">
											{roundThinking.students_choose
												? $i18n.t(
														'Students could switch thinking off; each reply in the timeline shows what it used.'
													)
												: $i18n.t(
														'Frozen at submission time; later setting changes do not change it.'
													)}
										</div>
									</div>
								{/if}

								<!-- AI use: the one fixed question. Revise-draft students are not asked (the platform starts the first read-through). -->
								{#if !isReviseDraft}
									<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
										<div class="mb-2 text-[11px] text-gray-400">
											{$i18n.t('Did you use AI for this submission?')}
										</div>
										<span
											class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
										>
											{detail.micro_reflection.ai_used
												? $i18n.t('Used AI')
												: $i18n.t('Did not use AI')}
										</span>
									</div>
								{/if}

								<!-- Teacher-defined questions, frozen as they were when the student submitted -->
								{#each detail.micro_reflection.reflection_json.items as item (item.id)}
									<div class="rounded-2xl bg-gray-50 dark:bg-gray-800 px-4 py-4">
										<div class="mb-2 whitespace-pre-wrap text-xs text-gray-500 dark:text-gray-400">
											{item.prompt}
										</div>
										{#if item.kind === 'text'}
											{#if item.text}
												<div
													class="whitespace-pre-wrap text-sm leading-7 text-gray-700 dark:text-gray-300"
												>
													{item.text}
												</div>
											{:else}
												<div class="text-sm text-gray-400">{$i18n.t('Not answered')}</div>
											{/if}
										{:else if item.selected.length || item.other_text}
											<div class="flex flex-wrap gap-2">
												{#each item.selected as option}
													<span
														class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
													>
														{option}
													</span>
												{/each}
												{#if item.other_text}
													<span
														class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-3 py-1 text-xs text-gray-700 dark:text-gray-300"
													>
														{$i18n.t('Other')}: {item.other_text}
													</span>
												{/if}
											</div>
										{:else}
											<div class="text-sm text-gray-400">{$i18n.t('Not answered')}</div>
										{/if}
									</div>
								{/each}

								<!-- Version history -->
								<div>
									<div class="mb-3 flex items-center justify-between">
										<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">
											{$i18n.t('Versions')}
										</div>
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
											<div
												class="flex items-center justify-between gap-3 rounded-2xl border px-4 text-sm transition-colors {isAutosave
													? 'border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40 py-2 opacity-55'
													: 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 py-3'}"
											>
												<span
													class={isAutosave
														? 'text-xs text-gray-500 dark:text-gray-400'
														: 'font-medium text-gray-900 dark:text-gray-100'}
												>
													{$i18n.t('Version')}
													{version.version_no}
												</span>
												<div class="flex items-center gap-2 text-right">
													{#if !isAutosave}
														<EduBadge soft tone="emerald">
															{getVersionTriggerLabel(version.trigger_type, t)}
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
