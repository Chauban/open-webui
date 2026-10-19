<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 服务商注意事项的一块:连接设置、模型编辑页、AI 步骤设置共用。文字由 utils/provider-quirks.ts 生成。
	export let notes: string[] = [];
	export let testid = 'provider-quirks';
	export let compact = false;
</script>

{#if notes.length > 0}
	<div
		class="{compact
			? 'mt-0.5'
			: 'mt-2 rounded-lg border border-amber-200/60 px-3 py-2 dark:border-amber-500/20'} text-[0.6875rem] text-amber-700 dark:text-amber-400"
		data-testid={testid}
	>
		{#if !compact}
			<div class="mb-0.5 font-medium">{$i18n.t('Provider quirks')}</div>
		{/if}
		<ul class="list-disc space-y-0.5 pl-4">
			{#each notes as note}
				<li>{note}</li>
			{/each}
		</ul>
	</div>
{/if}
