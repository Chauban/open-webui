<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { extractDraftBaselineFile, submitDraftBaseline } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import EduButton from './EduButton.svelte';
	import { EDU_FIELD_CLASS } from './styles';

	// 修订初稿作业的第一步:学生把课外写好的初稿交进来,冻结为修改的起点。
	// 显式步骤本身就是「先交初稿」的关卡,也让学生清楚哪一份是初稿;
	// 不做「空文档里第一次大段粘贴自动认定为初稿」,那样会把第二次粘贴误判成初稿。
	// 初稿多半是 Word 文件,可以上传或拖进来:后端解析成纯文本填回框里,学生核对后再确认。

	export let sessionId: string;
	export let onSubmitted: () => Promise<void> | void;

	// 与后端 DRAFT_BASELINE_MIN_CHARS 一致,按去掉空白后的字数算。
	const MIN_CHARS = 200;
	const ACCEPTED_FILES = '.docx,.doc,.txt,.md';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let text = '';
	let submitting = false;
	let importing = false;
	let dragging = false;
	let fileInput: HTMLInputElement;

	$: charCount = text.replace(/\s/g, '').length;
	$: tooShort = charCount < MIN_CHARS;
	$: busy = submitting || importing;

	const importFile = async (file: File | undefined) => {
		if (!file || busy) return;
		importing = true;
		try {
			const result = await extractDraftBaselineFile(localStorage.token, sessionId, file);
			text = result.text;
			toast.success(t('Read from {{name}}. Check the text before confirming.', { name: file.name }));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			importing = false;
		}
	};

	const onFileChange = async () => {
		const file = fileInput.files?.[0];
		// 清空,同一个文件改完再选一次也能触发 change
		fileInput.value = '';
		await importFile(file);
	};

	const onDrop = async (event: DragEvent) => {
		dragging = false;
		await importFile(event.dataTransfer?.files?.[0]);
	};

	const confirm = async () => {
		if (tooShort || busy) return;
		submitting = true;
		try {
			await submitDraftBaseline(localStorage.token, sessionId, text);
			await onSubmitted();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			submitting = false;
		}
	};
</script>

<!-- 撑满外层滚动区的高度:正文框吃掉剩余空间,确认按钮落在底部;外层太矮时退回滚动 -->
<section class="flex min-h-0 flex-1 flex-col gap-3">
	<div>
		<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
			{$i18n.t('Step 1: Submit your first draft')}
		</h3>
		<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
			{$i18n.t(
				'Paste the first draft you wrote outside class here, or import it from a Word file. Once confirmed it is saved as the starting point of your revision and cannot be changed.'
			)}
		</p>
		<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('The editor and the AI chat unlock after you confirm.')}
		</p>
	</div>
	<div class="flex flex-wrap items-center gap-2">
		<input
			bind:this={fileInput}
			type="file"
			accept={ACCEPTED_FILES}
			class="hidden"
			data-testid="draft-file-input"
			on:change={onFileChange}
		/>
		<EduButton disabled={busy} on:click={() => fileInput.click()}>
			{importing ? $i18n.t('Reading file...') : $i18n.t('Import from file')}
		</EduButton>
		<span class="text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('Supports .docx, .doc, .txt and .md. For PDF, copy the text in or save it as .docx.')}
		</span>
	</div>
	<textarea
		bind:value={text}
		class="min-h-64 w-full flex-1 resize-none {EDU_FIELD_CLASS} {dragging
			? 'ring-2 ring-sky-400 dark:ring-sky-500'
			: ''}"
		placeholder={$i18n.t('Paste your first draft here, or drop a file in')}
		disabled={busy}
		on:dragover|preventDefault={() => (dragging = true)}
		on:dragleave={() => (dragging = false)}
		on:drop|preventDefault={onDrop}
	></textarea>
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div class="text-xs tabular-nums {tooShort ? 'text-gray-500 dark:text-gray-400' : 'text-emerald-600 dark:text-emerald-400'}">
			{$i18n.t('{{count}} / {{min}} characters at least', { count: charCount, min: MIN_CHARS })}
		</div>
		<EduButton variant="primary" disabled={tooShort || busy} on:click={confirm}>
			{submitting ? $i18n.t('Saving...') : $i18n.t('Confirm this is my first draft')}
		</EduButton>
	</div>
</section>
