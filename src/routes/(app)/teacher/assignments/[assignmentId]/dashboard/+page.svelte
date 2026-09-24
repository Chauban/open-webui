<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { generateChallengeInsight, getTeacherAssignment, getTeacherDashboard } from '$lib/apis/education';
	import type { ChallengeInsight } from '$lib/apis/education';
	import { getRewriteLevelLabel, resolveErrorMessage } from '$lib/utils/education';
	import { educationNotificationSummary, models } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduEvidenceDisclaimer from '$lib/components/education/EduEvidenceDisclaimer.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduRiskBadges from '$lib/components/education/EduRiskBadges.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { assignmentTabs } from '$lib/components/education/teacher-nav';

	// 这一页是「单份作业」的分析,此前标题写成「班级概览」。风险只在逐份提交上出现,
	// 不再做全班加总(加总看不出是谁);逐人卡片改成能排序的表,和提交列表各司其职:
	// 提交列表管「批到哪了」,这里管「这份作业大家是怎么写出来的」。

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const assignmentId = $page.params.assignmentId;

	let dashboard = null;
	let assignmentTitle = '';
	let loadError = '';
	let unsubscribeNotifications;
	let notificationsInitialized = false;
	let insight: ChallengeInsight | null = null;
	let insightLoading = false;

	type SortKey = 'student' | 'typed' | 'inserted' | 'pasted' | 'prompts' | 'signals';
	let sortKey: SortKey = 'signals';
	let sortDesc = true;

	const COLUMNS: Array<{ key: SortKey; label: string; numeric: boolean }> = [
		{ key: 'student', label: 'Student', numeric: false },
		{ key: 'typed', label: 'Typed', numeric: true },
		{ key: 'inserted', label: 'AI inserted', numeric: true },
		{ key: 'pasted', label: 'AI pasted', numeric: true },
		{ key: 'prompts', label: 'Prompts', numeric: true },
		{ key: 'signals', label: 'Process Signals', numeric: true }
	];

	const signalScore = (item) =>
		(item.risk_summary?.suspected_unmarked_import_count ?? 0) * 1000 +
		(item.risk_summary?.burst_count ?? 0);

	const sortValue = (item, key: SortKey) => {
		switch (key) {
			case 'student':
				return item.student_name ?? '';
			case 'typed':
				return item.source_stats.user_typed_chars ?? 0;
			case 'inserted':
				return item.source_stats.ai_inserted_chars ?? 0;
			case 'pasted':
				return item.source_stats.ai_pasted_chars ?? 0;
			case 'prompts':
				return item.prompt_count ?? 0;
			default:
				return signalScore(item);
		}
	};

	const setSort = (key: SortKey) => {
		if (sortKey === key) {
			sortDesc = !sortDesc;
		} else {
			sortKey = key;
			sortDesc = key !== 'student';
		}
	};

	$: rewriteLevels = Object.entries(
		(dashboard?.distributions?.rewrite_levels ?? {}) as Record<string, number>
	);
	$: rewriteTotal = Math.max(1, rewriteLevels.reduce((sum, [, count]) => sum + count, 0));
	$: flagged = (dashboard?.items ?? [])
		.filter((item) => signalScore(item) > 0)
		.sort((a, b) => signalScore(b) - signalScore(a))
		.slice(0, 5);
	$: sortedItems = [...(dashboard?.items ?? [])].sort((a, b) => {
		const left = sortValue(a, sortKey);
		const right = sortValue(b, sortKey);
		const order =
			typeof left === 'string' ? left.localeCompare(right as string) : (left as number) - (right as number);
		return sortDesc ? -order : order;
	});

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
			insight = await generateChallengeInsight(localStorage.token, assignmentId, modelId);
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
			`/teacher/assignments/new?from=${assignmentId}` +
				`&challengeFocus=${encodeURIComponent(focusKey)}`
		);
	};

	const loadDashboard = async () => {
		try {
			dashboard = await getTeacherDashboard(localStorage.token, assignmentId);
			loadError = '';
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		}
	};

	onMount(async () => {
		getTeacherAssignment(localStorage.token, assignmentId)
			.then((item) => (assignmentTitle = item?.assignment?.title ?? ''))
			.catch(() => {});
		await loadDashboard();
		// 收到教学通知(如新提交)时后台刷新
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
	crumbs={[{ label: $i18n.t('Assignments'), href: '/teacher/assignments' }]}
	title={assignmentTitle}
	tabs={assignmentTabs(assignmentId)}
>
	{#if dashboard}
		<div class="mx-auto max-w-6xl px-4 py-6">
			{#if dashboard.items.length === 0}
				<EduStateCard>{$i18n.t('No submissions yet.')}</EduStateCard>
			{:else}
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
									<EduButton variant="link" on:click={() => useAsNextFocus(row.focus_key)}>
										{$i18n.t('Use as next challenge focus')}
									</EduButton>
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

				<div class="mb-6 grid gap-4 {flagged.length > 0 ? 'lg:grid-cols-[0.9fr_1.1fr]' : ''}">
					<EduCard>
						<div class="mb-4 text-sm font-semibold">{$i18n.t('Rewrite Distribution')}</div>
						{#if rewriteLevels.every(([, count]) => count === 0)}
							<EduEmpty>{$i18n.t('No tracked import segments yet.')}</EduEmpty>
						{:else}
							<div class="space-y-3">
								{#each rewriteLevels as [level, count]}
									<div>
										<div
											class="mb-1 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300"
										>
											<span>{getRewriteLevelLabel(level, t)}</span>
											<span class="tabular-nums">{count}</span>
										</div>
										<div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
											<div
												class="h-2 rounded-full bg-black dark:bg-gray-100"
												style={`width: ${(count / rewriteTotal) * 100}%`}
											></div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</EduCard>

					{#if flagged.length > 0}
						<EduCard>
							<div class="text-sm font-semibold">{$i18n.t('Look at these first')}</div>
							<EduEvidenceDisclaimer class="mb-4 mt-1.5" />
							<div class="space-y-2">
								{#each flagged as item}
									<a
										href={`/teacher/submissions/${item.submission_id}`}
										class="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-gray-200 px-4 py-3 text-sm transition hover:border-gray-400 dark:border-gray-800 dark:hover:border-gray-600"
									>
										<span class="font-medium text-gray-900 dark:text-gray-100">{item.student_name}</span>
										<EduRiskBadges summary={item.risk_summary} />
									</a>
								{/each}
							</div>
						</EduCard>
					{/if}
				</div>

				<EduCard padding="none">
					<div class="border-b border-gray-100 px-4 py-3 text-sm font-semibold dark:border-gray-800">
						{$i18n.t('How each submission was written')}
					</div>
					<div class="overflow-x-auto">
						<table class="w-full min-w-[44rem] text-sm">
							<thead
								class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
							>
								<tr>
									{#each COLUMNS as column}
										<th
											class="px-4 py-2.5 font-medium {column.numeric && column.key !== 'signals'
												? 'text-right'
												: ''}"
											aria-sort={sortKey === column.key
												? sortDesc
													? 'descending'
													: 'ascending'
												: 'none'}
										>
											<button
												type="button"
												class="inline-flex items-center gap-1 hover:text-gray-900 dark:hover:text-gray-100"
												on:click={() => setSort(column.key)}
											>
												{$i18n.t(column.label)}
												{#if sortKey === column.key}
													<span aria-hidden="true">{sortDesc ? '↓' : '↑'}</span>
												{/if}
											</button>
										</th>
									{/each}
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Reflection')}</th>
								</tr>
							</thead>
							<tbody>
								{#each sortedItems as item (item.submission_id)}
									<tr
										class="cursor-pointer border-t border-gray-100 transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
										on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
									>
										<td class="px-4 py-3 font-medium">
											<a
												href={`/teacher/submissions/${item.submission_id}`}
												class="hover:underline"
												on:click|stopPropagation
											>
												{item.student_name}
											</a>
										</td>
										<td class="px-4 py-3 text-right tabular-nums">{item.source_stats.user_typed_chars ?? 0}</td>
										<td class="px-4 py-3 text-right tabular-nums">{item.source_stats.ai_inserted_chars ?? 0}</td>
										<td class="px-4 py-3 text-right tabular-nums">{item.source_stats.ai_pasted_chars ?? 0}</td>
										<td class="px-4 py-3 text-right tabular-nums">{item.prompt_count}</td>
										<td class="px-4 py-3">
											{#if signalScore(item) > 0}
												<EduRiskBadges summary={item.risk_summary} />
											{:else}
												<span class="text-gray-300 dark:text-gray-600">—</span>
											{/if}
										</td>
										<td class="px-4 py-3 text-gray-600 dark:text-gray-300">
											{item.has_reflection ? $i18n.t('Yes') : $i18n.t('No')}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</EduCard>
			{/if}
		</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<LoadingState messageKey="Loading dashboard..." />
	{/if}
</TeacherPageShell>
