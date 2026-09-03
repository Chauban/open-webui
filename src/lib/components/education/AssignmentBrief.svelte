<script lang="ts">
	import { getContext } from 'svelte';

	export let assignment: any = null;

	const i18n = getContext('i18n');

	let expanded = false;

	$: description = (assignment?.description ?? '').trim();
	$: criteria = assignment?.rubric_schema?.criteria ?? [];
	$: collapsible = description.length > 140 || description.split('\n').length > 3;
</script>

{#if assignment && (description || criteria.length > 0)}
	<div class="mt-3 rounded-2xl bg-stone-50 dark:bg-gray-900 px-3 py-2.5">
		{#if description}
			<div
				class="text-[11px] font-medium uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400"
			>
				{$i18n.t('Assignment Requirements')}
			</div>
			<div
				class="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-gray-600 dark:text-gray-300 {collapsible &&
				!expanded
					? 'line-clamp-3'
					: ''}"
			>
				{description}
			</div>
			{#if collapsible}
				<button
					type="button"
					class="mt-1 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:underline"
					on:click={() => (expanded = !expanded)}
				>
					{$i18n.t(expanded ? 'Collapse' : 'Expand')}
				</button>
			{/if}
		{/if}
		{#if criteria.length > 0}
			<div class="mt-2 flex flex-wrap items-center gap-1.5">
				<span class="text-[11px] text-gray-500 dark:text-gray-400">{$i18n.t('Rubric')}</span>
				{#each criteria as criterion (criterion.key)}
					<span
						class="rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 px-2 py-0.5 text-[11px] text-gray-600 dark:text-gray-300"
					>
						{criterion.label} · {criterion.max_score}
					</span>
				{/each}
				<span class="text-[11px] text-gray-500 dark:text-gray-400">
					{$i18n.t('Total {{score}} points', { score: assignment.score_max })}
				</span>
			</div>
		{/if}
	</div>
{/if}
