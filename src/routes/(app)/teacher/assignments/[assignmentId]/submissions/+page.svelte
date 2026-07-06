<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { getTeacherSubmissions } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getReviewStatusLabel = (value: string) =>
		({
			pending: t('Pending Review'),
			reviewed: t('Reviewed'),
			returned: t('Returned')
		})[value] || value;
	const getAiHelpTypeLabel = (value: string) =>
		(
			{
				'Understand Assignment': t('Understand Assignment'),
				Outline: t('Outline'),
				Examples: t('Examples'),
				'Explain Concepts': t('Explain Concepts'),
				'Revise Structure': t('Revise Structure'),
				Polish: t('Polish'),
				'Check Errors': t('Check Errors'),
				"Help Break Through Writer's Block": t("Help Break Through Writer's Block"),
				'Strengthen Reasoning': t('Strengthen Reasoning'),
				Other: t('Other')
			} as Record<string, string>
		)[value] || value;

	let items = [];
	let loaded = false;
	let loadError = '';
	let selectedStatus = 'all';

	$: filteredItems = items.filter((item) =>
		selectedStatus === 'all' ? true : item.review_status === selectedStatus
	);

	onMount(async () => {
		try {
			items = await getTeacherSubmissions(localStorage.token, $page.params.assignmentId);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loaded = true;
		}
	});
</script>

<TeacherPageShell title="Assignments">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<TeacherSectionNav />

	<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
		<div>
			<div class="text-xs uppercase tracking-[0.2em] text-gray-500">{$i18n.t('Teacher Review')}</div>
			<h1 class="text-2xl font-semibold">{$i18n.t('Submissions')}</h1>
		</div>
		<div class="flex gap-2">
			<button
				class="rounded-full border border-gray-300 px-4 py-2 text-sm"
				on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}`)}
			>
				{$i18n.t('Assignment')}
			</button>
			<button
				class="rounded-full border border-gray-300 px-4 py-2 text-sm"
				on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}/dashboard`)}
			>
				{$i18n.t('Dashboard')}
			</button>
		</div>
	</div>

	<div class="mb-6 flex flex-wrap gap-2">
		<button
			class={`rounded-full border px-4 py-2 text-sm transition ${
				selectedStatus === 'all'
					? 'border-black bg-black text-white'
					: 'border-gray-300 bg-white text-gray-700'
			}`}
			on:click={() => (selectedStatus = 'all')}
		>
			{$i18n.t('All')}
		</button>
		<button
			class={`rounded-full border px-4 py-2 text-sm transition ${
				selectedStatus === 'pending'
					? 'border-black bg-black text-white'
					: 'border-gray-300 bg-white text-gray-700'
			}`}
			on:click={() => (selectedStatus = 'pending')}
		>
			{$i18n.t('To Review')}
		</button>
		<button
			class={`rounded-full border px-4 py-2 text-sm transition ${
				selectedStatus === 'reviewed'
					? 'border-black bg-black text-white'
					: 'border-gray-300 bg-white text-gray-700'
			}`}
			on:click={() => (selectedStatus = 'reviewed')}
		>
			{$i18n.t('Reviewed')}
		</button>
	</div>

	{#if loaded && !loadError}
		{#if filteredItems.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('No submissions match the current filters.')}
			</div>
		{:else}
			<div class="overflow-hidden rounded-3xl border border-gray-200 bg-white">
				<table class="w-full table-fixed">
					<thead class="bg-gray-50 text-left text-sm text-gray-600">
						<tr>
							<th class="px-4 py-3">{$i18n.t('Student')}</th>
							<th class="px-4 py-3">{$i18n.t('Submitted At')}</th>
							<th class="px-4 py-3">{$i18n.t('AI Help')}</th>
							<th class="px-4 py-3">{$i18n.t('Status')}</th>
							<th class="px-4 py-3">{$i18n.t('Open')}</th>
						</tr>
					</thead>
					<tbody>
						{#each filteredItems as item}
							<tr class="border-t border-gray-100 text-sm">
								<td class="px-4 py-4">{item.student_name}</td>
								<td class="px-4 py-4">{new Date(item.submission.submitted_at * 1000).toLocaleString()}</td>
								<td class="px-4 py-4">
									{item.reflection?.ai_help_types?.length
										? item.reflection.ai_help_types.map(getAiHelpTypeLabel).join(' / ')
										: '-'}
								</td>
								<td class="px-4 py-4">{getReviewStatusLabel(item.review_status)}</td>
								<td class="px-4 py-4">
									<button
										class="rounded-full bg-black px-3 py-1.5 text-white"
										on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
									>
										{$i18n.t('View')}
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{:else if loaded && loadError}
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	{/if}
	</div>
</TeacherPageShell>
