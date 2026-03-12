<script lang="ts">
	// @ts-nocheck
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { getTeacherSubmissions } from '$lib/apis/education';

	let items = [];
	let loaded = false;
	let loadError = '';

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

<div class="mx-auto max-w-6xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<div>
			<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Teacher Review</div>
			<h1 class="text-2xl font-semibold">Submissions</h1>
		</div>
		<button
			class="rounded-full border border-gray-300 px-4 py-2 text-sm"
			on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}/dashboard`)}
		>
			Dashboard
		</button>
	</div>

	{#if loaded && !loadError}
		<div class="overflow-hidden rounded-3xl border border-gray-200 bg-white">
			<table class="w-full table-fixed">
				<thead class="bg-gray-50 text-left text-sm text-gray-600">
					<tr>
						<th class="px-4 py-3">Student</th>
						<th class="px-4 py-3">Submitted At</th>
						<th class="px-4 py-3">AI Help</th>
						<th class="px-4 py-3">Open</th>
					</tr>
				</thead>
				<tbody>
					{#each items as item}
						<tr class="border-t border-gray-100 text-sm">
							<td class="px-4 py-4">{item.student_name}</td>
							<td class="px-4 py-4">{new Date(item.submission.submitted_at * 1000).toLocaleString()}</td>
							<td class="px-4 py-4">{item.reflection?.ai_help_type ?? '-'}</td>
							<td class="px-4 py-4">
								<button
									class="rounded-full bg-black px-3 py-1.5 text-white"
									on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
								>
									View
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else if loaded && loadError}
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	{/if}
</div>
