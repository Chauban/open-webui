<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { config } from '$lib/stores';
	import { extractImportDocument, extractImportImages } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import {
		DOCUMENT_ACCEPT,
		IMAGE_ACCEPT,
		IMAGE_MAX_COUNT,
		checkImageFiles,
		isImageFile,
		shrinkImageForUpload,
		sortImageFiles,
		type ImportInfo
	} from '$lib/utils/text-import';
	import EduButton from './EduButton.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	// 作业写作区的两个导入按钮:Word/文本文件由后端直接解析,照片交给管理员选定的识图模型转录;
	// Word/PDF 由后端统一提取正文和附件，保留原文件与读取状态。
	// 只把识别出的正文交给外层(修订初稿填进初稿框、从零写作进预览),确认与插入由外层负责。

	export let sessionId: string;
	export let disabled = false;
	export let onImported: (text: string, info: ImportInfo) => void;
	// 外层据此锁住输入框和确认按钮。
	export let busy = false;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let documentInput: HTMLInputElement;
	let imageInput: HTMLInputElement;
	let reading: 'document' | 'images' | null = null;

	$: busy = reading !== null;
	// 管理员没选识图模型时不提供图片导入,并说明原因。
	$: imageImportEnabled = $config?.features?.enable_education_draft_image_import === true;

	const run = async (kind: ImportInfo['kind'], files: File[]) => {
		reading = kind;
		try {
			const names = files.map((file) => file.name);
			if (kind === 'images') {
				const result = await extractImportImages(localStorage.token, sessionId, files);
				onImported(result.text, { kind, names, modelId: result.model_id });
			} else {
				const result = await extractImportDocument(localStorage.token, sessionId, files[0]);
				onImported(result.text, { kind, names, material: result.material });
			}
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			reading = null;
		}
	};

	/** 单个文档由后端统一解析；照片仍按上传顺序转录。 */
	export const importFiles = async (files: File[]) => {
		if (files.length === 0 || busy || disabled) return;
		if (files.every(isImageFile)) {
			if (!imageImportEnabled) {
				toast.error(
					t('Image import is not set up. Ask your administrator to choose an image parsing model.')
				);
				return;
			}
			// 先缩再查上限:手机原图超过 10MB 的,缩完多半就够了。
			reading = 'images';
			const shrunk = await Promise.all(sortImageFiles(files).map(shrinkImageForUpload));
			reading = null;
			const error = checkImageFiles(shrunk);
			if (error) {
				toast.error(t(error));
				return;
			}
			await run('images', shrunk);
			return;
		}
		if (files.length > 1) {
			toast.error(t('Import one document at a time. Several files only work for images.'));
			return;
		}
		await run('document', files);
	};

	const onPicked = async (input: HTMLInputElement) => {
		const files = Array.from(input.files ?? []);
		// 清空,同一个文件改完再选一次也能触发 change
		input.value = '';
		await importFiles(files);
	};
</script>

<div class="flex flex-col gap-1.5">
	<div class="flex flex-wrap items-center gap-2">
		<input
			bind:this={documentInput}
			type="file"
			accept={DOCUMENT_ACCEPT}
			class="hidden"
			data-testid="draft-file-input"
			on:change={() => onPicked(documentInput)}
		/>
		<input
			bind:this={imageInput}
			type="file"
			accept={IMAGE_ACCEPT}
			multiple
			class="hidden"
			data-testid="draft-image-input"
			on:change={() => onPicked(imageInput)}
		/>
		<EduButton disabled={disabled || busy} on:click={() => documentInput.click()}>
			{reading === 'document' ? $i18n.t('Reading file...') : $i18n.t('Import from file')}
		</EduButton>
		<EduButton
			disabled={disabled || busy || !imageImportEnabled}
			on:click={() => imageInput.click()}
		>
			{reading === 'images' ? $i18n.t('Reading images...') : $i18n.t('Import from images')}
		</EduButton>
		<Tooltip
			content={$i18n.t(
				'Supports .docx, .doc, .txt, .md and .pdf. Word and PDF images and notes are imported as attached materials. Unreadable items are shown for checking.'
			) +
				'\n\n' +
				$i18n.t(
					imageImportEnabled
						? 'Images: photos or scans of a handwritten or printed draft (JPG, PNG or WebP), up to 8 at a time, read in file-name order. The AI only transcribes, so check the text carefully.'
						: 'Image import is not available: your administrator has not chosen an image parsing model.'
				)}
			allowHTML={false}
			tippyOptions={{ trigger: 'mouseenter focusin click', maxWidth: 340 }}
		>
			<button
				type="button"
				class="rounded-full px-2 py-1 text-xs text-gray-500 underline decoration-dotted underline-offset-4 focus-visible:outline focus-visible:outline-2 dark:text-gray-400"
				data-testid={imageImportEnabled ? 'import-help' : 'image-import-unavailable'}
			>
				{$i18n.t('Import help')}
			</button>
		</Tooltip>
	</div>
	{#if reading === 'document'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('Reading document text, images and notes. Please wait.')}
		</p>
	{:else if reading === 'images'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('The AI is transcribing your images. Please wait a moment.')}
		</p>
	{/if}
</div>
