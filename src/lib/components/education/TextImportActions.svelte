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
		isPdfFile,
		shrinkImageForUpload,
		sortImageFiles,
		type ImportInfo
	} from '$lib/utils/text-import';
	import { buildPdfText, type PdfPage } from '$lib/utils/pdf-text';
	import EduButton from './EduButton.svelte';

	// 作业写作区的两个导入按钮:Word/文本文件由后端直接解析,照片交给管理员选定的识图模型转录;
	// PDF 在浏览器里读,扫描页渲染成图后走同一条识图路径。
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
	let reading: 'document' | 'images' | 'pdf' | null = null;
	let pdfProgress: { page: number; total: number } | null = null;

	$: busy = reading !== null;
	// 管理员没选识图模型时不提供图片导入,并说明原因。
	$: imageImportEnabled = $config?.features?.enable_education_draft_image_import === true;

	const run = async (kind: ImportInfo['kind'], files: File[]) => {
		reading = kind;
		try {
			const result =
				kind === 'images'
					? await extractImportImages(localStorage.token, sessionId, files)
					: await extractImportDocument(localStorage.token, sessionId, files[0]);
			onImported(result.text, { kind, names: files.map((file) => file.name) });
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			reading = null;
		}
	};

	/**
	 * PDF:浏览器里逐页取文字层;扫描页(几乎没字、画了图)渲染成图,一次交给识图模型,
	 * 结果按页插回原位,再整体还原段落、去掉页眉页脚和页码。
	 */
	const importPdf = async (file: File) => {
		reading = 'pdf';
		pdfProgress = null;
		try {
			// 按需加载:pdf.js 和这段代码都不进工作区首屏包。
			const { readPdf, PdfImportError } = await import('$lib/utils/pdf-import');
			let pages;
			try {
				pages = await readPdf(file, {
					renderScans: imageImportEnabled,
					onProgress: (page, total) => (pdfProgress = { page, total })
				});
			} catch (error) {
				toast.error(t(error instanceof PdfImportError ? error.message : 'Could not read this PDF'));
				return;
			}
			const scans = pages.filter((page) => page.kind === 'scan');
			const hasText = pages.some((page) => page.kind === 'text' && page.lines.length > 0);
			let transcribed: string[] = [];
			if (scans.length > 0 && !imageImportEnabled) {
				if (!hasText) {
					toast.error(
						t(
							'This PDF is a scan, and image import is not set up. Ask your administrator to choose an image parsing model.'
						)
					);
					return;
				}
				toast.warning(
					t('Skipped {{count}} scanned page(s): image import is not set up.', {
						count: scans.length
					})
				);
			} else if (scans.length > 0) {
				if (scans.length > IMAGE_MAX_COUNT) {
					toast.error(
						t('This PDF has more than 8 scanned pages. Import at most 8 scanned pages at a time.')
					);
					return;
				}
				const images = scans.map((page) => (page.kind === 'scan' ? page.image : null));
				if (images.some((image) => !image)) {
					toast.error(t('Could not read this PDF'));
					return;
				}
				const error = checkImageFiles(images as File[]);
				if (error) {
					toast.error(t(error));
					return;
				}
				reading = 'images';
				transcribed = (await extractImportImages(localStorage.token, sessionId, images as File[]))
					.pages;
			}
			let scanIndex = 0;
			const built: PdfPage[] = [];
			for (const page of pages) {
				if (page.kind === 'text') built.push({ kind: 'text', lines: page.lines });
				else if (page.kind === 'scan' && imageImportEnabled) {
					built.push({ kind: 'ocr', text: transcribed[scanIndex] ?? '' });
					scanIndex += 1;
				}
			}
			const text = buildPdfText(built);
			if (!text.trim()) {
				toast.error(t('No text found in this PDF'));
				return;
			}
			const usedImages = scans.length > 0 && imageImportEnabled;
			onImported(text, {
				kind: usedImages ? 'images' : 'document',
				names: [file.name],
				...(usedImages ? { scannedPages: scans.length } : {})
			});
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			reading = null;
			pdfProgress = null;
		}
	};

	/** 选择或拖进来的文件:一个 PDF 在浏览器里读;全是图片走识图;否则只收一个文档。 */
	export const importFiles = async (files: File[]) => {
		if (files.length === 0 || busy || disabled) return;
		if (files.length === 1 && isPdfFile(files[0])) {
			await importPdf(files[0]);
			return;
		}
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
			{reading === 'document' || reading === 'pdf'
				? $i18n.t('Reading file...')
				: $i18n.t('Import from file')}
		</EduButton>
		<EduButton
			disabled={disabled || busy || !imageImportEnabled}
			on:click={() => imageInput.click()}
		>
			{reading === 'images' ? $i18n.t('Reading images...') : $i18n.t('Import from images')}
		</EduButton>
	</div>
	<p class="text-xs text-gray-500 dark:text-gray-400">
		{$i18n.t(
			'Supports .docx, .doc, .txt, .md and .pdf. A PDF is read in your browser; scanned pages go through image import.'
		)}
	</p>
	{#if reading === 'pdf' && pdfProgress}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('Reading the PDF: page {{page}} of {{total}}', pdfProgress)}
		</p>
	{:else if reading === 'images'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('The AI is transcribing your images. This can take up to a minute.')}
		</p>
	{:else if imageImportEnabled}
		<p class="text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t(
				'Images: photos or scans of a handwritten or printed draft (JPG, PNG or WebP), up to 8 at a time, read in file-name order. The AI only transcribes, so check the text carefully.'
			)}
		</p>
	{:else}
		<p class="text-xs text-gray-500 dark:text-gray-400" data-testid="image-import-unavailable">
			{$i18n.t(
				'Image import is not available: your administrator has not chosen an image parsing model.'
			)}
		</p>
	{/if}
</div>
