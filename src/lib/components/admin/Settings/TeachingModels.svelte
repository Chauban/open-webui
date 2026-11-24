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
	type PublishedAssignment = {
		id: string;
		title: string;
		classroom: string | null;
		model_id: string;
	};
	type Settings = {
		policy: { model_ids: string[]; recommended_model_id: string | null };
		assignments: PublishedAssignment[];
		snapshot: string;
	};
	let snapshot = '';
	let assignments: PublishedAssignment[] = [];
	let replacements: Record<string, string> = {};
	let needsReload = false;
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
	$: sources = [...new Set(assignments.map((item) => item.model_id))];
	$: selectedIds = selectedPublicModels.map((model) => model.id);
	$: incomplete = sources.some((source) =>
		replacements[source]
			? !selectedIds.includes(replacements[source]) || !!replacements[replacements[source]]
			: !selectedIds.includes(source)
	);
	function accept(result: Settings) {
		selected = result.policy.model_ids;
		recommended = result.policy.recommended_model_id ?? '';
		assignments = result.assignments;
		snapshot = result.snapshot;
		replacements = {};
		needsReload = false;
	}
	async function load() {
		busy = true;
		error = '';
		try {
			accept(await teachingApi<Settings>('/admin/teaching-models'));
		} catch (e) {
			error = String(e.detail ?? e.message ?? e);
			needsReload = true;
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		void load();
	});
	async function save() {
		busy = true;
		error = '';
		try {
			accept(
				await teachingApi<Settings>('/admin/teaching-models', 'PUT', {
					model_ids: selectedIds,
					recommended_model_id: visibleRecommended || null,
					expected_snapshot: snapshot,
					replacements: Object.fromEntries(
						Object.entries(replacements).filter(([, target]) => target)
					)
				})
			);
			status = '已保存';
		} catch (e) {
			needsReload = e.status === 409;
			error = $i18n.t(String(e.detail ?? e.message ?? e));
		} finally {
			busy = false;
		}
	}
</script>

<section class="my-4 space-y-3 rounded-xl border p-4 dark:border-gray-700">
	<h2 class="font-semibold">{$i18n.t('段落论证教学模型')}</h2>
	<p class="text-sm">
		{$i18n.t(
			'取消在用模型的授权前，请为下列作业选择替代模型。保存后，学生的下一次初读或交流使用新模型。'
		)}
	</p>
	<p class="text-sm text-gray-500">
		{$i18n.t('Only public models from Model Settings are listed here.')}
	</p>
	<p class="text-sm text-gray-500">
		{$i18n.t(
			'The recommended model is preselected when preparing an assignment. Published assignments use their saved coaching model. Image-to-text uses the separate platform setting.'
		)}
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
	>
	{#each sources as source}
		<details class="my-3 rounded-lg border p-3" open={!selectedIds.includes(source)}>
			<summary
				>{source} · {$i18n.t('已布置作业')} ({assignments.filter((item) => item.model_id === source)
					.length})</summary
			>
			<ul class="my-2 text-sm">
				{#each assignments.filter((item) => item.model_id === source) as item}
					<li>{item.classroom ?? ''} · {item.title}</li>
				{/each}
			</ul>
			<label
				>{$i18n.t('替换这些作业的模型')}
				<select bind:value={replacements[source]} class="mx-2 rounded border">
					<option value=""
						>{selectedIds.includes(source)
							? $i18n.t('保留当前模型')
							: $i18n.t('请选择替代模型')}</option
					>
					{#each selectedPublicModels.filter((model) => model.id !== source) as model}
						<option value={model.id}>{model.name} ({model.id})</option>
					{/each}
				</select>
			</label>
		</details>
	{/each}
	{#if needsReload}<button type="button" on:click={load}>{$i18n.t('重新加载')}</button>{/if}
	<button
		class="rounded-lg border px-3 py-2"
		disabled={busy || !snapshot || needsReload || incomplete}
		on:click={save}>{$i18n.t('保存教学模型')}</button
	>
	<p role="status">{$i18n.t(status)}</p>
	{#if error}<p role="alert">{error}</p>{/if}
</section>
