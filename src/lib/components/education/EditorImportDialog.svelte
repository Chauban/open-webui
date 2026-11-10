<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import type { ImportInfo } from '$lib/utils/text-import';
	import EduButton from './EduButton.svelte';
	import TextImportActions from './TextImportActions.svelte';
	import UploadedOriginals from './UploadedOriginals.svelte';
	import WritingEditor from './WritingEditor.svelte';
	import { documentText, textDocument, hasDocumentContent } from '$lib/utils/writing-document';
	import { resolveErrorMessage } from '$lib/utils/education';

	// 从零写作作业的编辑器导入:导入文件或照片 → 预览框里核对、修改 → 插到光标处或替换全文。
	// 插入的文字在写作过程里记为「外部粘贴」,老师在时间线上看得到它来自导入。

	export let show = false;
	export let sessionId: string;
	export let imageReadingEnabled = false;
	// 编辑器里已有正文时,「替换全文」要再点一次确认。
	export let hasContent = false;
	export let onInsert: (
		text: string,
		mode: 'insert' | 'replace',
		info: ImportInfo
	) => Promise<void> | void;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let document = textDocument('');
	let info: ImportInfo | null = null;
	let importing = false;
	let inserting = false;
	let confirmReplace = false;
	let importer: TextImportActions;
	let editor: any = null;
	let insertAtCursor = false;

	export async function importFiles(files: File[]) {
		show = true;
		await tick();
		await importer.importFiles(files);
	}

	$: if (!show) reset();
	$: ready = !!info && hasDocumentContent(document) && !importing && !inserting;

	function reset() {
		document = textDocument('');
		info = null;
		confirmReplace = false;
	}

	const onImported = (imported: string, nextInfo: ImportInfo) => {
		const incoming = nextInfo.document ?? textDocument(imported);
		if (insertAtCursor && editor && info) {
			editor.chain().focus().insertContent(incoming.content).run();
			info = {
				...info,
				names: [...info.names, ...nextInfo.names],
				materials: [...(info.materials ?? []), ...(nextInfo.materials ?? [])]
			};
		} else {
			document = incoming;
			info = nextInfo;
		}
		confirmReplace = false;
		toast.success(
			nextInfo.kind === 'images'
				? t('已导入 {{count}} 张图片，请核对图文内容。', { count: nextInfo.names.length })
				: t('已导入 {{name}}，请核对图文内容。', { name: nextInfo.names[0] })
		);
	};

	const insert = async (mode: 'insert' | 'replace') => {
		if (!ready || !info) return;
		if (mode === 'replace' && hasContent && !confirmReplace) {
			confirmReplace = true;
			return;
		}
		inserting = true;
		try {
			await onInsert(documentText(document), mode, { ...info, document });
			show = false;
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			inserting = false;
		}
	};
</script>

<Modal bind:show size="md">
	<div class="flex max-h-[calc(100dvh-4rem)] flex-col gap-3 px-5 py-5">
		<div>
			<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('导入图文稿件')}
			</h2>
			<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
				{$i18n.t('导入文档或图片，核对后插入或替换当前稿件。导入内容会记录来源。')}
			</p>
		</div>
		<TextImportActions
			bind:this={importer}
			{imageReadingEnabled}
			{sessionId}
			bind:busy={importing}
			{onImported}
		/>
		<div class="min-h-0 flex-1 overflow-y-auto rounded-xl border border-gray-200 p-4">
			<WritingEditor
				bind:editor
				onImportFiles={async (files, source) => {
					insertAtCursor = source === 'paste';
					try {
						await importer.importFiles(files);
					} finally {
						insertAtCursor = false;
					}
				}}
				bind:value={document}
				{sessionId}
				{imageReadingEnabled}
				editable={!importing && !inserting && !!info}
				className="input-prose min-h-56"
				placeholder={$i18n.t('The imported text appears here for you to check.')}
			/>
		</div>
		<UploadedOriginals materials={info?.materials ?? (info?.material ? [info.material] : [])} />
		{#if confirmReplace}
			<p class="text-xs text-rose-600 dark:text-rose-400" role="alert">
				{$i18n.t('This replaces everything you have written so far. Click again to confirm.')}
			</p>
		{/if}
		<div class="flex flex-wrap items-center justify-end gap-2">
			<EduButton disabled={inserting} on:click={() => (show = false)}>{$i18n.t('Cancel')}</EduButton
			>
			<EduButton variant="danger" disabled={!ready} on:click={() => insert('replace')}>
				{confirmReplace ? $i18n.t('Confirm replacing all text') : $i18n.t('Replace all text')}
			</EduButton>
			<EduButton variant="primary" disabled={!ready} on:click={() => insert('insert')}>
				{$i18n.t('Insert at cursor')}
			</EduButton>
		</div>
	</div>
</Modal>
