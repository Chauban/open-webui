<script lang="ts">
	import { getContext } from 'svelte';

	export let assignment: any = null;

	const i18n = getContext('i18n');

	// 写作面板头部此前叠了要求卡(三行说明 + 评分维度),笔记本屏上编辑区被压得很矮。
	// 默认收成一行:标签 + 首行要求 + 满分;展开看全文与各维度分值。
	let expanded = false;

	$: description = (assignment?.description ?? '').trim();
	$: criteria = assignment?.rubric_schema?.criteria ?? [];
</script>

{#if assignment && (description || criteria.length > 0)}
	<div class="mt-3 rounded-2xl bg-stone-50 dark:bg-gray-900 px-3 py-2">
		<button
			type="button"
			class="flex w-full items-baseline gap-2 text-left text-xs"
			aria-expanded={expanded}
			on:click={() => (expanded = !expanded)}
		>
			<span class="shrink-0 font-medium text-gray-700 dark:text-gray-300">
				{$i18n.t('Assignment Requirements')}
			</span>
			{#if !expanded}
				<span class="min-w-0 flex-1 truncate text-gray-500 dark:text-gray-400">
					{description.split('\n')[0]}
				</span>
			{:else}
				<span class="flex-1"></span>
			{/if}
			<span class="shrink-0 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300">
				{$i18n.t(expanded ? 'Collapse' : 'Expand')}
			</span>
		</button>

		{#if expanded}
			{#if description}
				<div
					class="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-gray-600 dark:text-gray-300"
				>
					{description}
				</div>
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
		{/if}
	</div>
{/if}
