<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import type { RevisionReading, ReadingPurpose } from '$lib/apis/education';
	const i18n = getContext<Writable<I18nType>>('i18n');
	export let records: RevisionReading[] = [];
	export let currentText = '';
	export let readonly = false;
	export let busy = false;
	export let onRead: (purpose: ReadingPurpose) => void = () => {};
	export let onDiscuss: (text: string) => void = () => {};
	const titles = {
		first_read: '初次阅读',
		revision_review: '看看这次修改',
		whole_review: '整段复看'
	};
</script>

<section
	class="my-3 max-h-80 overflow-y-auto rounded-xl border border-gray-200 bg-white p-3 text-sm dark:border-gray-700 dark:bg-gray-900"
>
	<h3 class="font-medium">{$i18n.t('AI 阅读意见')}</h3>
	{#if !readonly}
		<p class="mt-1 text-xs text-gray-500">
			{$i18n.t('可继续编辑或直接提交；阅读与复看均不影响提交资格。')}
		</p>
		<div class="my-2 flex flex-wrap gap-3">
			<button
				type="button"
				class="underline disabled:opacity-40"
				disabled={busy}
				on:click={() => onRead('revision_review')}>{$i18n.t('看看这次修改')}</button
			>
			<button
				type="button"
				class="underline disabled:opacity-40"
				disabled={busy}
				on:click={() => onRead('whole_review')}>{$i18n.t('整段复看')}</button
			>
		</div>
	{/if}
	{#if busy}<p class="text-xs text-gray-500">{$i18n.t('正在阅读，你可以继续写作或提交。')}</p>{/if}
	{#each [...records].reverse() as record (record.id)}
		<details
			class="mt-3 border-t border-gray-100 pt-2 dark:border-gray-800"
			open={record.id === records.at(-1)?.id}
		>
			<summary class="cursor-pointer text-xs text-gray-500"
				>{$i18n.t(titles[record.purpose])} · {new Date(record.created_at * 1000).toLocaleString()} · {$i18n.t(
					'要求版本'
				)}
				{record.context.description_version}</summary
			>
			{#if record.source_text !== currentText}<p class="mt-1 text-xs text-amber-700">
					{$i18n.t('这份意见针对当时保存的稿件，当前正文已有变化。')}
				</p>{/if}
			{#if record.status === 'running'}
				<p class="mt-2 text-xs text-gray-500">{$i18n.t('正在阅读，你可以继续写作或提交。')}</p>
			{:else if record.status === 'failed'}
				<p class="mt-2">{$i18n.t('阅读未完成，仍可提交。')}</p>
				{#if !readonly}<button
						type="button"
						disabled={busy}
						class="underline"
						on:click={() => onRead(record.purpose)}>{$i18n.t('重试阅读')}</button
					>{/if}
			{:else if record.feedback}
				<p class="mt-2">{record.feedback.understanding}</p>
				{#each [record.feedback.strength, ...record.feedback.focus].filter(Boolean) as observation}
					{#if observation}
						{#if observation.quote}<blockquote class="my-2 border-l-2 border-stone-300 pl-3">
								{observation.quote}
							</blockquote>{/if}
						<p class="whitespace-pre-wrap">{observation.feedback}</p>
						{#if !readonly}<button
								type="button"
								class="mt-1 text-xs underline"
								on:click={() =>
									onDiscuss(`${$i18n.t('讨论这处')}：${observation.quote || observation.feedback}`)}
								>{$i18n.t('讨论这处')}</button
							>{/if}
					{/if}
				{/each}
				<details class="mt-2">
					<summary class="cursor-pointer text-xs">{$i18n.t('查看整段阅读意见')}</summary>
					<p class="mt-2 whitespace-pre-wrap">{record.feedback.overview}</p>
				</details>
			{/if}
			<details class="mt-2">
				<summary class="cursor-pointer text-xs">{$i18n.t('查看对应稿件')}</summary>
				<p class="mt-2 whitespace-pre-wrap">{record.source_text}</p>
			</details>
		</details>
	{/each}
	{#if !readonly}<button
			class="mt-2 text-xs underline"
			type="button"
			on:click={() => onDiscuss($i18n.t('我想先看别处'))}>{$i18n.t('我想先看别处')}</button
		>{/if}
</section>
