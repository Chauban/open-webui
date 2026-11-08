<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import type { RevisionReading, ReadingPurpose } from '$lib/apis/education';
	import ReadingProgress from './ReadingProgress.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import EduButton from './EduButton.svelte';
	import EduActionMenu from './EduActionMenu.svelte';
	const i18n = getContext<Writable<I18nType>>('i18n');
	export let record: RevisionReading | null = null;
	export let readonly = false;
	export let busy = false;
	export let onRetry: (purpose: ReadingPurpose) => void = () => {};
	let showSource = false;
	$: actions = record ? [{ label: '对照当时的稿件', onClick: () => (showSource = true) }] : [];
</script>

<article
	class="mx-auto w-full max-w-3xl px-5 py-5 text-sm leading-7"
	aria-label={$i18n.t('AI 写作伙伴')}
>
	<div class="mb-3 flex items-center justify-between gap-2">
		<span class="font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('AI 写作伙伴')}</span>
		{#if record}<EduActionMenu items={actions} />{/if}
	</div>
	{#if record?.status === 'running' || (!record && busy)}<ReadingProgress />
	{:else if record?.feedback}
		<div class="space-y-3">
			{#if record.feedback.understanding}<p class="whitespace-pre-wrap">
					{record.feedback.understanding}
				</p>{/if}
			{#if record.feedback.strength}<p class="whitespace-pre-wrap">
					{record.feedback.strength.feedback}
				</p>{/if}
			{#each record.feedback.focus as observation}
				{#if observation.quote}<blockquote
						class="border-l-2 border-stone-300 pl-3 text-gray-500 dark:border-gray-600"
					>
						{observation.quote}
					</blockquote>{/if}
				<p class="whitespace-pre-wrap">{observation.feedback}</p>
			{/each}
			{#if record.feedback.overview}<p class="whitespace-pre-wrap">
					{record.feedback.overview}
				</p>{/if}
		</div>
	{:else}
		<p>{$i18n.t('这次没能读完。你可以重试，也可以直接聊聊稿子或继续修改。')}</p>
		{#if !readonly}<EduButton
				size="sm"
				disabled={busy}
				on:click={() => onRetry(record?.purpose ?? 'first_read')}>{$i18n.t('重试阅读')}</EduButton
			>{/if}
	{/if}
</article>
<Modal bind:show={showSource} size="md">
	{#if record}<div class="p-5">
			<div class="mb-4 flex justify-between gap-3">
				<h3 class="font-semibold">{$i18n.t('当时的稿件')}</h3>
				<EduButton size="sm" on:click={() => (showSource = false)}>{$i18n.t('Close')}</EduButton>
			</div>
			<p class="mb-3 text-xs text-gray-500">
				{new Date(record.created_at * 1000).toLocaleString()} · {$i18n.t(
					'这里保留阅读时的记录，不会替换当前正文。'
				)}
			</p>
			<div class="max-h-[55dvh] overflow-y-auto whitespace-pre-wrap text-sm leading-7">
				{record.source_text}
			</div>
		</div>{/if}
</Modal>
