<script lang="ts">
	import { getContext } from 'svelte';
	import EduBadge from './EduBadge.svelte';

	// 风险药丸组：概述页此前在待批改/最近提交/最近作业/班级四处各拼各的指标，
	// 同一份提交的数字被重复展示四遍。风险是「一份提交」的属性，作业级/班级级
	// 只是把它们加起来，所以现在只在提交粒度出现一次，且零值不渲染。
	export let summary: Record<string, number> | null | undefined = undefined;
	// 全零时给一条「未见异常」，区分「查过没问题」和「没数据」。
	export let showClear = false;
	let className = '';
	export { className as class };

	const i18n = getContext('i18n');

	$: importCount = summary?.suspected_unmarked_import_count ?? 0;
	$: burstCount = summary?.burst_count ?? 0;
	$: aiPastedChars = summary?.ai_pasted_chars ?? 0;
	$: hasSignal = importCount > 0 || burstCount > 0 || aiPastedChars > 0;
</script>

{#if hasSignal}
	<div class="flex flex-wrap items-center gap-2 text-xs {className}">
		{#if importCount > 0}
			<EduBadge tone="rose" title={$i18n.t('Suspected Unmarked Imports')}>
				{$i18n.t('Unmarked imports')}: {importCount}
			</EduBadge>
		{/if}
		{#if burstCount > 0}
			<EduBadge tone="amber" title={$i18n.t('Large Bursts')}>
				{$i18n.t('Bursts')}: {burstCount}
			</EduBadge>
		{/if}
		{#if aiPastedChars > 0}
			<EduBadge tone="sky" title={$i18n.t('Characters pasted from AI conversations')}>
				{$i18n.t('AI pasted')}: {aiPastedChars}
			</EduBadge>
		{/if}
	</div>
{:else if showClear}
	<div class="flex flex-wrap items-center gap-2 text-xs {className}">
		<EduBadge tone="emerald">{$i18n.t('No risk signals')}</EduBadge>
	</div>
{/if}
