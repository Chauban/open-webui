<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getTeacherDashboard } from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import LoadingState from '$lib/components/education/LoadingState.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
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
			loadError = `${error?.detail ?? error}`;
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

<TeacherPageShell title="Assignments">
	{#if dashboard}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex items-center justify-between">
			<div>
				<div class="text-xs uppercase tracking-[0.2em] text-gray-500">{$i18n.t('Teacher Dashboard')}</div>
				<h1 class="text-2xl font-semibold">{$i18n.t('Class Overview')}</h1>
			</div>
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

		<div class="mb-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
			<EduCard>
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Rewrite Distribution')}</div>
				<div class="space-y-3">
					{#each Object.entries(dashboard.distributions?.rewrite_levels ?? {}) as [level, count]}
						<div>
							<div class="mb-1 flex items-center justify-between text-sm text-gray-700">
								<span>{$i18n.t(rewriteLevelLabels[level] ?? level)}</span>
								<span>{count}</span>
							</div>
							<div class="h-2 rounded-full bg-gray-100">
								<div
									class="h-2 rounded-full bg-black"
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
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Top Risk Submissions')}</div>
				<div class="space-y-3">
					{#each [...dashboard.items].sort((a, b) => (b.risk_summary?.suspected_unmarked_import_count ?? 0) - (a.risk_summary?.suspected_unmarked_import_count ?? 0) || (b.risk_summary?.burst_count ?? 0) - (a.risk_summary?.burst_count ?? 0)).slice(0, 5) as item}
						<button
							class="w-full rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm"
							on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
						>
							<div class="font-medium text-gray-900">{item.student_name}</div>
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
					<div class="mt-3 space-y-1 text-sm text-gray-600">
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
