<script lang="ts">
	import { getContext } from 'svelte';
	import type { SourceRun } from '$lib/utils/writing-source-map';
	import { getWritingComposition } from '$lib/utils/writing-composition';

	export let sourceRuns: SourceRun[];
	export let clarificationAnsweredCount: number | null;

	const i18n = getContext('i18n');
	$: composition = getWritingComposition(sourceRuns);
</script>

<section
	aria-label={$i18n.t('This writing composition')}
	class="mb-4 rounded-xl border border-gray-200 bg-white/70 p-3 text-gray-600 dark:border-gray-800 dark:bg-gray-850/50 dark:text-gray-300"
>
	<h3 class="text-sm font-medium text-gray-800 dark:text-gray-100">
		{$i18n.t('This writing composition')}
	</h3>
	{#if composition.total === 0}
		<p class="mt-2 text-xs">{$i18n.t('Composition will appear as you write.')}</p>
	{:else}
		<dl class="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-xs">
			{#each composition.categories as category (category.key)}
				<div class="flex gap-1">
					<dt>{$i18n.t(category.label)}</dt>
					<dd class="font-medium tabular-nums">{category.percent}%</dd>
				</div>
			{/each}
		</dl>
		<p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('Based on the text currently in your draft. AI sources track in-app insertions and copies.')}
		</p>
	{/if}
	<p class="mt-2 text-xs">
		{$i18n.t('Clarification questions answered')}
		<span class="font-medium tabular-nums">{clarificationAnsweredCount ?? '—'}</span>
	</p>
</section>
