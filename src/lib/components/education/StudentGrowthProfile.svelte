<script lang="ts">
	// @ts-nocheck
	import { createEventDispatcher, getContext } from 'svelte';
	import { get } from 'svelte/store';

	import EduBadge from './EduBadge.svelte';
	import EduButton from './EduButton.svelte';
	import EduCard from './EduCard.svelte';
	import EduEmpty from './EduEmpty.svelte';
	import EduStatCard from './EduStatCard.svelte';
	import EduTile from './EduTile.svelte';
	import EduTrendChart from './EduTrendChart.svelte';
	import EduTrendStat from './EduTrendStat.svelte';
	import {
		formatDuration,
		formatRatioPercent,
		formatShortDate,
		getAiHelpTypeLabel,
		getReviewStatusLabel
	} from '$lib/utils/education';

	// 教师端与学生端共用同一份画像视图：同一套指标、同一套解释，
	// 只有「能不能点进某次提交」不同。教师看到的和学生看到的必须一致，
	// 否则老师没法拿着这页跟学生讲。
	export let profile;
	export let variant: 'teacher' | 'student' = 'teacher';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const dispatch = createEventDispatcher();

	const STATUS_TONES = {
		unsubmitted: 'gray',
		pending: 'amber',
		reviewed: 'emerald',
		returned: 'rose'
	};

	// insight 的文案在前端拼，后端只给 code + 参数，避免后端产出自然语言绕开 i18n。
	const INSIGHT_TEXT = {
		not_enough_data: () => ['Not enough submissions yet to show a growth trend.', {}],
		digestion_up: (p) => [
			'AI-sourced text is being rewritten more than before (+{{delta}}%).',
			{ delta: Math.round(p.delta ?? 0) }
		],
		digestion_low: (p) => [
			'AI text makes up {{ai}}% of the latest draft but was barely rewritten ({{digestion}}%).',
			{ ai: Math.round((p.ai_ratio ?? 0) * 100), digestion: Math.round(p.digestion_ratio ?? 0) }
		],
		ai_reliance_down: (p) => [
			'AI share of the draft dropped by {{delta}} points.',
			{ delta: Math.round(Math.abs(p.delta ?? 0) * 100) }
		],
		ai_reliance_up: (p) => [
			'AI share of the draft rose by {{delta}} points.',
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
		last_minute_writing: (p) => [
			'{{ratio}}% of the latest draft was written in the final tenth of the writing window.',
			{ ratio: Math.round((p.ratio ?? 0) * 100) }
		],
		process_up: (p) => [
			'Writing process investment is trending up (+{{delta}}).',
			{ delta: Math.round(p.delta ?? 0) }
		],
		reflection_thin: (p) => [
			'Reflections are mostly generic (average quality {{score}}/100).',
			{ score: p.average_score ?? 0 }
		]
	};

	const INSIGHT_TONES = { positive: 'emerald', warning: 'amber', neutral: 'gray' };

	const renderInsight = (insight) => {
		const builder = INSIGHT_TEXT[insight.code];
		if (!builder) return insight.code;
		const [key, params] = builder(insight.params ?? {});
		return t(key, params);
	};

	$: timeline = profile?.timeline ?? [];
	$: labels = timeline.map((point) => formatShortDate(point.submitted_at));
	$: trends = Object.fromEntries((profile?.trends ?? []).map((trend) => [trend.key, trend]));
	$: latest = timeline.at(-1) ?? null;

	// rubric 各维度直接从时间线上取，未评的那次留空，折线自然断开。
	$: rubricKeys = Array.from(
		new Set(
			timeline.flatMap((point) =>
				Object.entries(point.rubric ?? {})
					.filter(([, value]) => typeof value === 'number')
					.map(([key]) => key)
			)
		)
	);
	const RUBRIC_TONES = ['sky', 'emerald', 'violet', 'amber', 'rose'];

	$: helpDistribution = Object.entries(profile?.ai_help_type_distribution ?? {}).sort(
		(left, right) => right[1] - left[1]
	);
	$: helpShift = profile?.ai_help_type_shift ?? {};

	const seriesOf = (key: string, label: string, tone: string, mapper = (value) => value) => ({
		key,
		label: t(label),
		tone,
		values: timeline.map((point) => (point[key] == null ? null : mapper(point[key])))
	});

	const trendOf = (key: string) => trends[key] ?? null;
	const roundValue = (value) => (value == null ? null : Math.round(value));
</script>

{#if !profile}
	<EduEmpty>{$i18n.t('No profile data yet.')}</EduEmpty>
{:else}
	<div class="space-y-8">
		<div class="grid gap-4 md:grid-cols-5">
			<EduStatCard label="Assignments" value={profile.assignment_count} />
			<EduStatCard label="Submitted" value={profile.submitted_count} />
			<EduStatCard label="Unsubmitted" value={profile.unsubmitted_count} />
			<EduStatCard label="Reviewed" value={profile.reviewed_count} />
			<EduStatCard
				label="Average Score"
				value={profile.average_score != null ? profile.average_score : '—'}
			/>
		</div>

		{#if profile.insights?.length}
			<EduCard>
				<div class="mb-3 text-sm font-semibold">{$i18n.t('What the data shows')}</div>
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
							<span class="text-gray-700 dark:text-gray-300">{renderInsight(insight)}</span>
						</li>
					{/each}
				</ul>
			</EduCard>
		{/if}

		<!-- 产出维：分数没有统一满分，所以只呈现原值与变化，不折算成任何指数。 -->
		<EduCard>
			<div class="mb-1 text-sm font-semibold">{$i18n.t('Output')}</div>
			<div class="mb-5 text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('Teacher scores and draft length, shown as raw values over time.')}
			</div>

			<div class="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
				<EduTrendStat
					label="Latest Score"
					hint="Score given by the teacher on the most recent submission."
					value={latest?.score ?? null}
					delta={trendOf('score')?.delta ?? null}
					direction={trendOf('score')?.direction ?? null}
					higherIsBetter="yes"
					format={(value) => `${Math.round(value)}`}
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
						{$i18n.t('Score')}
					</div>
					<EduTrendChart
						{labels}
						series={[seriesOf('score', 'Score', 'emerald')]}
						formatValue={(value) => `${Math.round(value)}`}
					/>
				</div>
				<div>
					<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
						{$i18n.t('Draft Length')}
					</div>
					<EduTrendChart
						{labels}
						series={[seriesOf('total_chars', 'Draft Length', 'sky')]}
						formatValue={(value) => `${Math.round(value)}`}
					/>
				</div>
			</div>

			{#if rubricKeys.length}
				<div class="mt-8">
					<div class="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
						{$i18n.t('Rubric')}
					</div>
					<EduTrendChart
						{labels}
						series={rubricKeys.map((key, index) => ({
							key,
							label: $i18n.t(key.charAt(0).toUpperCase() + key.slice(1)),
							tone: RUBRIC_TONES[index % RUBRIC_TONES.length],
							values: timeline.map((point) =>
								typeof point.rubric?.[key] === 'number' ? point.rubric[key] : null
							)
						}))}
						formatValue={(value) => `${Math.round(value)}`}
					/>
				</div>
			{/if}
		</EduCard>

		<!-- 过程维 -->
		<EduCard>
			<div class="mb-1 text-sm font-semibold">{$i18n.t('Writing Process')}</div>
			<div class="mb-5 text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('How the draft was built: revisions, time span, and whether it was rushed.')}
			</div>

			<div class="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
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
					label="Last-Minute Writing"
					hint="Share of the text written in the final tenth of the writing window."
					value={latest?.last_minute_ratio ?? null}
					delta={trendOf('last_minute_ratio')?.delta ?? null}
					direction={trendOf('last_minute_ratio')?.direction ?? null}
					higherIsBetter="no"
					format={(value) => formatRatioPercent(value)}
				/>
				<EduTrendStat
					label="Head Start"
					hint="How long before the due time the student first started writing this round."
					value={latest?.lead_time_seconds != null && latest.lead_time_seconds > 0
						? latest.lead_time_seconds
						: null}
					format={(value) => formatDuration(value, t)}
				/>
			</div>

			<EduTrendChart
				{labels}
				min={0}
				max={100}
				series={[seriesOf('process_index', 'Process Index', 'violet')]}
				formatValue={(value) => `${Math.round(value)}`}
			/>
		</EduCard>

		<!-- AI 协作维：AI 占比本身不评好坏，真正有教学意义的是「消化度」。 -->
		<EduCard>
			<div class="mb-1 text-sm font-semibold">{$i18n.t('AI Collaboration')}</div>
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
					hint="Heuristic score from reflection length, concrete actions, locations, and self-judgement."
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

		<!-- 轮次进步：退回—重交之间的改动幅度 -->
		<EduCard>
			<div class="mb-1 text-sm font-semibold">{$i18n.t('Revision Between Rounds')}</div>
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

		<!-- 作业清单：未提交的也要在，缺交本身是画像的一部分 -->
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
											<EduBadge tone="emerald">{$i18n.t('Score')}: {item.score}</EduBadge>
										{/if}
										{#if item.round_no != null && item.round_no > 1}
											<EduBadge>{$i18n.t('Round {{round}}', { round: item.round_no })}</EduBadge>
										{/if}
										{#if item.submitted_at}
											<span class="text-gray-500 dark:text-gray-400">
												{new Date(item.submitted_at * 1000).toLocaleString()}
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

		<!-- 指数不做黑箱：构成随接口一起返回，这里如实列出 -->
		<EduCard tone="muted">
			<details>
				<summary class="cursor-pointer text-sm font-semibold">
					{$i18n.t('How these indexes are calculated')}
				</summary>
				<div class="mt-4 space-y-3 text-xs text-gray-600 dark:text-gray-400">
					<p>
						{$i18n.t(
							'Process Index = average of revision depth (deleted-or-replaced chars / written chars, {{ratio}}% counts as full), writing span (span / {{days}} days), and pacing (1 − last-minute share). Each part is capped at 100.',
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
							'Reflection quality = length (up to 40) + concrete action (20) + concrete location (20) + self-judgement (20).'
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
	</div>
{/if}
