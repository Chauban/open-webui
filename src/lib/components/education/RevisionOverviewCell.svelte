<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';

	import EduBadge from './EduBadge.svelte';

	// 修订初稿作业一行的修改清单概况(提交列表、本次分析共用)。数据是提交时冻存的那一轮。
	// 「终稿与初稿相同」「说改了、原句未动」只是提示老师去看一眼，不是判定，所以都用灰色。
	export let overview: {
		problem_count: number;
		decisions: { revised: number; partly: number; kept: number };
		claimed_untouched: number;
		unchanged_from_draft: boolean;
	} | null = null;

	const i18n = getContext<Writable<i18nType>>('i18n');
</script>

{#if !overview}
	<span class="text-gray-300 dark:text-gray-600">—</span>
{:else}
	<div class="whitespace-nowrap text-xs">
		{overview.problem_count === 0
			? $i18n.t('Nothing marked to fix')
			: $i18n.t('{{count}} to fix: revised {{revised}} · partly {{partly}} · kept {{kept}}', {
					count: overview.problem_count,
					revised: overview.decisions.revised,
					partly: overview.decisions.partly,
					kept: overview.decisions.kept
				})}
	</div>
	{#if overview.unchanged_from_draft || overview.claimed_untouched}
		<div class="mt-1 flex flex-wrap gap-1">
			{#if overview.unchanged_from_draft}
				<EduBadge soft tone="gray">{$i18n.t('Same as first draft')}</EduBadge>
			{:else}
				<EduBadge soft tone="gray">
					{$i18n.t('{{count}} marked revised, sentence unchanged', {
						count: overview.claimed_untouched
					})}
				</EduBadge>
			{/if}
		</div>
	{/if}
{/if}
