<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	export let review: {
		round_no: number;
		submitted_at: number;
		review_status: string;
		score?: number | null;
		overall_comment?: string | null;
		rubric?: Record<string, number> | null;
		returned_comment?: string | null;
		resubmit_due_at?: number | null;
		reviewed_at?: number | null;
	};
	export let onRevise: (() => void) | null = null;

	const formatTime = (ts: number | null | undefined) =>
		ts ? new Date(ts * 1000).toLocaleString() : '';
</script>

{#if review.review_status === 'returned'}
	<div
		class="rounded-xl border border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/40 p-4 mb-3"
	>
		<div class="font-semibold text-rose-700 dark:text-rose-300">
			{$i18n.t('Returned for revision')} · {$i18n.t('Round {{round}}', { round: review.round_no })}
		</div>
		{#if review.returned_comment}
			<p class="mt-2 text-sm whitespace-pre-wrap">{review.returned_comment}</p>
		{/if}
		{#if review.resubmit_due_at}
			<div class="mt-2 text-sm font-medium">
				{$i18n.t('Resubmit before')}: {formatTime(review.resubmit_due_at)}
			</div>
		{/if}
		{#if onRevise}
			<button
				class="mt-3 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-sm hover:bg-rose-700"
				on:click={onRevise}
			>
				{$i18n.t('Revise and resubmit')}
			</button>
		{/if}
	</div>
{:else if review.review_status === 'reviewed'}
	<div
		class="rounded-xl border border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40 p-4 mb-3"
	>
		<div class="flex items-center justify-between">
			<div class="font-semibold text-emerald-700 dark:text-emerald-300">
				{$i18n.t('Reviewed')} · {$i18n.t('Round {{round}}', { round: review.round_no })}
			</div>
			{#if review.score !== null && review.score !== undefined}
				<div class="text-2xl font-bold">{review.score}</div>
			{/if}
		</div>
		{#if review.rubric}
			<div class="mt-2 flex gap-4 text-sm">
				{#each Object.entries(review.rubric) as [key, value]}
					<span class="text-gray-600 dark:text-gray-300">{key}: {value}</span>
				{/each}
			</div>
		{/if}
		{#if review.overall_comment}
			<p class="mt-2 text-sm whitespace-pre-wrap">{review.overall_comment}</p>
		{/if}
		<div class="mt-2 text-xs text-gray-500">{formatTime(review.reviewed_at)}</div>
	</div>
{:else}
	<div
		class="rounded-xl border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 p-3 mb-3 text-sm text-gray-600 dark:text-gray-300"
	>
		{$i18n.t('Submitted, awaiting review')} · {$i18n.t('Round {{round}}', {
			round: review.round_no
		})} · {formatTime(review.submitted_at)}
	</div>
{/if}
