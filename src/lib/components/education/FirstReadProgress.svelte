<script lang="ts">
	// 修订初稿作业:学生交了初稿后,平台先按评分维度逐项通读(要半分钟上下),
	// 通读完 AI 才给第一轮反馈。这段时间对话锁着,这里告诉学生在等什么;没通读成时给重试。
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';

	import Spinner from '$lib/components/common/Spinner.svelte';

	export let status: 'ready' | 'pending' | 'failed' | null = null;
	export let criteria: string[] = [];
	export let onRetry: () => void = () => {};

	const i18n = getContext<Writable<i18nType>>('i18n');
</script>

<div
	class="mt-3 rounded-2xl border border-gray-200 bg-white px-3 py-2.5 text-xs dark:border-gray-800 dark:bg-gray-900"
	role="status"
>
	{#if status === 'failed'}
		<div class="text-gray-700 dark:text-gray-300">
			{$i18n.t('The first read-through did not finish.')}
			<button
				type="button"
				class="ml-1 font-medium underline underline-offset-2 hover:text-gray-900 dark:hover:text-white"
				on:click={onRetry}
			>
				{$i18n.t('Try again')}
			</button>
		</div>
	{:else}
		<div class="flex items-center gap-2 text-gray-700 dark:text-gray-300">
			<Spinner className="size-3.5 shrink-0" />
			<span>
				{$i18n.t(
					'Reading your draft against each of the {{count}} rubric criteria. This takes about half a minute; then the AI gives its first feedback.',
					{ count: criteria.length }
				)}
			</span>
		</div>
		{#if criteria.length > 0}
			<div class="mt-2 flex flex-wrap gap-1.5">
				{#each criteria as label}
					<span
						class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
					>
						{label}
					</span>
				{/each}
			</div>
		{/if}
	{/if}
</div>
