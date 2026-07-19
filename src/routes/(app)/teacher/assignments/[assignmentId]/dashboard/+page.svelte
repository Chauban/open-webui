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
				<button
					class="rounded-full border border-gray-300 px-4 py-2 text-sm disabled:opacity-60"
					disabled={refreshing}
					on:click={loadDashboard}
				>
					{refreshing ? $i18n.t('Refreshing...') : $i18n.t('Refresh')}
				</button>
				<button
					class="rounded-full border border-gray-300 px-4 py-2 text-sm"
					on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}`)}
				>
					{$i18n.t('Back')}
				</button>
			</div>
		</div>

		<div class="mb-6 grid gap-4 md:grid-cols-4">
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Submissions')}</div>
				<div class="mt-2 text-3xl font-semibold">{dashboard.summary?.submission_count ?? dashboard.items.length}</div>
			</div>
			<div class="rounded-3xl border border-rose-200 bg-rose-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-rose-600">{$i18n.t('Suspected Unmarked Imports')}</div>
				<div class="mt-2 text-3xl font-semibold text-rose-700">{dashboard.summary?.suspected_unmarked_import_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-amber-200 bg-amber-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-amber-600">{$i18n.t('Large Bursts')}</div>
				<div class="mt-2 text-3xl font-semibold text-amber-700">{dashboard.summary?.burst_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Average Rewrite Ratio')}</div>
				<div class="mt-2 text-3xl font-semibold">{dashboard.summary?.average_rewrite_ratio ?? 0}%</div>
			</div>
		</div>

		<div class="mb-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
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
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="mb-4 text-sm font-semibold">{$i18n.t('Top Risk Submissions')}</div>
				<div class="space-y-3">
					{#each [...dashboard.items].sort((a, b) => (b.risk_summary?.suspected_unmarked_import_count ?? 0) - (a.risk_summary?.suspected_unmarked_import_count ?? 0) || (b.risk_summary?.burst_count ?? 0) - (a.risk_summary?.burst_count ?? 0)).slice(0, 5) as item}
						<button
							class="w-full rounded-2xl border border-gray-200 px-4 py-4 text-left text-sm"
							on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
						>
							<div class="font-medium text-gray-900">{item.student_name}</div>
							<div class="mt-2 flex flex-wrap gap-2 text-xs">
								<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
									{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
								</div>
								<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
									{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
								</div>
							</div>
						</button>
					{/each}
				</div>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			{#each dashboard.items as item}
				<button
					class="rounded-3xl border border-gray-200 bg-white p-5 text-left transition hover:border-gray-400"
					on:click={() => goto(`/teacher/submissions/${item.submission_id}`)}
				>
					<div class="text-lg font-semibold">{item.student_name}</div>
					<div class="mt-3 space-y-1 text-sm text-gray-600">
						<div>{$i18n.t('Typed')}: {item.source_stats.user_typed_chars ?? 0}</div>
						<div>{$i18n.t('AI inserted')}: {item.source_stats.ai_inserted_chars ?? 0}</div>
						<div>{$i18n.t('AI pasted')}: {item.source_stats.ai_pasted_chars ?? 0}</div>
						<div>{$i18n.t('Prompts')}: {item.prompt_count}</div>
						<div>{$i18n.t('Reflection')}: {item.has_reflection ? t('Yes') : t('No')}</div>
					</div>
					<div class="mt-3 flex flex-wrap gap-2 text-xs">
						<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
							{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
						</div>
						<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
							{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
						</div>
						<div class="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-gray-700">
							{$i18n.t('Average Rewrite Ratio')}: {item.risk_summary?.average_rewrite_ratio ?? 0}%
						</div>
					</div>
				</button>
			{/each}
		</div>
		</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		</div>
	{/if}
</TeacherPageShell>
