<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import EduBadge from './EduBadge.svelte';
	import EduButton from './EduButton.svelte';
	import EduCard from './EduCard.svelte';
	import EduEmpty from './EduEmpty.svelte';
	import EduStatCard from './EduStatCard.svelte';
	import EduTile from './EduTile.svelte';
	import EduTrendChart from './EduTrendChart.svelte';
	import EduTrendStat from './EduTrendStat.svelte';
	import type {
		ProfileMetricKey,
		StudentProfile,
		StudentProfileFilters,
		StudentProfileInsight,
		StudentProfileInsightParams,
		TeacherStudentProfile
	} from '$lib/apis/education/types';
	import {
		createGrowthGoal,
		createTeacherStudentNote,
		deleteTeacherStudentNote,
		updateGrowthGoal,
		updateTeacherStudentNote
	} from '$lib/apis/education';
	import { buildRubricDimensions, rubricDimensionSignature } from '$lib/utils/growth-profile';
	import {
		formatDuration,
		formatEpoch,
		formatEpochDate,
		formatRatioPercent,
		formatShortDate,
		getAiHelpTypeLabel,
		getReviewStatusLabel,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 教师端与学生端共用同一份画像视图：同一套指标、同一套解释，
	// 只有「能不能点进某次提交」不同。教师看到的和学生看到的必须一致，
	// 否则老师没法拿着这页跟学生讲。
	export let profile: StudentProfile | TeacherStudentProfile | null;
	export let variant: 'teacher' | 'student' = 'teacher';
	export let filters: StudentProfileFilters = {};

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const dispatch = createEventDispatcher<{
		open: { submissionId: string };
		filter: StudentProfileFilters;
	}>();

	type Section = 'overview' | 'output' | 'process' | 'ai' | 'rounds' | 'assignments';
	let activeSection: Section = 'overview';
	let startDate = filters.start_at
		? new Date(filters.start_at * 1000).toISOString().slice(0, 10)
		: '';
	let endDate = filters.end_at ? new Date(filters.end_at * 1000).toISOString().slice(0, 10) : '';
	let assignmentFilter = filters.assignment_id ?? '';
	let roundFilter = filters.round_no ? `${filters.round_no}` : '';
	let metricVersionFilter = filters.metric_version ?? '';
	let assignmentOptions: StudentProfile['assignments'] = [];
	let roundOptions: number[] = [];
	let goalText = '';
	let goalTargetDate = '';
	let goalClassroomId = '';
	let noteContent = '';
	let savingGoal = false;
	let savingNote = false;
	let editingNoteId = '';
	let editingNoteContent = '';
	type CompletenessItem = {
		label: string;
		status: 'complete' | 'missing' | 'pending' | 'not_applicable';
	};

	const sections: Array<{ key: Section; label: string }> = [
		{ key: 'overview', label: 'Overview' },
		{ key: 'output', label: 'Output' },
		{ key: 'process', label: 'Writing Process' },
		{ key: 'ai', label: 'AI Collaboration' },
		{ key: 'rounds', label: 'Revision Between Rounds' },
		{ key: 'assignments', label: 'Assignment History' }
	];

	const STATUS_TONES = {
		unsubmitted: 'gray',
		pending: 'amber',
		reviewed: 'emerald',
		returned: 'rose'
	};

	// insight 的文案在前端拼，后端只给 code + 参数，避免后端产出自然语言绕开 i18n。
	const INSIGHT_TEXT: Record<
		string,
		(params: StudentProfileInsightParams) => [string, Record<string, unknown>]
	> = {
		not_enough_data: () => ['Not enough submissions yet to show a growth trend.', {}],
		digestion_up: (p) => [
			'AI-sourced text is being rewritten more than before (+{{delta}}%).',
			{ delta: Math.round(p.delta ?? 0) }
		],
		digestion_low: (p) => [
			'AI text makes up {{ai}}% of the latest draft but was barely rewritten ({{digestion}}%).',
			{ ai: Math.round((p.ai_ratio ?? 0) * 100), digestion: Math.round(p.digestion_ratio ?? 0) }
		],
		ai_share_changed: (p) => [
			'AI share of the draft changed by {{delta}} points; this is neutral unless read with digestion and reflection.',
			{ delta: Math.round((p.delta ?? 0) * 100) }
		],
		round_improvement: (p) => [
			'Scores improved after revision in {{count}} assignment(s), best +{{best}}.',
			{ count: p.count ?? 0, best: p.best_delta ?? 0 }
		],
		round_revision_thin: (p) => [
			'Resubmissions changed less than {{ratio}}% of the text.',
			{ ratio: p.revision_ratio ?? 0 }
		],
		help_type_shift_refining: (p) => [
			'AI use shifted from generating text toward revising own writing (+{{delta}} points).',
			{ delta: Math.round((p.delta ?? 0) * 100) }
		],
		deadline_rush: (p) => [
			'{{ratio}}% of the latest draft was written during the final 24 hours before the deadline or later.',
			{ ratio: Math.round((p.ratio ?? 0) * 100) }
		],
		process_up: (p) => [
			'Writing process investment is trending up (+{{delta}}).',
			{ delta: Math.round(p.delta ?? 0) }
		],
		reflection_thin: (p) => [
			'Reflections are mostly generic (average quality {{score}}/100).',
			{ score: p.average_score ?? 0 }
		],
		ai_revision_productive: (p) => [
			'AI use, rewriting, reflection, revision depth, and score evidence point in the same productive direction.',
			{}
		],
		ai_use_needs_review: (p) => [
			'High AI share currently coincides with shallow rewriting, reflection, and revision without score improvement.',
			{}
		]
	};

	const INSIGHT_TONES = { positive: 'emerald', warning: 'amber', neutral: 'gray' } as const;
	const INSIGHT_ACTION_TEXT: Record<string, string> = {
		complete_more_submissions: 'Next: complete at least three submissions before judging a trend.',
		keep_rewriting_ai_text: 'Next: keep rewriting AI-sourced text in your own reasoning and voice.',
		rewrite_one_ai_section:
			'Next: choose one AI-sourced section and rebuild it with your own evidence.',
		review_ai_use_pattern:
			'Next: compare AI share with digestion and reflection before drawing a conclusion.',
		reuse_successful_revision:
			'Next: reuse the revision method that produced the strongest score improvement.',
		revise_feedback_deeply:
			'Next: make one structural or evidence-level revision before resubmitting.',
		continue_refining_own_writing: 'Next: continue using AI to question and refine your own draft.',
		start_next_assignment_earlier:
			'Next: create the outline at least two days before the deadline.',
		keep_current_process: 'Next: keep the current revision and pacing routine.',
		add_specific_reflection_evidence:
			'Next: name the exact change, location, reason, and next step.',
		repeat_productive_ai_revision:
			'Next: repeat this pattern—question, rewrite, reflect, and verify the result against the rubric.',
		reduce_ai_share_and_deepen_revision:
			'Next: reduce generated text in one section and rebuild it through deeper revision and evidence.'
	};

	const renderInsight = (insight: StudentProfileInsight) => {
		const builder = INSIGHT_TEXT[insight.code];
		if (!builder) return insight.code;
		const [key, params] = builder(insight.params ?? {});
		return t(key, params);
	};

	$: timeline = profile?.timeline ?? [];
	$: crossTimeline = profile?.cross_assignment_timeline ?? [];
	$: labels = crossTimeline.map(
		(point) =>
			`${point.assignment_title} · ${t('Round {{round}}', { round: point.round_no })} · ${formatShortDate(point.submitted_at)}`
	);
	$: axisLabels = crossTimeline.map((point) => formatShortDate(point.submitted_at));
	$: trends = Object.fromEntries((profile?.trends ?? []).map((trend) => [trend.key, trend]));
	$: latest = crossTimeline.at(-1) ?? timeline.at(-1) ?? null;
	// 只统计真的做过试读的轮次，没开试读的轮次不进分母。
	$: challengeRounds = (crossTimeline.length ? crossTimeline : timeline).filter(
		(point) => point.challenge_status != null
	);
	$: challengeCompletedCount = challengeRounds.filter(
		(point) => point.challenge_status === 'completed'
	).length;
	$: challengeSkippedCount = challengeRounds.filter(
		(point) => point.challenge_status === 'skipped'
	).length;
	$: challengeRevisedCount = challengeRounds.filter(
		(point) => point.challenge_revised === true
	).length;
	$: completenessItems = latest
		? ([
				{ label: 'Version data', status: latest.data_completeness.version_data },
				{
					label: 'Editing operations',
					status: latest.data_completeness.editor_operations
				},
				{ label: 'Source tracking', status: latest.data_completeness.source_tracking },
				{ label: 'Comparable score', status: latest.data_completeness.scoring }
			] satisfies CompletenessItem[])
		: [];
	$: if ((profile?.assignments?.length ?? 0) > assignmentOptions.length) {
		assignmentOptions = profile?.assignments ?? [];
	}
	$: if (profile && !metricVersionFilter) metricVersionFilter = profile.metric_version;
	$: if (profile?.timeline) {
		roundOptions = Array.from(
			new Set([...roundOptions, ...profile.timeline.map((point) => point.round_no)])
		).sort((left, right) => left - right);
	}
	$: teacherNotes = profile && 'teacher_notes' in profile ? profile.teacher_notes : [];

	// rubric 各维度直接从时间线上取，未评的那次留空，折线自然断开。
	$: rubricCriteriaByAssignment = Object.fromEntries(
		(profile?.assignments ?? []).map((item) => [
			item.assignment.id,
			Object.fromEntries(
				(item.assignment.rubric_schema?.criteria ?? []).map((criterion) => [
					criterion.key,
					criterion
				])
			)
		])
	);
	$: rubricDimensions = buildRubricDimensions(crossTimeline, rubricCriteriaByAssignment);
	const RUBRIC_TONES = ['sky', 'emerald', 'violet', 'amber', 'rose'];

	$: helpDistribution = Object.entries(profile?.ai_help_type_distribution ?? {}).sort(
		(left, right) => right[1] - left[1]
	);
	$: helpShift = profile?.ai_help_type_shift ?? {};

	const seriesOf = (
		key: ProfileMetricKey,
		label: string,
		tone: 'sky' | 'emerald' | 'amber' | 'rose' | 'violet' | 'gray',
		mapper: (value: number) => number = (value) => value
	) => ({
		key,
		label: t(label),
		tone,
		values: crossTimeline.map((point) => {
			const value = point[key];
			return typeof value === 'number' ? mapper(value) : null;
		})
	});

	const trendOf = (key: ProfileMetricKey) => trends[key] ?? null;
	const roundValue = (value: number | null) => (value == null ? null : Math.round(value));
	const formatLeadTime = (value: number | null) => {
		if (value == null) return '—';
		if (value === 0) return t('At due time');
		return value >= 0
			? t('{{duration}} before due', { duration: formatDuration(value, t) })
			: t('{{duration}} after due', { duration: formatDuration(Math.abs(value), t) });
	};

	const dateToSeconds = (value: string, endOfDay = false) => {
		if (!value) return undefined;
		const suffix = endOfDay ? 'T23:59:59' : 'T00:00:00';
		return Math.floor(new Date(`${value}${suffix}`).getTime() / 1000);
	};

	const applyFilters = () => {
		dispatch('filter', {
			start_at: dateToSeconds(startDate),
			end_at: dateToSeconds(endDate, true),
			assignment_id: assignmentFilter || undefined,
			round_no: roundFilter ? Number(roundFilter) : undefined,
			metric_version: metricVersionFilter || undefined,
			limit: filters.limit ?? 200,
			offset: 0
		});
	};

	const clearFilters = () => {
		startDate = '';
		endDate = '';
		assignmentFilter = '';
		roundFilter = '';
		metricVersionFilter = '';
		dispatch('filter', {});
	};

	const goToOffset = (offset: number) => {
		dispatch('filter', {
			start_at: dateToSeconds(startDate),
			end_at: dateToSeconds(endDate, true),
			assignment_id: assignmentFilter || undefined,
			round_no: roundFilter ? Number(roundFilter) : undefined,
			metric_version: metricVersionFilter || undefined,
			limit: profile?.timeline_pagination.limit ?? 200,
			offset: Math.max(offset, 0)
		});
	};

	const addGoal = async () => {
		if (!profile || goalText.trim().length < 5 || savingGoal) return;
		savingGoal = true;
		try {
			const goal = await createGrowthGoal(localStorage.token, {
				goal_text: goalText.trim(),
				classroom_id:
					goalClassroomId ||
					(profile.classrooms.length === 1 ? profile.classrooms[0].id : undefined),
				target_at: dateToSeconds(goalTargetDate, true)
			});
			profile.growth_goals = [goal, ...profile.growth_goals];
			profile = profile;
			goalText = '';
			goalTargetDate = '';
			goalClassroomId = '';
			toast.success(t('Growth goal added'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingGoal = false;
		}
	};

	const toggleGoal = async (goalId: string, completed: boolean) => {
		if (!profile) return;
		try {
			const updated = await updateGrowthGoal(localStorage.token, goalId, {
				status: completed ? 'active' : 'completed'
			});
			profile.growth_goals = profile.growth_goals.map((goal) =>
				goal.id === goalId ? updated : goal
			);
			profile = profile;
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const addTeacherNote = async () => {
		if (!profile || noteContent.trim().length < 2 || savingNote || !profile.classrooms[0]) return;
		savingNote = true;
		try {
			const note = await createTeacherStudentNote(
				localStorage.token,
				profile.classrooms[0].id,
				profile.student_id,
				{ content: noteContent.trim() }
			);
			if ('teacher_notes' in profile) {
				profile.teacher_notes = [note, ...profile.teacher_notes];
			}
			profile = profile;
			noteContent = '';
			toast.success(t('Teacher note added'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingNote = false;
		}
	};

	const removeTeacherNote = async (noteId: string) => {
		if (!profile) return;
		if (!window.confirm(t('Delete this private teacher note?'))) return;
		try {
			await deleteTeacherStudentNote(localStorage.token, noteId);
			if ('teacher_notes' in profile) {
				profile.teacher_notes = profile.teacher_notes.filter((note) => note.id !== noteId);
			}
			profile = profile;
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const startEditingNote = (noteId: string, content: string) => {
		editingNoteId = noteId;
		editingNoteContent = content;
	};

	const cancelEditingNote = () => {
		editingNoteId = '';
		editingNoteContent = '';
	};

	const saveTeacherNote = async () => {
		if (!profile || !editingNoteId || editingNoteContent.trim().length < 2) return;
		try {
			const updated = await updateTeacherStudentNote(localStorage.token, editingNoteId, {
				content: editingNoteContent.trim()
			});
			if ('teacher_notes' in profile) {
				profile.teacher_notes = profile.teacher_notes.map((note) =>
					note.id === updated.id ? updated : note
				);
			}
			profile = profile;
			cancelEditingNote();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};
</script>

{#if !profile}
	<EduEmpty>{$i18n.t('No profile data yet.')}</EduEmpty>
{:else}
	<div class="space-y-8">
		<EduCard tone="muted">
			<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
				<label class="text-xs text-gray-600 dark:text-gray-300">
					<span class="mb-1 block">{$i18n.t('Start date')}</span>
					<input
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						type="date"
						bind:value={startDate}
					/>
				</label>
				<label class="text-xs text-gray-600 dark:text-gray-300">
					<span class="mb-1 block">{$i18n.t('End date')}</span>
					<input
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						type="date"
						bind:value={endDate}
					/>
				</label>
				<label class="text-xs text-gray-600 dark:text-gray-300">
					<span class="mb-1 block">{$i18n.t('Assignment')}</span>
					<select
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						bind:value={assignmentFilter}
					>
						<option value="">{$i18n.t('All Assignments')}</option>
						{#each assignmentOptions as item}
							<option value={item.assignment.id}>{item.assignment.title}</option>
						{/each}
					</select>
				</label>
				<label class="text-xs text-gray-600 dark:text-gray-300">
					<span class="mb-1 block">{$i18n.t('Round')}</span>
					<select
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						bind:value={roundFilter}
					>
						<option value="">{$i18n.t('All rounds')}</option>
						{#each roundOptions as round}
							<option value={round}>{$i18n.t('Round {{round}}', { round })}</option>
						{/each}
					</select>
				</label>
				<label class="text-xs text-gray-600 dark:text-gray-300">
					<span class="mb-1 block">{$i18n.t('Metric version')}</span>
					<select
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700"
						bind:value={metricVersionFilter}
					>
						{#each profile.available_metric_versions as version}
							<option value={version}
								>{version} · {$i18n.t(
									version === profile.active_metric_version ? 'Current' : 'Historical'
								)}</option
							>
						{/each}
					</select>
				</label>
				<div class="flex items-end gap-2">
					<EduButton variant="primary" on:click={applyFilters}>{$i18n.t('Apply')}</EduButton>
					<EduButton on:click={clearFilters}>{$i18n.t('Clear')}</EduButton>
				</div>
			</div>
			{#if profile.timeline_pagination.total > profile.timeline_pagination.limit}
				<div class="mt-3 flex flex-wrap items-center justify-end gap-2 text-xs text-gray-500">
					<span>
						{profile.timeline_pagination.offset + 1}–{Math.min(
							profile.timeline_pagination.offset + profile.timeline_pagination.limit,
							profile.timeline_pagination.total
						)} / {profile.timeline_pagination.total}
					</span>
					<EduButton
						size="sm"
						disabled={profile.timeline_pagination.offset === 0}
						on:click={() =>
							goToOffset(profile.timeline_pagination.offset - profile.timeline_pagination.limit)}
					>
						{$i18n.t('Previous')}
					</EduButton>
					<EduButton
						size="sm"
						disabled={profile.timeline_pagination.offset + profile.timeline_pagination.limit >=
							profile.timeline_pagination.total}
						on:click={() =>
							goToOffset(profile.timeline_pagination.offset + profile.timeline_pagination.limit)}
					>
						{$i18n.t('Next')}
					</EduButton>
				</div>
			{/if}
		</EduCard>

		<nav
			class="flex gap-1 overflow-x-auto border-b border-gray-200 pb-px dark:border-gray-800"
			aria-label={$i18n.t('Growth profile sections')}
		>
			{#each sections as section}
				<button
					type="button"
					class="shrink-0 rounded-t-lg px-3 py-2 text-sm font-medium transition {activeSection ===
					section.key
						? 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-white'
						: 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'}"
					aria-pressed={activeSection === section.key}
					on:click={() => (activeSection = section.key)}
				>
					{$i18n.t(section.label)}
				</button>
			{/each}
		</nav>

		{#if activeSection === 'overview'}
			{#if profile.filters_applied}
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
					<EduStatCard label="Visible Data Points" value={profile.filtered_summary.point_count} />
					<EduStatCard
						label="Visible Assignments"
						value={profile.filtered_summary.assignment_count}
					/>
					<EduStatCard
						label="Reviewed Points"
						value={profile.filtered_summary.reviewed_point_count}
					/>
					<EduStatCard
						label="Filtered Average Score (%)"
						value={profile.filtered_summary.average_score_percent != null
							? `${profile.filtered_summary.average_score_percent}%`
							: '—'}
					/>
				</div>
			{:else}
				<div class="grid gap-4 md:grid-cols-5">
					<EduStatCard label="Assignments" value={profile.portfolio_summary.assignment_count} />
					<EduStatCard label="Submitted" value={profile.portfolio_summary.submitted_count} />
					<EduStatCard label="Unsubmitted" value={profile.portfolio_summary.unsubmitted_count} />
					<EduStatCard label="Reviewed" value={profile.portfolio_summary.reviewed_count} />
					<EduStatCard
						label="Average Score (%)"
						value={profile.portfolio_summary.average_score_percent != null
							? `${profile.portfolio_summary.average_score_percent}%`
							: '—'}
					/>
				</div>
			{/if}
			{#if profile.excluded_snapshot_count > 0}
				<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
					{$i18n.t('{{count}} data point(s) use another metric version and are excluded.', {
						count: profile.excluded_snapshot_count
					})}
				</div>
			{/if}

			{#if profile.insights?.length}
				<EduCard>
					<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
						<div class="text-sm font-semibold">{$i18n.t('What the data shows')}</div>
						<span class="text-xs text-gray-500">insight {profile.insight_version}</span>
					</div>
					<ul class="space-y-2">
						{#each profile.insights as insight}
							<li class="flex items-start gap-2.5 text-sm">
								<EduBadge tone={INSIGHT_TONES[insight.tone] ?? 'gray'} soft class="mt-0.5 shrink-0">
									{$i18n.t(
										insight.tone === 'positive'
											? 'Progress'
											: insight.tone === 'warning'
												? 'Watch'
												: 'Info'
									)}
								</EduBadge>
								<div class="min-w-0 flex-1">
									<div class="text-gray-700 dark:text-gray-300">{renderInsight(insight)}</div>
									<div
										class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400"
									>
										<span>{$i18n.t('Samples')}: {insight.sample_count}</span>
										<span
											>{$i18n.t('Data completeness')}: {Math.round(
												insight.data_completeness * 100
											)}%</span
										>
										<span>{$i18n.t('Confidence')}: {Math.round(insight.confidence * 100)}%</span>
										<span>{$i18n.t('Priority')}: {insight.priority_score.toFixed(2)}</span>
									</div>
									{#if insight.action_code && INSIGHT_ACTION_TEXT[insight.action_code]}
										<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
											{$i18n.t(INSIGHT_ACTION_TEXT[insight.action_code])}
										</div>
									{/if}
									{#if variant === 'teacher' && insight.submission_id}
										<EduButton
											size="sm"
											class="mt-2"
											on:click={() => dispatch('open', { submissionId: insight.submission_id })}
										>
											{$i18n.t('View evidence')}
										</EduButton>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
				</EduCard>
			{/if}

			<EduCard>
				<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
					<div class="text-sm font-semibold">{$i18n.t('Growth goals')}</div>
					{#if profile.data_completeness.overall_ratio != null}
						<EduBadge>
							{$i18n.t('Overall data completeness')}: {Math.round(
								profile.data_completeness.overall_ratio * 100
							)}%
						</EduBadge>
					{/if}
				</div>
				{#if variant === 'student'}
					<div class="mb-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
						<input
							class="min-w-0 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
							bind:value={goalText}
							maxlength="500"
							placeholder={$i18n.t('Example: create an outline two days before the next deadline')}
						/>
						{#if profile.classrooms.length > 1}
							<select
								class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
								bind:value={goalClassroomId}
								aria-label={$i18n.t('Goal classroom')}
							>
								<option value="">{$i18n.t('All classes')}</option>
								{#each profile.classrooms as classroom}
									<option value={classroom.id}>{classroom.name}</option>
								{/each}
							</select>
						{/if}
						<input
							class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
							type="date"
							aria-label={$i18n.t('Target date')}
							bind:value={goalTargetDate}
						/>
						<EduButton
							variant="primary"
							disabled={savingGoal || goalText.trim().length < 5}
							on:click={addGoal}
						>
							{$i18n.t('Add goal')}
						</EduButton>
					</div>
				{/if}
				{#if profile.growth_goals.length}
					<div class="space-y-2">
						{#each profile.growth_goals as goal}
							<div
								class="flex flex-col gap-2 rounded-lg border border-gray-200 px-3 py-2 sm:flex-row sm:items-center sm:justify-between dark:border-gray-800"
							>
								<div class:line-through={goal.status === 'completed'} class="text-sm">
									{goal.goal_text}
									{#if goal.target_at}
										<span class="ml-2 text-xs text-gray-500">{formatEpochDate(goal.target_at)}</span
										>
									{/if}
								</div>
								{#if variant === 'student'}
									<EduButton
										size="sm"
										on:click={() => toggleGoal(goal.id, goal.status === 'completed')}
									>
										{$i18n.t(goal.status === 'completed' ? 'Reopen' : 'Complete goal')}
									</EduButton>
								{:else}
									<EduBadge tone={goal.status === 'completed' ? 'emerald' : 'gray'}>
										{$i18n.t(goal.status === 'completed' ? 'Completed' : 'Active')}
									</EduBadge>
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<EduEmpty>{$i18n.t('No growth goals yet.')}</EduEmpty>
				{/if}
			</EduCard>

			{#if variant === 'teacher'}
				<EduCard>
					<div class="mb-3 text-sm font-semibold">
						{$i18n.t('Teacher observations and coaching notes')}
					</div>
					<div class="mb-4 flex flex-col gap-2 sm:flex-row">
						<textarea
							class="min-h-20 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
							bind:value={noteContent}
							maxlength="2000"
							placeholder={$i18n.t('Record an observation or coaching follow-up')}
						></textarea>
						<EduButton
							variant="primary"
							disabled={savingNote || noteContent.trim().length < 2}
							on:click={addTeacherNote}
						>
							{$i18n.t('Add note')}
						</EduButton>
					</div>
					{#if teacherNotes.length}
						<div class="space-y-2">
							{#each teacherNotes as note}
								<div
									class="flex items-start justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-800"
								>
									<div class="min-w-0 flex-1">
										{#if editingNoteId === note.id}
											<textarea
												class="min-h-20 w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
												bind:value={editingNoteContent}
												maxlength="2000"
											></textarea>
										{:else}
											<div class="whitespace-pre-wrap text-sm">{note.content}</div>
										{/if}
										<div class="mt-1 text-xs text-gray-500">
											{formatEpoch(note.observed_at)}
											{#if note.edited_at}
												· {$i18n.t('Edited')}{/if}
										</div>
									</div>
									<div class="flex shrink-0 flex-wrap gap-1">
										{#if editingNoteId === note.id}
											<EduButton
												size="sm"
												variant="primary"
												disabled={editingNoteContent.trim().length < 2}
												on:click={saveTeacherNote}
											>
												{$i18n.t('Save')}
											</EduButton>
											<EduButton size="sm" on:click={cancelEditingNote}
												>{$i18n.t('Cancel')}</EduButton
											>
										{:else}
											<EduButton size="sm" on:click={() => startEditingNote(note.id, note.content)}>
												{$i18n.t('Edit')}
											</EduButton>
											<EduButton
												size="sm"
												variant="danger"
												on:click={() => removeTeacherNote(note.id)}
											>
												{$i18n.t('Delete')}
											</EduButton>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{:else}
						<EduEmpty>{$i18n.t('No teacher notes yet.')}</EduEmpty>
					{/if}
				</EduCard>
			{/if}

			<EduCard>
				<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
					<div class="text-sm font-semibold">{$i18n.t('Latest data completeness')}</div>
					<span class="text-xs text-gray-500"
						>metric {profile.metric_version} · {$i18n.t(
							profile.metric_version === profile.active_metric_version ? 'Current' : 'Historical'
						)}{profile.aggregate_materialized && profile.aggregate_revision
							? ` · aggregate r${profile.aggregate_revision}`
							: ''}</span
					>
				</div>
				{#if latest}
					<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
						{#each completenessItems as item}
							<div class="rounded-lg border border-gray-200 px-3 py-2 text-xs dark:border-gray-800">
								<div class="font-medium">{$i18n.t(item.label)}</div>
								<div
									class={item.status === 'complete'
										? 'text-emerald-600 dark:text-emerald-400'
										: item.status === 'missing'
											? 'text-amber-600 dark:text-amber-400'
											: 'text-gray-500 dark:text-gray-400'}
								>
									{$i18n.t(
										item.status === 'complete'
											? 'Complete'
											: item.status === 'missing'
												? 'Data missing'
												: item.status === 'pending'
													? 'Pending'
													: 'Not applicable'
									)}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<EduEmpty>{$i18n.t('No profile data yet.')}</EduEmpty>
				{/if}
			</EduCard>
		{/if}

		<!-- 产出维：分数没有统一满分，所以只呈现原值与变化，不折算成任何指数。 -->
		{#if activeSection === 'output'}
			<EduCard>
				<div class="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold">
					{$i18n.t('Output')}
					<EduBadge>{$i18n.t('Cross-assignment growth')}</EduBadge>
				</div>
				<div class="mb-5 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t(
						'Scores are normalized by each assignment maximum before they are compared over time.'
					)}
				</div>

				<div class="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
					<EduTrendStat
						label="Latest Score (%)"
						hint="Teacher score divided by the assignment maximum."
						value={latest?.normalized_score ?? null}
						delta={trendOf('normalized_score')?.delta ?? null}
						direction={trendOf('normalized_score')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}%`}
					/>
					<EduTrendStat
						label="Draft Length"
						hint="Character count of the submitted draft."
						value={latest?.total_chars ?? null}
						delta={trendOf('total_chars')?.delta ?? null}
						direction={trendOf('total_chars')?.direction ?? null}
						format={(value) => `${Math.round(value)}`}
					/>
				</div>

				<div class="grid gap-8 lg:grid-cols-2">
					<div>
						<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('Normalized Score')}
						</div>
						<EduTrendChart
							{labels}
							{axisLabels}
							min={0}
							max={100}
							series={[seriesOf('normalized_score', 'Normalized Score', 'emerald')]}
							formatValue={(value) => `${Math.round(value)}%`}
						/>
					</div>
					<div>
						<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('Draft Length')}
						</div>
						<EduTrendChart
							{labels}
							{axisLabels}
							series={[seriesOf('total_chars', 'Draft Length', 'sky')]}
							formatValue={(value) => `${Math.round(value)}`}
						/>
					</div>
				</div>

				{#if rubricDimensions.length}
					<div class="mt-8">
						<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('Rubric')}
						</div>
						<EduTrendChart
							{labels}
							{axisLabels}
							min={0}
							max={100}
							series={rubricDimensions.map((dimension, index) => ({
								key: dimension.signature,
								label: dimension.label,
								tone: RUBRIC_TONES[index % RUBRIC_TONES.length],
								values: crossTimeline.map((point) => {
									const criterion =
										rubricCriteriaByAssignment[point.assignment_id]?.[dimension.key];
									const score = point.rubric?.[dimension.key];
									return criterion &&
										rubricDimensionSignature(dimension.key, criterion.label) ===
											dimension.signature &&
										typeof score === 'number'
										? (score / criterion.max_score) * 100
										: null;
								})
							}))}
							formatValue={(value) => `${Math.round(value)}%`}
						/>
					</div>
				{/if}
			</EduCard>
		{/if}

		<!-- 过程维 -->
		{#if activeSection === 'process'}
			<EduCard>
				<div class="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold">
					{$i18n.t('Writing Process')}
					<EduBadge>{$i18n.t('Cross-assignment growth')}</EduBadge>
				</div>
				<div class="mb-5 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('How the draft was built: revisions, time span, and whether it was rushed.')}
				</div>

				<div class="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
					<EduTrendStat
						label="Process Index"
						hint="Average of revision effort, writing span, and pacing. See how it is calculated below."
						value={latest?.process_index ?? null}
						delta={trendOf('process_index')?.delta ?? null}
						direction={trendOf('process_index')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}`}
					/>
					<EduTrendStat
						label="Revision Depth"
						hint="How much text was deleted or replaced, over how much was written. Version counts are not used: one version is just an autosave."
						value={latest?.revision_depth ?? null}
						delta={trendOf('revision_depth')?.delta ?? null}
						direction={trendOf('revision_depth')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}`}
					/>
					<EduTrendStat
						label="Active Writing Time"
						hint="Editing activity clustered into blocks; idle gaps are not counted."
						value={latest?.active_writing_seconds ?? null}
						delta={trendOf('active_writing_seconds')?.delta ?? null}
						direction={trendOf('active_writing_seconds')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => formatDuration(value, t)}
					/>
					<EduTrendStat
						label="End-loaded Writing"
						hint="Share of text written in the final tenth of this submission's own writing window."
						value={latest?.end_loaded_ratio ?? null}
						delta={trendOf('end_loaded_ratio')?.delta ?? null}
						direction={trendOf('end_loaded_ratio')?.direction ?? null}
						higherIsBetter="no"
						format={(value) => formatRatioPercent(value)}
					/>
					<EduTrendStat
						label="Deadline-window Writing"
						hint="Share of text written in the final 24 hours before the deadline or later."
						value={latest?.deadline_window_ratio ?? null}
						delta={trendOf('deadline_window_ratio')?.delta ?? null}
						direction={trendOf('deadline_window_ratio')?.direction ?? null}
						higherIsBetter="no"
						format={(value) => formatRatioPercent(value)}
					/>
					<EduTrendStat
						label="Head Start"
						hint="How long before the due time the student first started writing this round."
						value={latest?.lead_time_seconds ?? null}
						format={formatLeadTime}
					/>
				</div>

				<EduTrendChart
					{labels}
					{axisLabels}
					min={0}
					max={100}
					series={[seriesOf('process_index', 'Process Index', 'violet')]}
					formatValue={(value) => `${Math.round(value)}`}
				/>

				<!--
					面对质疑放在过程维，不放在 AI 协作维：质疑读者不是帮手，
					把它并进「AI 协作」会把两个刻意分开的角色又混回去。
					作业没开试读时整块不渲染——那是「不适用」，不是「表现差」。
				-->
				{#if challengeRounds.length > 0}
					<div class="mt-8 border-t border-gray-200 pt-6 dark:border-gray-800">
						<div class="mb-1 text-sm font-semibold">{$i18n.t('Facing challenges')}</div>
						<div class="mb-4 text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t(
								'Only rounds where a reader challenged the draft before submitting are counted here.'
							)}
						</div>
						<div class="grid gap-6 sm:grid-cols-3">
							<EduTrendStat
								label="Rounds with a read-through"
								hint="How many submitted rounds went through the pre-submission read-through."
								value={challengeCompletedCount}
								format={(value) => `${Math.round(value)}`}
							/>
							<EduTrendStat
								label="Answered rounds"
								hint="Share of reader questions answered in the latest read-through."
								value={latest?.challenge_answer_ratio ?? null}
								higherIsBetter="yes"
								format={(value) => `${Math.round(value)}%`}
							/>
							<EduTrendStat
								label="Revised after the read-through"
								hint="Rounds where the draft actually changed after the reader's closing notes."
								value={challengeRevisedCount}
								higherIsBetter="yes"
								format={(value) => `${Math.round(value)}`}
							/>
						</div>
						{#if challengeSkippedCount > 0}
							<div class="mt-3 text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('Skipped the read-through in {{count}} rounds.', {
									count: challengeSkippedCount
								})}
							</div>
						{/if}
					</div>
				{/if}
			</EduCard>
		{/if}

		<!-- AI 协作维：AI 占比本身不评好坏，真正有教学意义的是「消化度」。 -->
		{#if activeSection === 'ai'}
			<EduCard>
				<div class="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold">
					{$i18n.t('AI Collaboration')}
					<EduBadge>{$i18n.t('Cross-assignment growth')}</EduBadge>
				</div>
				<div class="mb-5 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t(
						'A high AI share is not good or bad by itself. What matters is how much of it was rewritten.'
					)}
				</div>

				<div class="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
					<EduTrendStat
						label="Collaboration Index"
						hint="Average of digestion, question effort, and reflection quality. See how it is calculated below."
						value={latest?.collaboration_index ?? null}
						delta={trendOf('collaboration_index')?.delta ?? null}
						direction={trendOf('collaboration_index')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}`}
					/>
					<EduTrendStat
						label="AI Share"
						hint="Characters that came from AI insert or in-app AI paste, over the whole draft."
						value={latest?.ai_ratio ?? null}
						delta={trendOf('ai_ratio')?.delta ?? null}
						direction={trendOf('ai_ratio')?.direction ?? null}
						format={(value) => formatRatioPercent(value)}
					/>
					<EduTrendStat
						label="Digestion"
						hint="How much of the AI-sourced text was rewritten before submitting. Higher means more digested."
						value={latest?.digestion_ratio ?? null}
						delta={trendOf('digestion_ratio')?.delta ?? null}
						direction={trendOf('digestion_ratio')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}%`}
					/>
					<EduTrendStat
						label="Reflection Quality"
						hint="Structured evidence score from the action, location, judgement, and next step."
						value={latest?.reflection_quality ?? null}
						delta={trendOf('reflection_quality')?.delta ?? null}
						direction={trendOf('reflection_quality')?.direction ?? null}
						higherIsBetter="yes"
						format={(value) => `${Math.round(value)}`}
					/>
				</div>

				<div class="grid gap-8 lg:grid-cols-2">
					<div>
						<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('AI Share vs Digestion')}
						</div>
						<EduTrendChart
							{labels}
							{axisLabels}
							min={0}
							max={100}
							series={[
								seriesOf('ai_ratio', 'AI Share', 'rose', (value) => value * 100),
								seriesOf('digestion_ratio', 'Digestion', 'emerald')
							]}
							formatValue={(value) => `${Math.round(value)}%`}
						/>
					</div>
					<div>
						<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('Prompts and Reflection')}
						</div>
						<EduTrendChart
							{labels}
							{axisLabels}
							series={[
								seriesOf('prompt_count', 'Prompts', 'sky'),
								seriesOf('reflection_quality', 'Reflection Quality', 'amber')
							]}
							formatValue={(value) => `${Math.round(value)}`}
						/>
					</div>
				</div>

				{#if helpDistribution.length}
					<div class="mt-8">
						<div class="mb-3 text-xs font-medium text-gray-500 dark:text-gray-400">
							{$i18n.t('What AI was used for')}
						</div>
						<div class="mb-4 flex flex-wrap gap-2">
							{#each helpDistribution as [helpType, count]}
								<EduBadge>{getAiHelpTypeLabel(helpType, t)} × {count}</EduBadge>
							{/each}
						</div>
						{#if helpShift.recent}
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('Share of AI use aimed at revising own writing')}:
								<span class="font-medium text-gray-700 dark:text-gray-300">
									{formatRatioPercent(helpShift.early?.refining_ratio ?? 0)} →
									{formatRatioPercent(helpShift.recent?.refining_ratio ?? 0)}
								</span>
							</div>
						{/if}
					</div>
				{/if}
			</EduCard>
		{/if}

		<!-- 轮次进步：退回—重交之间的改动幅度 -->
		{#if activeSection === 'rounds'}
			<EduCard>
				<div class="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold">
					{$i18n.t('Revision Between Rounds')}
					<EduBadge>{$i18n.t('Same-assignment round improvement')}</EduBadge>
				</div>
				<div class="mb-4 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('How much changed after the teacher returned the work.')}
				</div>
				{#if !profile.round_progress?.length}
					<EduEmpty>{$i18n.t('No resubmissions yet.')}</EduEmpty>
				{:else}
					<div class="space-y-3">
						{#each profile.round_progress as item}
							<EduTile>
								<div class="flex flex-wrap items-center justify-between gap-3">
									<div>
										<div class="font-medium text-gray-900 dark:text-gray-100">
											{item.assignment_title}
										</div>
										<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
											{$i18n.t('Round {{round}}', { round: item.from_round })} →
											{$i18n.t('Round {{round}}', { round: item.to_round })}
										</div>
									</div>
									<div class="flex flex-wrap items-center gap-2 text-xs">
										<EduBadge tone={item.revision_ratio >= 20 ? 'emerald' : 'amber'}>
											{$i18n.t('Rewritten')}: {item.revision_ratio}%
										</EduBadge>
										<EduBadge>
											{item.char_delta >= 0 ? '+' : ''}{item.char_delta}
											{$i18n.t('chars')}
										</EduBadge>
										{#if item.score_delta != null}
											<EduBadge tone={item.score_delta > 0 ? 'emerald' : 'gray'}>
												{$i18n.t('Score')}: {item.score_delta > 0 ? '+' : ''}{item.score_delta}
											</EduBadge>
										{/if}
										{#if item.turnaround_seconds != null}
											<span class="text-gray-500 dark:text-gray-400">
												{$i18n.t('Turnaround')}: {formatDuration(item.turnaround_seconds, t)}
											</span>
										{/if}
									</div>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>
		{/if}

		<!-- 作业清单：未提交的也要在，缺交本身是画像的一部分 -->
		{#if activeSection === 'assignments'}
			<EduCard>
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment History')}</div>
				{#if !profile.assignments?.length}
					<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
				{:else}
					<div class="space-y-3">
						{#each profile.assignments as item}
							<EduTile>
								<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
									<div>
										<div class="font-medium text-gray-900 dark:text-gray-100">
											{item.assignment.title}
										</div>
										<div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
											<EduBadge tone={STATUS_TONES[item.review_status] ?? 'gray'}>
												{item.review_status === 'unsubmitted'
													? $i18n.t('Unsubmitted')
													: getReviewStatusLabel(item.review_status, t)}
											</EduBadge>
											{#if item.score != null}
												<EduBadge tone="emerald">
													{$i18n.t('Score')}: {item.score}/{item.assignment.score_max}
												</EduBadge>
											{/if}
											{#if item.round_no != null && item.round_no > 1}
												<EduBadge>{$i18n.t('Round {{round}}', { round: item.round_no })}</EduBadge>
											{/if}
											{#if item.submitted_at}
												<span class="text-gray-500 dark:text-gray-400">
													{formatEpoch(item.submitted_at)}
												</span>
											{/if}
										</div>
									</div>
									{#if variant === 'teacher' && item.submission_id}
										<EduButton
											variant="primary"
											class="shrink-0 self-start"
											on:click={() => dispatch('open', { submissionId: item.submission_id })}
										>
											{$i18n.t('Open')}
										</EduButton>
									{/if}
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>
		{/if}

		<!-- 指数对教师不做黑箱：构成随教师端接口返回，这里如实列出。
		     学生端不给 —— 阈值一公开就是刷分说明书（改够三成、写满三天、问够十条），
		     学生看到的是自己的指标值和趋势。 -->
		{#if activeSection === 'overview' && variant === 'teacher'}
			<EduCard tone="muted">
				<details>
					<summary class="cursor-pointer text-sm font-semibold">
						{$i18n.t('How these indexes are calculated')}
					</summary>
					<div class="mt-4 space-y-3 text-xs text-gray-600 dark:text-gray-400">
						<p>
							{$i18n.t(
								'Process Index = average of revision depth (deleted-or-replaced chars / written chars, {{ratio}}% counts as full), writing span (span / {{days}} days), and pacing (1 − end-loaded share). Each part is capped at 100. Missing revision or timing evidence leaves the index unavailable.',
								{
									ratio: Math.round(
										(profile.index_formula?.process_index?.revision_depth?.target ?? 0.3) * 100
									),
									days: Math.round(
										(profile.index_formula?.process_index?.span_effort?.target ?? 259200) / 86400
									)
								}
							)}
						</p>
						<p>
							{$i18n.t(
								'Collaboration Index = average of digestion (rewrite ratio of AI text), question effort (prompts / {{prompts}}), and reflection quality. Submissions with no AI use fall back to reflection quality only.',
								{
									prompts: profile.index_formula?.collaboration_index?.inquiry?.target ?? 10
								}
							)}
						</p>
						<p>
							{$i18n.t(
								'Reflection quality is the 1—5 rating you give the reflection when you review, mapped onto 0—100. It stays empty until the submission is reviewed.'
							)}
						</p>
						<p class="text-gray-500 dark:text-gray-500">
							{$i18n.t(
								'Risk signals such as large bursts and suspected unmarked imports are shown on each submission page and never feed into these indexes.'
							)}
						</p>
					</div>
				</details>
			</EduCard>
		{/if}
	</div>
{/if}
