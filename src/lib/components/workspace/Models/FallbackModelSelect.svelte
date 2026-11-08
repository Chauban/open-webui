<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	const i18n = getContext<Writable<I18nType>>('i18n');
	export let value = '';
	export let primaryId = '';
	export let options: { id: string; name: string; provider: string; connection: number }[] = [];
	export let unavailable = false;
	$: primary = options.find((option) => option.id === primaryId);
	$: candidates = options.filter(
		(option) => option.id !== primaryId && (!primary || option.connection !== primary.connection)
	);
	$: providers = [...new Set(candidates.map((option) => option.provider))].sort();
</script>

<div class="my-4">
	<label for="fallback-model" class="mb-2 block text-sm font-medium">
		{$i18n.t('备用模型（可选）')}
	</label>
	<select
		id="fallback-model"
		bind:value
		class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700"
	>
		<option value="">{$i18n.t('无，不使用备用模型')}</option>
		{#if value && !candidates.some((option) => option.id === value)}
			<option {value} disabled>{value} · {$i18n.t('当前不可用')}</option>
		{/if}
		{#each providers as provider}
			<optgroup label={provider}>
				{#each candidates.filter((option) => option.provider === provider) as option}
					<option value={option.id}>{option.name} · {provider} — {option.id}</option>
				{/each}
			</optgroup>
		{/each}
	</select>
	<p class="mt-2 text-xs text-gray-500">
		{$i18n.t('当前模型响应超时时，自动使用备用模型重试。地址和密钥沿用已有连接。')}
	</p>
	{#if value}
		<p class="mt-1 text-xs text-gray-500">
			{$i18n.t('已发布的教学作业需重新发布辅导配置后使用新的备用设置。')}
		</p>
	{/if}
	{#if unavailable}
		<p role="alert" class="mt-1 text-xs text-amber-700">
			{$i18n.t('备用模型列表加载失败，请重新打开编辑页。')}
		</p>
	{/if}
</div>
