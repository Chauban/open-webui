<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';

	import { config } from '$lib/stores';
	import { extractImportDocument, extractImportImages } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import {
		DOCUMENT_ACCEPT,
		IMAGE_ACCEPT,
		IMAGE_MAX_COUNT,
		checkImageFiles,
		isImageFile,
		sortImageFiles,
		type ImportInfo
	} from '$lib/utils/text-import';
	import EduButton from './EduButton.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte';

	// 所有图文始终可以上传；开关只控制识读。外层核对同一份结构化稿件。

	export let sessionId: string;
	export let disabled = false;
	export let imageReadingEnabled = false;
	export let baselineHelp = false;
	export let onImported: (text: string, info: ImportInfo) => void;
	// 外层据此锁住输入框和确认按钮。
	export let busy = false;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let uploadInput: HTMLInputElement;
	let reading: 'document' | 'images' | null = null;
	let importError = '';

	$: busy = reading !== null;
	// 模型可用性影响帮助说明，不隐藏图片上传。
	$: imageImportEnabled =
		imageReadingEnabled && $config?.features?.enable_education_draft_image_import === true;
	$: acceptedFiles = `${DOCUMENT_ACCEPT},${IMAGE_ACCEPT}`;
	$: helpText = [
		t(
			'Documents: one Word, PDF, TXT or Markdown file at a time. Word/PDF: up to 50 MB; PDF: up to 50 pages. Plain text and legacy DOC: up to 10 MB.'
		),
		t(
			'Images: up to 8 JPG, PNG or WebP files, read in file-name order. Upload size: 10 MB each, 30 MB total. Do not mix images and documents.'
		),
		...(!imageImportEnabled ? [t('AI 本次只读取文字，图片仍会随作业保存。')] : []),
		...(baselineHelp
			? [
					t(
						'The confirmed draft is saved as the starting point of your revision. Before final submission, you can withdraw it from the top-right "…" menu and import it again.'
					)
				]
			: [])
	].join('\n\n');

	const run = async (kind: ImportInfo['kind'], files: File[]) => {
		reading = kind;
		try {
			const names = files.map((file) => file.name);
			if (kind === 'images') {
				const images = files;
				const error = checkImageFiles(images);
				if (error) throw error;
				const result = await extractImportImages(localStorage.token, sessionId, images);
				onImported(result.text, {
					kind,
					names,
					document: result.content_json,
					materials: result.materials
				});
			} else {
				const result = await extractImportDocument(localStorage.token, sessionId, files[0]);
				onImported(result.text, {
					kind,
					names,
					document: result.content_json,
					materials: [result.material]
				});
			}
		} catch (error) {
			importError = resolveErrorMessage(error, t);
		} finally {
			reading = null;
		}
	};

	/** 单个文档由后端统一解析；照片仍按上传顺序转录。 */
	export const importFiles = async (files: File[]) => {
		if (files.length === 0 || busy || disabled) return;
		importError = '';
		if (files.every(isImageFile)) {
			if (files.length > IMAGE_MAX_COUNT) {
				importError = t('Upload at most 8 images at a time');
				return;
			}
			await run('images', sortImageFiles(files));
			return;
		}
		if (files.length > 1) {
			importError = t('Choose one document or up to 8 images; do not mix them.');
			return;
		}
		await run('document', files);
	};

	const onPicked = async () => {
		const files = Array.from(uploadInput.files ?? []);
		// 清空,同一个文件改完再选一次也能触发 change
		uploadInput.value = '';
		await importFiles(files);
	};
</script>

<div class="flex flex-col gap-1.5">
	<div class="flex flex-wrap items-center gap-2">
		<input
			bind:this={uploadInput}
			type="file"
			accept={acceptedFiles}
			multiple
			class="hidden"
			data-testid="draft-upload-input"
			on:change={onPicked}
		/>
		<EduButton
			class="inline-flex items-center gap-2"
			disabled={disabled || busy}
			on:click={() => uploadInput.click()}
		>
			<ArrowUpTray />
			{reading ? $i18n.t('Reading...') : $i18n.t('Upload')}
		</EduButton>
		<Tooltip
			content={helpText}
			allowHTML={false}
			tippyOptions={{ trigger: 'mouseenter focusin click', maxWidth: 340 }}
		>
			<button
				type="button"
				class="rounded-full px-2 py-1 text-xs text-gray-500 underline decoration-dotted underline-offset-4 focus-visible:outline focus-visible:outline-2 dark:text-gray-400"
				data-testid="import-help"
			>
				{$i18n.t('Supported formats')}
			</button>
		</Tooltip>
	</div>
	{#if importError}<p role="alert" class="text-xs text-rose-600 dark:text-rose-400">
			{importError}
		</p>{/if}
	{#if reading === 'document'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('Reading the file. Please wait.')}
		</p>
	{:else if reading === 'images'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('正在保存图片，请稍候。')}
		</p>
	{/if}
</div>
