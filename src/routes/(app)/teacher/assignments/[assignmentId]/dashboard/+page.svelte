<script lang="ts">
	// @ts-nocheck
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { toast } from 'svelte-sonner';

	import { getTeacherDashboard } from '$lib/apis/education';

	let dashboard = null;
	let loadError = '';

	onMount(async () => {
		try {
			dashboard = await getTeacherDashboard(localStorage.token, $page.params.assignmentId);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		}
	});
</script>

{#if dashboard}
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-6">
			<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Teacher Dashboard</div>
			<h1 class="text-2xl font-semibold">Class Overview</h1>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			{#each dashboard.items as item}
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="text-lg font-semibold">{item.student_name}</div>
					<div class="mt-3 space-y-1 text-sm text-gray-600">
						<div>Typed: {item.source_stats.user_typed_chars ?? 0}</div>
						<div>AI inserted: {item.source_stats.ai_inserted_chars ?? 0}</div>
						<div>AI pasted: {item.source_stats.ai_pasted_chars ?? 0}</div>
						<div>Prompts: {item.prompt_count}</div>
						<div>Reflection: {item.has_reflection ? 'Yes' : 'No'}</div>
					</div>
				</div>
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
