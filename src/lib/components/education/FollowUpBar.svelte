<script lang="ts">
	// 修订初稿作业:第一次通读时某一项(如综述定位)出了问题,另几项先暂缓。
	// 学生改好那一项后点「改好了，接着看」:平台先确认它改到位了,再给暂缓的几项补上结论,
	// 然后替学生在对话里说一句「请接着看」,AI 按补全后的结论表回复。
	// 只在还有暂缓项时出现;这一行不重复对话内容,只是补看的入口。
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';

	import Spinner from '$lib/components/common/Spinner.svelte';

	export let status: 'idle' | 'running' | 'not_ready' | 'failed' = 'idle';
	export let blockingLabel = '';
	export let deferredLabels: string[] = [];
	export let note: string | null = null;
	export let onFollowUp: () => void = () => {};

	const i18n = getContext<Writable<i18nType>>('i18n');
</script>

<div
	class="mt-3 rounded-2xl border border-gray-200 bg-white px-3 py-2.5 text-xs dark:border-gray-800 dark:bg-gray-900"
	role="status"
>
	{#if status === 'running'}
		<div class="flex items-center gap-2 text-gray-700 dark:text-gray-300">
			<Spinner className="size-3.5 shrink-0" />
			<span>
				{$i18n.t(
					'Checking whether "{{blocking}}" is fixed, then reading the {{count}} items that were waiting. This takes about half a minute.',
					{ blocking: blockingLabel, count: deferredLabels.length }
				)}
			</span>
		</div>
	{:else}
		<div class="flex flex-wrap items-center justify-between gap-2">
			<span class="leading-relaxed text-gray-600 dark:text-gray-300">
				{$i18n.t('{{count}} items are waiting until "{{blocking}}" is fixed: {{items}}.', {
					count: deferredLabels.length,
					blocking: blockingLabel,
					items: deferredLabels.join('、')
				})}
			</span>
			<button
				type="button"
				class="shrink-0 rounded-full bg-black px-3 py-1 text-xs font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200"
				on:click={onFollowUp}
			>
				{$i18n.t('Fixed it, read the rest')}
			</button>
		</div>
		{#if status === 'not_ready'}
			<div class="mt-2 leading-relaxed text-amber-700 dark:text-amber-400">
				{#if note}
					<span class="font-medium">{blockingLabel}</span> · {note}
				{:else}
					{$i18n.t('"{{blocking}}" is not fixed yet.', { blocking: blockingLabel })}
				{/if}
			</div>
		{:else if status === 'failed'}
			<div class="mt-2 text-gray-500 dark:text-gray-400">
				{$i18n.t('The follow-up read did not finish. Try again.')}
			</div>
		{/if}
	{/if}
</div>
