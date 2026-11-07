<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import type { TeacherModelUsage } from '$lib/utils/teacher-writing-process';
	import { AI_STEP_TEXT } from '$lib/utils/ai-steps';
	const i18n = getContext<Writable<I18nType>>('i18n');
	export let usage: TeacherModelUsage[] = [];
	$: modelIds = [...new Set(usage.flatMap((item) => item.models))];
</script>

<section
	class="rounded-2xl bg-gray-50 px-4 py-3 dark:bg-gray-800"
	aria-label={$i18n.t('AI models used this round')}
	data-testid="round-step-models"
>
	<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
		{$i18n.t('AI models used this round')}:
		<span class="break-words font-normal">
			{modelIds.length
				? modelIds.map((id) => id ?? $i18n.t('Model not recorded')).join(' / ')
				: $i18n.t('No AI model usage recorded')}
		</span>
	</div>
	{#if usage.length}
		<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
			{#each usage as item}
				<span class="min-w-0 break-words">
					{$i18n.t(AI_STEP_TEXT[item.step].title)}:
					{item.models.map((id) => id ?? $i18n.t('Model not recorded')).join(' / ')}
				</span>
			{/each}
		</div>
	{/if}
</section>
