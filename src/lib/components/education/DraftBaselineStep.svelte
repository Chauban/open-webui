<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { submitDraftBaseline } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import EduButton from './EduButton.svelte';
	import { EDU_FIELD_CLASS } from './styles';

	// 修订初稿作业的第一步:学生把课外写好的初稿交进来,冻结为修改的起点。
	// 显式步骤本身就是「先交初稿」的关卡,也让学生清楚哪一份是初稿;
	// 不做「空文档里第一次大段粘贴自动认定为初稿」,那样会把第二次粘贴误判成初稿。

	export let sessionId: string;
	export let onSubmitted: () => Promise<void> | void;

	// 与后端 DRAFT_BASELINE_MIN_CHARS 一致,按去掉空白后的字数算。
	const MIN_CHARS = 200;

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let text = '';
	let submitting = false;

	$: charCount = text.replace(/\s/g, '').length;
	$: tooShort = charCount < MIN_CHARS;

	const confirm = async () => {
		if (tooShort || submitting) return;
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

<section class="grid gap-3">
	<div>
		<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
			{$i18n.t('Step 1: Submit your first draft')}
		</h3>
		<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
			{$i18n.t(
				'Paste the first draft you wrote outside class here. Once confirmed it is saved as the starting point of your revision and cannot be changed.'
			)}
		</p>
		<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('The editor and the AI chat unlock after you confirm.')}
		</p>
	</div>
	<textarea
		bind:value={text}
		class="min-h-[50vh] w-full {EDU_FIELD_CLASS}"
		placeholder={$i18n.t('Paste your first draft here')}
		disabled={submitting}
	></textarea>
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div class="text-xs tabular-nums {tooShort ? 'text-gray-500 dark:text-gray-400' : 'text-emerald-600 dark:text-emerald-400'}">
			{$i18n.t('{{count}} / {{min}} characters at least', { count: charCount, min: MIN_CHARS })}
		</div>
		<EduButton variant="primary" disabled={tooShort || submitting} on:click={confirm}>
			{submitting ? $i18n.t('Saving...') : $i18n.t('Confirm this is my first draft')}
		</EduButton>
	</div>
</section>
