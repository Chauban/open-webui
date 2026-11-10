<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';
	import { toast } from 'svelte-sonner';
	import DOMPurify from 'dompurify';
	import { get } from 'svelte/store';
	import RichTextInput from '$lib/components/common/RichTextInput.svelte';
	import { writingExtensions } from './writing-document-extensions';
	import { documentText, textDocument, type WritingNode } from '$lib/utils/writing-document';
	export let editor: any = null;
	export let value: WritingNode = textDocument('');
	export let sessionId = '';
	export let imageReadingEnabled = false;
	export let onChange = (_content: any) => {};
	export let onExternalContent = (_metadata: Record<string, string>) => {};
	export let onImportFiles:
		| ((files: File[], source: 'paste' | 'drop') => Promise<void> | void)
		| null = null;
	const i18n: any = getContext('i18n');
	const dispatch = createEventDispatcher();
	const t = (key: string) => (get(i18n) as any).t(key);
	const extensions = writingExtensions({
		t,
		sessionId: () => sessionId,
		imageReading: () => imageReadingEnabled,
		onTranscription: (metadata) =>
			onExternalContent({ ...metadata, import_kind: 'image_transcription' })
	});
	function importFiles(files: File[], source: 'paste' | 'drop') {
		if (!editor?.isEditable) return;
		if (!onImportFiles) {
			toast.error(t('此处不支持文件导入。'));
			return;
		}
		void Promise.resolve(onImportFiles(files, source)).catch(() =>
			toast.error(t('导入失败，请重试。'))
		);
	}
	function paste(event: CustomEvent) {
		const original = event.detail?.event ?? event;
		const clipboard = original.clipboardData;
		const files = Array.from(clipboard?.files ?? []) as File[];
		if (!files.length) {
			for (const item of Array.from(clipboard?.items ?? []) as DataTransferItem[]) {
				const file = item.getAsFile?.();
				if (file) files.push(file);
			}
		}
		if (files.length) {
			original.preventDefault();
			const html = clipboard?.getData('text/html') ?? '';
			if (
				html &&
				new DOMParser()
					.parseFromString(
						DOMPurify.sanitize(html, { FORBID_TAGS: ['img', 'script', 'style'] }),
						'text/html'
					)
					.body.textContent?.trim()
			) {
				toast.info(t('剪贴板文件先按文件导入；完整图文请上传原文档。'));
			}
			importFiles(files, 'paste');
			return;
		}
		const html = clipboard?.getData('text/html') ?? '';
		if (/<img\b/i.test(html) && !html.includes('data-writing-image')) {
			original.preventDefault();
			const sanitized = DOMPurify.sanitize(html, { FORBID_TAGS: ['img', 'script', 'style'] });
			if (new DOMParser().parseFromString(sanitized, 'text/html').body.textContent?.trim()) {
				dispatch('paste', event.detail);
				editor?.commands.insertContent(sanitized);
			}
			toast.info(t('粘贴中的图片未导入，请上传原文件保留图文。'));
			return;
		}
		if (clipboard?.getData('text/plain')) dispatch('paste', event.detail);
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="min-w-0"
	on:dragover={(event) => {
		if (event.dataTransfer?.types.includes('Files')) event.preventDefault();
	}}
	on:drop={(event) => {
		const files = Array.from(event.dataTransfer?.files ?? []);
		if (files.length) {
			event.preventDefault();
			event.stopPropagation();
			importFiles(files, 'drop');
		}
	}}
>
	<RichTextInput
		{...$$restProps}
		bind:editor
		bind:value
		json={true}
		link={true}
		showFloatingToolbar={false}
		selectTemplates={false}
		additionalExtensions={extensions}
		onChange={(content) =>
			onChange({ ...content, text: documentText(content.json), md: documentText(content.json) })}
		on:paste={paste}
	/>
</div>
