<script lang="ts">
	// @ts-nocheck
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { page } from '$app/stores';

	import { getTeacherSubmissionDetail } from '$lib/apis/education';
	import SourceHighlightedText from '$lib/components/education/SourceHighlightedText.svelte';

	let detail = null;
	let loaded = false;
	let loadError = '';
	let highlight = true;

	onMount(async () => {
		try {
			detail = await getTeacherSubmissionDetail(localStorage.token, $page.params.submissionId);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loaded = true;
		}
	});
</script>

{#if loaded && detail}
	<div class="mx-auto grid max-w-7xl gap-4 px-4 py-6 lg:grid-cols-[1.2fr_0.8fr]">
		<div class="rounded-3xl border border-gray-200 bg-white p-6">
			<div class="mb-4 flex items-center justify-between">
				<div>
					<div class="text-xs uppercase tracking-[0.2em] text-gray-500">Submission Review</div>
					<h1 class="text-2xl font-semibold">{detail.assignment.title}</h1>
				</div>
				<label class="flex items-center gap-2 text-sm text-gray-600">
					<input type="checkbox" bind:checked={highlight} />
					Highlight sources
				</label>
			</div>

			<div class="rounded-2xl bg-stone-50 p-5">
				{#if highlight}
					<SourceHighlightedText
						text={detail.final_version.note_snapshot_text ?? detail.note?.data?.content?.md ?? ''}
						segments={detail.provenance_segments}
					/>
				{:else}
					<div class="whitespace-pre-wrap leading-7">
						{detail.final_version.note_snapshot_text ?? detail.note?.data?.content?.md ?? ''}
					</div>
				{/if}
			</div>
		</div>

		<div class="space-y-4">
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-sm font-semibold">Source Stats</div>
				<div class="mt-3 grid gap-2 text-sm">
					<div>Typed: {detail.submission.stats_json.user_typed_chars ?? 0}</div>
					<div>AI inserted: {detail.submission.stats_json.ai_inserted_chars ?? 0}</div>
					<div>AI pasted: {detail.submission.stats_json.ai_pasted_chars ?? 0}</div>
					<div>Prompts: {detail.submission.stats_json.prompt_count ?? 0}</div>
					<div>Versions: {detail.submission.stats_json.version_count ?? 0}</div>
				</div>
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-sm font-semibold">Reflection</div>
				<div class="mt-3 text-sm text-gray-600">{detail.micro_reflection.ai_help_type}</div>
				<div class="mt-2 whitespace-pre-wrap text-sm leading-7">{detail.micro_reflection.reflection_text}</div>
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-sm font-semibold">Prompt Timeline</div>
				<div class="mt-3 max-h-80 space-y-3 overflow-y-auto">
					{#each detail.prompt_timeline as item}
						<div class="rounded-2xl bg-gray-50 px-3 py-3 text-sm">
							<div class="mb-1 text-[11px] uppercase tracking-[0.14em] text-gray-500">{item.role}</div>
							<div class="whitespace-pre-wrap break-words">
								{typeof item.content === 'string' ? item.content : JSON.stringify(item.content)}
							</div>
						</div>
					{/each}
				</div>
			</div>

			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-sm font-semibold">Versions</div>
				<div class="mt-3 space-y-2">
					{#each detail.versions as version}
						<div class="rounded-2xl border border-gray-200 px-3 py-3 text-sm">
							<div class="font-medium">V{version.version_no} · {version.trigger_type}</div>
							<div class="mt-1 text-xs text-gray-500">
								{new Date(version.created_at * 1000).toLocaleString()}
							</div>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
{:else if loaded && loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	</div>
{/if}
