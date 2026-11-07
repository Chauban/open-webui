<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import type { RevisionReading, ReadingPurpose } from '$lib/apis/education';
	import ReadingProgress from './ReadingProgress.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import EduButton from './EduButton.svelte';
	const i18n = getContext<Writable<I18nType>>('i18n');
	export let records: RevisionReading[] = [];
	export let currentText = '';
	export let readonly = false;
	export let busy = false;
	export let hasMessages = false;
	export let onRead: (purpose: ReadingPurpose) => void = () => {};
	export let onDiscuss: (text: string) => void = () => {};
	export let onEdit: () => void = () => {};
	let showRecord = false;
	let selectedRecord: RevisionReading | null = null;
	let recordTab: 'feedback' | 'source' = 'feedback';
	const titles = {
		first_read: '先聊聊你的初稿',
		revision_review: '这次修改的反馈',
		whole_review: '整段复看的反馈'
	};
	$: latest = records.at(-1);
	$: waiting = busy || latest?.status === 'running';
	const inspect = (record: RevisionReading, tab: 'feedback' | 'source') => {
		selectedRecord = record;
		recordTab = tab;
		showRecord = true;
	};
</script>

<section
	aria-label={$i18n.t('AI 写作伙伴')}
	class="mx-auto w-full max-w-3xl px-5 pt-6 pb-3 text-sm leading-7"
>
	<div class="mb-3 flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100">
		<span
			class="flex size-7 items-center justify-center rounded-full bg-stone-100 text-xs dark:bg-gray-800"
			aria-hidden="true">AI</span
		>
		{$i18n.t('AI 写作伙伴')}
	</div>
	<details open={!hasMessages || waiting} class="group">
		<summary class="cursor-pointer font-medium text-gray-700 dark:text-gray-200"
			>{$i18n.t(latest ? titles[latest.purpose] : '先聊聊你的初稿')}</summary
		>
		{#if waiting}<ReadingProgress />
		{:else if latest?.status === 'failed'}
			<p class="mt-3">{$i18n.t('这次没能读完。你可以重试，也可以直接聊聊稿子或继续修改。')}</p>
			{#if !readonly}<EduButton size="sm" on:click={() => onRead(latest.purpose)}
					>{$i18n.t('重试阅读')}</EduButton
				>{/if}
		{:else if latest?.feedback}
			<div class="mt-3 space-y-3">
				<p class="whitespace-pre-wrap">{latest.feedback.understanding}</p>
				{#if latest.feedback.strength}<p class="whitespace-pre-wrap">
						{latest.feedback.strength.feedback}
					</p>{/if}
				{#each latest.feedback.focus as observation}
					<div>
						{#if observation.quote}<blockquote
								class="my-2 border-l-2 border-stone-300 pl-3 text-gray-500 dark:border-gray-600"
							>
								{observation.quote}
							</blockquote>{/if}
						<p class="whitespace-pre-wrap">{observation.feedback}</p>
						{#if !readonly}<button
								type="button"
								class="mt-1 text-xs underline underline-offset-4"
								on:click={() =>
									onDiscuss(
										`${$i18n.t('我想讨论这处：')}「${observation.quote || observation.feedback}」\n`
									)}>{$i18n.t('就这处聊聊')}</button
							>{/if}
					</div>
				{/each}
			</div>
			{#if latest.source_text !== currentText}<p class="mt-3 text-xs text-gray-500">
					{$i18n.t('这份反馈针对之前的稿件；你可以继续修改，改好后再请我看看。')}
				</p>{/if}
			<div class="mt-3 flex flex-wrap gap-x-4 text-xs text-gray-500">
				<button
					type="button"
					class="underline underline-offset-4"
					on:click={() => inspect(latest, 'feedback')}>{$i18n.t('展开完整反馈')}</button
				>
				<button
					type="button"
					class="underline underline-offset-4"
					on:click={() => inspect(latest, 'source')}>{$i18n.t('对照当时的稿件')}</button
				>
			</div>
		{:else}
			<p class="mt-3">
				{$i18n.t('初稿已保存。你可以直接在下面说说想讨论的地方，或先去修改稿件。')}
			</p>
			{#if !readonly}<EduButton size="sm" on:click={() => onRead('first_read')}
					>{$i18n.t('请 AI 读读初稿')}</EduButton
				>{/if}
		{/if}
	</details>
	{#if !readonly}
		<p class="mt-4 text-xs leading-5 text-gray-500">
			{$i18n.t('在下面接着聊，或去修改稿件。什么时候交作业，由你决定。')}
		</p>
		<div class="mt-2 flex flex-wrap gap-2">
			<EduButton size="sm" on:click={() => onDiscuss('')}>{$i18n.t('我想讨论其他地方')}</EduButton>
			<EduButton size="sm" on:click={onEdit}>{$i18n.t('去修改稿件')}</EduButton>
			<EduButton size="sm" disabled={waiting} on:click={() => onRead('revision_review')}
				>{$i18n.t('看看这次修改')}</EduButton
			>
			<EduButton size="sm" disabled={waiting} on:click={() => onRead('whole_review')}
				>{$i18n.t('整段复看')}</EduButton
			>
		</div>
	{/if}
	{#if records.length > 1}
		<details class="mt-3 text-xs text-gray-500">
			<summary class="cursor-pointer">{$i18n.t('此前的阅读记录')}</summary>
			{#each [...records].reverse().slice(1) as record (record.id)}
				<button
					type="button"
					class="block py-1 underline"
					on:click={() => inspect(record, 'feedback')}
					>{$i18n.t(titles[record.purpose])} · {new Date(
						record.created_at * 1000
					).toLocaleString()}</button
				>
			{/each}
		</details>
	{/if}
</section>

<Modal bind:show={showRecord} size="md">
	{#if selectedRecord}
		<div class="p-5">
			<div class="mb-4 flex items-center justify-between gap-3">
				<h3 class="font-semibold">{$i18n.t('阅读记录')}</h3>
				<EduButton size="sm" on:click={() => (showRecord = false)}>{$i18n.t('Close')}</EduButton>
			</div>
			<div class="mb-4 flex gap-2">
				<EduButton
					size="sm"
					variant={recordTab === 'feedback' ? 'primary' : 'secondary'}
					on:click={() => (recordTab = 'feedback')}>{$i18n.t('完整反馈')}</EduButton
				>
				<EduButton
					size="sm"
					variant={recordTab === 'source' ? 'primary' : 'secondary'}
					on:click={() => (recordTab = 'source')}>{$i18n.t('当时的稿件')}</EduButton
				>
			</div>
			<p class="mb-3 text-xs text-gray-500">
				{new Date(selectedRecord.created_at * 1000).toLocaleString()} · {$i18n.t(
					'这里保留阅读时的记录，不会替换当前正文。'
				)}
			</p>
			<div class="max-h-[55dvh] overflow-y-auto whitespace-pre-wrap text-sm leading-7">
				{#if recordTab === 'source'}{selectedRecord.source_text}
				{:else if selectedRecord.feedback}{selectedRecord.feedback.overview}
				{:else if selectedRecord.status === 'running'}<ReadingProgress />
				{:else}{$i18n.t('阅读未完成，仍可提交。')}{/if}
			</div>
		</div>
	{/if}
</Modal>
