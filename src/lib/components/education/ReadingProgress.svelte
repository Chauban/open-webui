<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	const i18n = getContext<Writable<I18nType>>('i18n');
</script>

<div
	role="status"
	class="my-3 flex items-center gap-3 rounded-xl bg-sky-50 p-3 text-sky-800 dark:bg-sky-950/40 dark:text-sky-200"
>
	<span
		aria-hidden="true"
		class="size-5 shrink-0 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600 motion-reduce:animate-none dark:border-sky-900 dark:border-t-sky-300"
	></span>
	<p class="text-xs leading-relaxed">
		{$i18n.t('AI 正在阅读，暂时无法编辑或提交，完成后自动恢复。')}
	</p>
</div>
