<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	let confirmation: ConfirmDialog;
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
	export let photoTranscriptionEnabled = false;
	export let imageReadingEnabled = false;
	// 替换已有正文前，通过统一确认框说明影响。
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
	let importer: TextImportActions;
	let editor: any = null;

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
	}

	const onImported = async (imported: string, nextInfo: ImportInfo) => {
		const incoming = nextInfo.document ?? textDocument(imported);
		if (nextInfo.kind === 'images' && !info) {
			// The upload choice already says what to insert. Keep the current draft and its cursor.
			await onInsert(documentText(incoming), 'insert', { ...nextInfo, document: incoming });
			show = false;
		} else if (editor && info) {
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
		toast.success(
			nextInfo.purpose === 'photo_to_text'
				? t('照片文字已进入编辑框，请对照原稿核对；□ 表示未辨认清楚的字。')
				: nextInfo.kind === 'images'
					? t('已导入 {{count}} 张图片，请核对图文内容。', { count: nextInfo.names.length })
					: t('已导入 {{name}}，请核对图文内容。', { name: nextInfo.names[0] })
		);
	};

	const insert = async (mode: 'insert' | 'replace') => {
		if (!ready || !info) return;
		if (
			mode === 'replace' &&
			hasContent &&
			!(await confirmation.ask({
				title: t('Replace all text'),
				message: t('This replaces everything you have written so far.'),
				confirmLabel: t('Confirm replacing all text'),
				variant: 'danger'
			}))
		)
			return;
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

<Modal
	bind:show
	size="md"
	title={$i18n.t('导入图文稿件')}
	description={$i18n.t('导入文档或图片，核对后插入或替换当前稿件。导入内容会记录来源。')}
	busy={importing || inserting}
	bodyClassName="flex flex-col gap-3"
>
	<TextImportActions
		bind:this={importer}
		{photoTranscriptionEnabled}
		{imageReadingEnabled}
		{sessionId}
		bind:busy={importing}
		{onImported}
	/>
	<div class="min-h-0 flex-1 overflow-y-auto rounded-xl border border-gray-200 p-4">
		<WritingEditor
			bind:editor
			onImportFiles={async (files) => {
				await importer.importFiles(files);
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
	<svelte:fragment slot="footer">
		<EduButton disabled={importing || inserting} on:click={() => (show = false)}
			>{$i18n.t('Cancel')}</EduButton
		>
		<EduButton variant="danger" disabled={!ready} on:click={() => insert('replace')}>
			{$i18n.t('Replace all text')}
		</EduButton>
		<EduButton variant="primary" disabled={!ready} on:click={() => insert('insert')}>
			{$i18n.t('Insert at cursor')}
		</EduButton>
	</svelte:fragment>
</Modal>

<ConfirmDialog bind:this={confirmation} />
