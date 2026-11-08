<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { models } from '$lib/stores';
	import { teachingApi } from '$lib/apis/education/teaching';
	const i18n = getContext('i18n');
	type TeachingModelOption = {
		id: string;
		name: string;
		owned_by: string;
		pipe?: unknown;
		pipeline?: unknown;
		info?: {
			is_active?: boolean;
			access_grants?: { principal_type: string; principal_id: string; permission: string }[];
		};
	};
	let selected: string[] = [];
	let recommended = '';
	let error = '';
	let status = '';
	let busy = false;
	$: publicModels = ($models as TeachingModelOption[]).filter(
		(model) =>
			model.owned_by !== 'arena' &&
			!model.pipe &&
			!model.pipeline &&
			model.info?.is_active !== false &&
			(model.info?.access_grants ?? []).some(
				(grant) =>
					grant.principal_type === 'user' &&
					grant.principal_id === '*' &&
					grant.permission === 'read'
			)
	);
	$: selectedPublicModels = publicModels.filter((model) => selected.includes(model.id));
	$: visibleRecommended = selectedPublicModels.some((model) => model.id === recommended)
		? recommended
		: '';
	onMount(async () => {
		try {
			const result = await teachingApi<{
				policy: { model_ids: string[]; recommended_model_id: string | null };
			}>('/teacher/teaching-models');
			selected = result.policy.model_ids;
			recommended = result.policy.recommended_model_id ?? '';
		} catch (e) {
			error = String(e.detail ?? e.message ?? e);
		}
	});
	async function save() {
		busy = true;
		error = '';
		try {
			await teachingApi('/admin/teaching-models', 'PUT', {
				model_ids: selectedPublicModels.map((model) => model.id),
				recommended_model_id: visibleRecommended || null
			});
			status = '已保存';
		} catch (e) {
			error = String(e.detail ?? e.message ?? e);
		} finally {
			busy = false;
		}
	}
</script>

<section class="my-4 space-y-3 rounded-xl border p-4 dark:border-gray-700">
	<h2 class="font-semibold">{$i18n.t('段落论证教学模型')}</h2>
	<p class="text-sm">
		{$i18n.t(
			'教师从此清单选定作业模型，统一用于初读、交流和复看；无需向学生开放普通聊天权限。撤销授权会立即阻止后续调用。'
		)}
	</p>
	<p class="text-sm text-gray-500">
		{$i18n.t('Only public models from Model Settings are listed here.')}
	</p>
	{#each publicModels as model}<label class="flex gap-2"
			><input type="checkbox" bind:group={selected} value={model.id} />{model.name}</label
		>{:else}<p class="text-sm text-gray-500">
			{$i18n.t('No public models available. Make a model public in Model Settings first.')}
		</p>{/each}
	<label
		>{$i18n.t('推荐模型')}<select
			class="mx-2 rounded-lg dark:bg-gray-800"
			value={visibleRecommended}
			on:change={(event) => {
				recommended = event.currentTarget.value;
			}}
			><option value="">{$i18n.t('不指定')}</option>{#each selectedPublicModels as model}<option
					value={model.id}>{model.name}</option
				>{/each}</select
		></label
	><button class="rounded-lg border px-3 py-2" disabled={busy} on:click={save}
		>{$i18n.t('保存教学模型')}</button
	>
	<p role="status">{$i18n.t(status)}</p>
	{#if error}<p role="alert">{error}</p>{/if}
</section>
