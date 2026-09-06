<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { generateChallengeInsight, getTeacherDashboard } from '$lib/apis/education';
	import type { ChallengeInsight } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import { educationNotificationSummary, models } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduEvidenceDisclaimer from '$lib/components/education/EduEvidenceDisclaimer.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let dashboard = null;
	let loadError = '';
	let refreshing = false;
	let unsubscribeNotifications;
	let notificationsInitialized = false;
	let insight: ChallengeInsight | null = null;
	let insightLoading = false;

	// 只有这一处班级分析会调模型，所以由教师点了才生成，不挂在看板加载上——
	// 挂上去就等于每打开一次看板烧一次调用。
	const loadInsight = async () => {
		const modelId = $models[0]?.id;
		if (!modelId) {
			toast.error(t('Pick a model before generating the analysis.'));
			return;
		}
		insightLoading = true;
		try {
			insight = await generateChallengeInsight(
				localStorage.token,
				$page.params.assignmentId,
				modelId
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			insightLoading = false;
		}
	};

	// 分析结果要能直接变成下一轮的教学配置，否则它只是一张看完就走的图表。
	// 复用既有的「以此为模板新建」流程：连同 rubric 一起带过去，焦点才有意义。
	const useAsNextFocus = (focusKey: string) => {
		goto(
			`/teacher/assignments/new?from=${$page.params.assignmentId}` +
				`&challengeFocus=${encodeURIComponent(focusKey)}`
		);
	};

	const rewriteLevelLabels = {
		unchanged: 'unchanged',
		lightly_edited: 'lightly_edited',
		moderately_rewritten: 'moderately_rewritten',
		deeply_rewritten: 'deeply_rewritten'
	};

	const loadDashboard = async () => {
		refreshing = true;
		try {
			dashboard = await getTeacherDashboard(localStorage.token, $page.params.assignmentId);
			loadError = '';
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			refreshing = false;
		}
	};

	onMount(async () => {
		await loadDashboard();
		// 收到教学通知(如新提交)时后台刷新看板
		unsubscribeNotifications = educationNotificationSummary.subscribe(() => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			loadDashboard();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});
</script>

<TeacherPageShell
	crumbs={[
		{ label: $i18n.t('Teaching') },
		{ label: $i18n.t('Assignments'), href: '/teacher/assignments' },
		{
			label: $i18n.t('Assignment'),
			href: `/teacher/assignments/${$page.params.assignmentId}`
		}
	]}
	title={$i18n.t('Class Overview')}
>
	{#if dashboard}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex items-center justify-end">
			<div class="flex gap-2">
				<EduButton disabled={refreshing} on:click={loadDashboard}>
					{refreshing ? $i18n.t('Refreshing...') : $i18n.t('Refresh')}
				</EduButton>
				<EduButton on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}`)}>
					{$i18n.t('Back')}
				</EduButton>
			</div>
		</div>

		<div class="mb-6 grid gap-4 md:grid-cols-4">
			<EduStatCard
				label="Submissions"
				value={dashboard.summary?.submission_count ?? dashboard.items.length}
			/>
			<EduStatCard
				tone="rose"
				label="Suspected Unmarked Imports"
				value={dashboard.summary?.suspected_unmarked_import_count ?? 0}
			/>
			<EduStatCard tone="amber" label="Large Bursts" value={dashboard.summary?.burst_count ?? 0} />
			<EduStatCard
				label="Average Rewrite Ratio"
				value={`${dashboard.summary?.average_rewrite_ratio ?? 0}%`}
			/>
		</div>

		{#if dashboard.distributions?.challenge}
			{@const challenge = dashboard.distributions.challenge}
			<EduCard class="mb-6">
				<div class="text-sm font-semibold">{$i18n.t('Where the class did not hold up')}</div>
				<!--
					来源占比回答「他用了多少 AI」，这一块回答「这个班普遍在哪个维度上站不住」。
					数据是服务端两份快照比对得出的，不是客户端上报，所以这里不挂
					EduEvidenceDisclaimer。
				-->
				<div class="mt-1 text-xs text-gray-400">
					{$i18n.t('{{completed}} finished the read-through · {{skipped}} skipped it', {
						completed: challenge.completed_students,
						skipped: challenge.skipped_students
					})}
				</div>

				{#if challenge.below_sample_threshold}
					<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
						{$i18n.t(
							'Fewer than {{threshold}} students finished — read these as individual cases, not a class pattern.',
							{ threshold: challenge.sample_threshold }
						)}
					</div>
				{/if}

				<div class="mt-4 space-y-3">
					{#each challenge.criteria as row (row.focus_key)}
						<div
							class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-2xl bg-gray-50 px-4 py-3 dark:bg-gray-800"
						>
							<!-- 给一句能直接拿去讲评的话，不是三个裸数字。 -->
							<div class="text-sm text-gray-700 dark:text-gray-200">
								{$i18n.t(
									'{{label}}: {{challenged}} challenged, {{unresolved}} did not hold up, {{unchanged}} of them left the sentence untouched',
									{
										label: row.label,
										challenged: row.challenged,
										unresolved: row.unresolved,
										unchanged: row.unresolved_unchanged
									}
								)}
							</div>
							<div class="flex items-center gap-3">
								{#if row.critique_total > 0}
									<!--
										写前认得出这个毛病的人次。认得出别人的、写自己时照样犯，
										这个对照才是写前评析和提交前质疑合起来的价值。
									-->
									<span class="text-xs text-gray-400">
										{$i18n.t('{{hits}} of {{total}} spotted it before writing', {
											hits: row.critique_hits,
											total: row.critique_total
										})}
									</span>
								{/if}
								<EduButton variant="link" on:click={() => useAsNextFocus(row.focus_key)}>
									{$i18n.t('Use as next challenge focus')}
								</EduButton>
							</div>
						</div>
					{/each}
				</div>

				<div class="mt-4 border-t border-gray-200 pt-3 dark:border-gray-700">
					{#if insight === null}
						<EduButton disabled={insightLoading} on:click={loadInsight}>
							{insightLoading
								? $i18n.t('Generating...')
								: $i18n.t('Group these into argument patterns')}
						</EduButton>
					{:else if insight.below_threshold}
						<!-- 样本不足就明说，不显示半成品结论：几条文本归纳出的「类型」是噪声。 -->
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t(
								'Only {{count}} students finished — {{threshold}} are needed before grouping means anything.',
								{ count: insight.sample_size, threshold: insight.threshold }
							)}
						</div>
					{:else if insight.categories.length === 0}
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('No shared pattern came out of this round.')}
						</div>
					{:else}
						<div class="space-y-3">
							{#each insight.categories as category (category.name)}
								<div>
									<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
										{category.name}
										<span class="ml-1.5 text-xs font-normal text-gray-400">
											{$i18n.t('{{hits}} occurrences', { hits: category.hits })}
										</span>
									</div>
									{#if category.advice}
										<div class="mt-0.5 text-xs text-gray-600 dark:text-gray-300">
											{category.advice}
										</div>
									{/if}
									{#each category.samples as sample}
										<div
											class="mt-1 border-l-2 border-gray-200 pl-3 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400"
										>
											{sample}
										</div>
									{/each}
								</div>
							{/each}
						</div>
						<!-- 样例已脱敏，教师可以直接念给全班听。 -->
						<div class="mt-3 text-xs text-gray-400">
							{$i18n.t('Samples carry no student identity — safe to read out in class.')}
						</div>
					{/if}
				</div>
			</EduCard>
		{/if}

		<div class="mb-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
			<EduCard>
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Rewrite Distribution')}</div>
				<div class="space-y-3">
					{#each Object.entries(dashboard.distributions?.rewrite_levels ?? {}) as [level, count]}
						<div>
							<div class="mb-1 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
								<span>{$i18n.t(rewriteLevelLabels[level] ?? level)}</span>
								<span>{count}</span>
							</div>
							<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
								<div
									class="h-2 rounded-full bg-black dark:bg-gray-100"
									style={`width: ${Math.max(
										8,
										((count as number) / Math.max(
											1,
											Object.values(dashboard.distributions?.rewrite_levels ?? {}).reduce(
												(sum, value) => sum + (value as number),
												0
											)
										)) * 100
									)}%`}
								></div>
							</div>
						</div>
					{/each}
				</div>
			</EduCard>

			<EduCard>
				<div class="text-sm font-semibold">{$i18n.t('Top Risk Submissions')}</div>
				<EduEvidenceDisclaimer class="mt-1.5 mb-4" />
				<div class="space-y-3">
					{#each [...dashboard.items].sort((a, b) => (b.risk_summary?.suspected_unmarked_import_count ?? 0) - (a.risk_summary?.suspected_unmarked_import_count ?? 0) || (b.risk_summary?.burst_count ?? 0) - (a.risk_summary?.burst_count ?? 0)).slice(0, 5) as item}
						<button
							class="w-full rounded-2xl border border-gray-200 dark:border-gray-800 px-4 py-4 text-left text-sm"
							on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
						>
							<div class="font-medium text-gray-900 dark:text-gray-100">{item.student_name}</div>
							<div class="mt-2 flex flex-wrap gap-2 text-xs">
								<EduBadge tone="rose">
									{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
										?.suspected_unmarked_import_count ?? 0}
								</EduBadge>
								<EduBadge tone="amber">
									{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
								</EduBadge>
							</div>
						</button>
					{/each}
				</div>
			</EduCard>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			{#each dashboard.items as item}
				<EduCard interactive on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}>
					<div class="text-lg font-semibold">{item.student_name}</div>
					<div class="mt-3 space-y-1 text-sm text-gray-600 dark:text-gray-400">
						<div>{$i18n.t('Typed')}: {item.source_stats.user_typed_chars ?? 0}</div>
						<div>{$i18n.t('AI inserted')}: {item.source_stats.ai_inserted_chars ?? 0}</div>
						<div>{$i18n.t('AI pasted')}: {item.source_stats.ai_pasted_chars ?? 0}</div>
						<div>{$i18n.t('Prompts')}: {item.prompt_count}</div>
						<div>{$i18n.t('Reflection')}: {item.has_reflection ? t('Yes') : t('No')}</div>
					</div>
					<div class="mt-3 flex flex-wrap gap-2 text-xs">
						<EduBadge tone="rose">
							{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
								?.suspected_unmarked_import_count ?? 0}
						</EduBadge>
						<EduBadge tone="amber">
							{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
						</EduBadge>
						<EduBadge>
							{$i18n.t('Average Rewrite Ratio')}: {item.risk_summary?.average_rewrite_ratio ?? 0}%
						</EduBadge>
					</div>
				</EduCard>
			{/each}
		</div>
		</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<LoadingState messageKey="Loading dashboard..." />
	{/if}
</TeacherPageShell>
