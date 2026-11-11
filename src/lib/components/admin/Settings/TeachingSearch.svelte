<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { teachingApi } from '$lib/apis/education/teaching';
	const i18n = getContext('i18n');
	let policy: { enabled: boolean; connection_index: number | null } = {
		enabled: false,
		connection_index: null
	};
	let connections: { index: number; name: string; has_key: boolean }[] = [];
	let loading = true;
	let busy = false;
	let error = '';
	let status = '';
	const explain = (e: unknown) =>
		String((e as { detail?: string; message?: string }).detail ?? (e as Error).message ?? e);
	onMount(async () => {
		try {
			const result = await teachingApi<{ policy: typeof policy; connections: typeof connections }>(
				'/admin/teaching-search'
			);
			policy = result.policy;
			connections = result.connections;
			loading = false;
		} catch (e) {
			error = explain(e);
		}
	});
	async function save() {
		busy = true;
		error = '';
		status = '';
		try {
			policy = await teachingApi('/admin/teaching-search', 'PUT', policy);
			status = '已保存';
		} catch (e) {
			error = explain(e);
		} finally {
			busy = false;
		}
	}
</script>

<section class="my-4 space-y-3 rounded-xl border p-4 dark:border-gray-700">
	<h2 class="font-semibold">{$i18n.t('段落论证资料搜索')}</h2>
	<p class="text-sm text-gray-500">
		{$i18n.t('使用连接设置中的 DeepSeek 官方密钥。教师再按作业开启；默认关闭，不修改辅导提示词。')}
	</p>
	<p class="text-sm text-gray-500">
		{$i18n.t(
			'关闭服务后不再搜索，历史对话中的资料仍保留。教师修改作业搜索设置后需保存并发布，试教设置修改后需重新测试。'
		)}
	</p>
	<label class="flex items-center gap-2"
		><input type="checkbox" bind:checked={policy.enabled} disabled={loading || busy} />{$i18n.t(
			'允许教师开启资料搜索'
		)}</label
	>
	<label class="block"
		>{$i18n.t('搜索服务连接')}
		<select
			class="ml-2 max-w-full rounded-lg border p-2 dark:bg-gray-800"
			bind:value={policy.connection_index}
			disabled={loading || busy}
		>
			<option value={null}>{$i18n.t('请选择连接')}</option>
			{#each connections as connection}<option
					value={connection.index}
					disabled={!connection.has_key}
					>{connection.name}{!connection.has_key ? ` · ${$i18n.t('未配置密钥')}` : ''}</option
				>{/each}
		</select>
	</label>
	{#if !loading && !connections.length}<p class="text-sm">
			{$i18n.t('请先在连接设置中添加 DeepSeek 官方连接和 API Key。')}
		</p>{/if}
	<p class="text-sm text-gray-500">
		{$i18n.t(
			'每轮最多搜索 2 次、读取 3 个网页，按实际调用计费。资料来源及检索结果随教学调用保存。'
		)}
	</p>
	<button
		type="button"
		class="rounded-lg border px-3 py-2"
		disabled={loading || busy}
		on:click={save}>{$i18n.t('保存资料搜索设置')}</button
	>
	<p role="status">{$i18n.t(status)}</p>
	{#if error}<p role="alert">{error}</p>{/if}
</section>
