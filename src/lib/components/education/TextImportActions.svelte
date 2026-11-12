<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onDestroy } from 'svelte';
	import { get } from 'svelte/store';

	import { config } from '$lib/stores';
	import {
		extractImportDocument,
		extractImportImages,
		type ImageUploadPurpose
	} from '$lib/apis/education';
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
	export let photoTranscriptionEnabled = false;
	export let baselineHelp = false;
	export let onImported: (text: string, info: ImportInfo) => Promise<void> | void;
	// 外层据此锁住输入框和确认按钮。
	export let busy = false;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let uploadInput: HTMLInputElement;
	let reading: 'document' | 'images' | null = null;
	let importError = '';
	let pendingImages: File[] = [];
	let finishChoice: (() => void) | null = null;
	let imagePurpose: ImageUploadPurpose | null = null;
	onDestroy(() => finishChoice?.());

	$: busy = reading !== null || pendingImages.length > 0;
	// 模型可用性影响帮助说明，不隐藏图片上传。
	$: imageImportEnabled =
		imageReadingEnabled && $config?.features?.enable_education_draft_image_import === true;
	$: photoImportEnabled =
		photoTranscriptionEnabled && $config?.features?.enable_education_photo_transcription === true;
	$: photoDisabledReason = !photoTranscriptionEnabled
		? t('本作业未开启照片转正文，请联系老师；仍可插入图片。')
		: t('平台未配置照片转正文模型，请联系管理员；仍可插入图片。');
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

	const run = async (kind: ImportInfo['kind'], files: File[], purpose?: ImageUploadPurpose) => {
		reading = kind;
		imagePurpose = purpose ?? null;
		try {
			const names = files.map((file) => file.name);
			if (kind === 'images') {
				const images = files;
				const error = checkImageFiles(images);
				if (error) throw error;
				const result = await extractImportImages(localStorage.token, sessionId, images, purpose!);
				await onImported(result.text, {
					kind,
					purpose,
					names,
					document: result.content_json,
					materials: result.materials
				});
			} else {
				const result = await extractImportDocument(localStorage.token, sessionId, files[0]);
				await onImported(result.text, {
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
			imagePurpose = null;
		}
	};

	function cancelChoice() {
		pendingImages = [];
		finishChoice?.();
		finishChoice = null;
	}
	async function choose(purpose: ImageUploadPurpose) {
		if (reading || (purpose === 'photo_to_text' && !photoImportEnabled)) return;
		importError = '';
		await run('images', pendingImages, purpose);
		// Keep the selected files and order available for a retry after a failed request.
		if (!importError) cancelChoice();
	}
	function move(index: number, direction: number) {
		const files = [...pendingImages];
		[files[index], files[index + direction]] = [files[index + direction], files[index]];
		pendingImages = files;
	}

	/** 单个文档由后端统一解析；照片仍按上传顺序转录。 */
	export const importFiles = async (files: File[]) => {
		if (files.length === 0 || busy || disabled) return;
		importError = '';
		if (files.every(isImageFile)) {
			if (files.length > IMAGE_MAX_COUNT) {
				importError = t('Upload at most 8 images at a time');
				return;
			}
			const error = checkImageFiles(files);
			if (error) {
				importError = resolveErrorMessage(error, t);
				return;
			}
			pendingImages = sortImageFiles(files);
			await new Promise<void>((resolve) => {
				finishChoice = resolve;
			});
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
	{#if pendingImages.length}
		<div
			class="max-w-full space-y-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700"
			aria-label={$i18n.t('选择图片用途')}
		>
			<p class="text-sm font-medium">{$i18n.t('这些图片用于什么？')}</p>
			<ol class="space-y-1 text-xs text-gray-600 dark:text-gray-300">
				{#each pendingImages as file, index}
					<li class="flex items-center gap-2">
						<span class="min-w-0 flex-1 break-all">{index + 1}. {file.name}</span>
						{#if pendingImages.length > 1}
							<button
								type="button"
								class="shrink-0 rounded px-2 py-1 disabled:opacity-30"
								disabled={!!reading || index === 0}
								aria-label={$i18n.t('上移 {{name}}', { name: file.name })}
								on:click={() => move(index, -1)}>↑</button
							>
							<button
								type="button"
								class="shrink-0 rounded px-2 py-1 disabled:opacity-30"
								disabled={!!reading || index === pendingImages.length - 1}
								aria-label={$i18n.t('下移 {{name}}', { name: file.name })}
								on:click={() => move(index, 1)}>↓</button
							>
						{/if}
					</li>
				{/each}
			</ol>
			<div class="flex flex-wrap gap-2">
				<EduButton
					variant="primary"
					disabled={!!reading || !photoImportEnabled}
					on:click={() => choose('photo_to_text')}>{$i18n.t('照片转正文')}</EduButton
				>
				<EduButton disabled={!!reading} on:click={() => choose('reference')}
					>{$i18n.t('插入图片')}</EduButton
				>
				<EduButton disabled={!!reading} on:click={cancelChoice}>{$i18n.t('Cancel')}</EduButton>
			</div>
			<p class="text-xs leading-relaxed text-gray-500">
				{$i18n.t(
					'照片转正文：识别手写或打印稿，文字直接进入编辑框。插入图片：保留参考图，不自动识别。'
				)}
			</p>
			{#if !photoImportEnabled}<p role="status" class="text-xs text-amber-700 dark:text-amber-300">
					{photoDisabledReason}
				</p>{/if}
		</div>
	{/if}
	{#if importError}<p role="alert" class="text-xs text-rose-600 dark:text-rose-400">
			{importError}
		</p>{/if}
	{#if reading === 'document'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t('Reading the file. Please wait.')}
		</p>
	{:else if reading === 'images'}
		<p class="text-xs text-sky-600 dark:text-sky-400" role="status">
			{$i18n.t(
				imagePurpose === 'photo_to_text' ? '正在将照片转为正文，请稍候。' : '正在保存图片，请稍候。'
			)}
		</p>
	{/if}
</div>
