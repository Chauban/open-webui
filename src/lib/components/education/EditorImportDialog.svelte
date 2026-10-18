<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import type { ImportInfo } from '$lib/utils/text-import';
	import EduButton from './EduButton.svelte';
	import TextImportActions from './TextImportActions.svelte';
	import { EDU_FIELD_CLASS } from './styles';

	// 从零写作作业的编辑器导入:导入文件或照片 → 预览框里核对、修改 → 插到光标处或替换全文。
	// 插入的文字在写作过程里记为「外部粘贴」,老师在时间线上看得到它来自导入。

	export let show = false;
	export let sessionId: string;
	// 编辑器里已有正文时,「替换全文」要再点一次确认。
	export let hasText = false;
	export let onInsert: (text: string, mode: 'insert' | 'replace', info: ImportInfo) => void;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let text = '';
	let info: ImportInfo | null = null;
	let importing = false;
	let confirmReplace = false;

	$: if (!show) reset();
	$: ready = !!info && text.trim().length > 0 && !importing;

	function reset() {
		text = '';
		info = null;
		confirmReplace = false;
	}

	const onImported = (imported: string, nextInfo: ImportInfo) => {
		text = imported;
		info = nextInfo;
		confirmReplace = false;
		toast.success(
			nextInfo.scannedPages
				? t(
						'Read {{name}}; {{count}} scanned page(s) were transcribed by AI. Check the text carefully.',
						{ name: nextInfo.names[0], count: nextInfo.scannedPages }
					)
				: nextInfo.kind === 'images'
				? t(
						'Read the text from {{count}} image(s). Check it against your draft before inserting.',
						{
							count: nextInfo.names.length
						}
					)
				: t('Read from {{name}}. Check the text before inserting.', { name: nextInfo.names[0] })
		);
	};

	const insert = (mode: 'insert' | 'replace') => {
		if (!ready || !info) return;
		if (mode === 'replace' && hasText && !confirmReplace) {
			confirmReplace = true;
			return;
		}
		onInsert(text, mode, info);
		show = false;
	};
</script>

<Modal bind:show size="md">
	<div class="flex max-h-[calc(100dvh-4rem)] flex-col gap-3 px-5 py-5">
		<div>
			<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('Import text into your writing')}
			</h2>
			<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
				{$i18n.t(
					'Import a Word, text or PDF file, or photos of a draft. Check and edit the text below, then insert it. Imported text is recorded as pasted from outside, and your teacher can see that it was imported.'
				)}
			</p>
		</div>
		<TextImportActions {sessionId} bind:busy={importing} {onImported} />
		<textarea
			bind:value={text}
			class="min-h-56 w-full flex-1 resize-none {EDU_FIELD_CLASS}"
			placeholder={$i18n.t('The imported text appears here for you to check.')}
			disabled={importing || !info}
			data-testid="import-preview"
		></textarea>
		{#if confirmReplace}
			<p class="text-xs text-rose-600 dark:text-rose-400" role="alert">
				{$i18n.t('This replaces everything you have written so far. Click again to confirm.')}
			</p>
		{/if}
		<div class="flex flex-wrap items-center justify-end gap-2">
			<EduButton on:click={() => (show = false)}>{$i18n.t('Cancel')}</EduButton>
			<EduButton variant="danger" disabled={!ready} on:click={() => insert('replace')}>
				{confirmReplace ? $i18n.t('Confirm replacing all text') : $i18n.t('Replace all text')}
			</EduButton>
			<EduButton variant="primary" disabled={!ready} on:click={() => insert('insert')}>
				{$i18n.t('Insert at cursor')}
			</EduButton>
		</div>
	</div>
</Modal>
