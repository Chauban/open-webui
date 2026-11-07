<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		getTeachingConfigs,
		saveTeachingConfig,
		type TaskMode,
		type TeachingConfig
	} from '$lib/apis/education';
	import { TASK_TYPES } from '$lib/utils/task-types';
	import { resolveErrorMessage } from '$lib/utils/education';
	import {
		getReflectionQuestionsError,
		normalizeReflectionQuestions
	} from '$lib/utils/reflection-questions';
	import ReflectionQuestionsEditor from '$lib/components/education/ReflectionQuestionsEditor.svelte';
	const i18n = getContext('i18n');
	let configs: Partial<Record<TaskMode, TeachingConfig>> = {};
	let selected: TaskMode = 'from_scratch';
	let draft: TeachingConfig | null = null;
	let busy = false;
	let error = '';
	const select = (mode: TaskMode) => {
		selected = mode;
		draft = structuredClone(configs[mode]!);
	};
	onMount(async () => {
		try {
			configs = await getTeachingConfigs(localStorage.token);
			select(selected);
		} catch (e) {
			error = resolveErrorMessage(e, (key) => $i18n.t(key));
		}
	});
	const save = async () => {
		if (!draft || busy) return;
		draft.reflection_questions = normalizeReflectionQuestions(draft.reflection_questions);
		const invalid = getReflectionQuestionsError(draft.reflection_questions);
		if (invalid) {
			toast.error($i18n.t(invalid.key, invalid.params));
			return;
		}
		busy = true;
		try {
			if (draft.scoring_mode === 'total') draft.rubric_schema.criteria = [];
			else
				draft.score_max = draft.rubric_schema.criteria.reduce(
					(sum, row) => sum + Number(row.max_score),
					0
				);
			configs[selected] = await saveTeachingConfig(localStorage.token, draft);
			select(selected);
			toast.success($i18n.t('教学配置新版本已保存。'));
		} catch (e) {
			toast.error(resolveErrorMessage(e, (key) => $i18n.t(key)));
		} finally {
			busy = false;
		}
	};
</script>

<section class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
	<h2 class="font-medium">{$i18n.t('按作业类型配置教学')}</h2>
	<p class="text-xs text-gray-500">
		{$i18n.t(
			'新建作业采用当前版本；已有学生确认初稿或提交后，教学规则固定。默认说明、评分与反思仅用于新建预填。'
		)}
	</p>
	<p class="text-xs text-gray-500">{$i18n.t('教师可布置类型和默认类型在用户管理中逐账号设置。')}</p>
	{#if error}<p role="alert">{error}</p>{/if}
	<div class="flex flex-wrap gap-2">
		{#each TASK_TYPES as type}
			<button
				type="button"
				class="rounded-lg border px-3 py-2 text-sm"
				class:font-bold={selected === type.key}
				disabled={busy || !configs[type.key]}
				on:click={() => select(type.key)}>{$i18n.t(type.title)}</button
			>
		{/each}
	</div>
	{#if draft}
		<p class="text-xs">{$i18n.t('当前版本')} {draft.version}</p>
		<label class="block text-sm"
			>{$i18n.t('教学目标与判断标准')}<textarea
				class="mt-1 min-h-32 w-full rounded-lg dark:bg-gray-800"
				bind:value={draft.standards}
			></textarea></label
		>
		<label class="block text-sm"
			>{$i18n.t('辅导提示词')}<textarea
				class="mt-1 min-h-48 w-full rounded-lg dark:bg-gray-800"
				bind:value={draft.prompt}
			></textarea></label
		>
		<label class="block text-sm"
			>{$i18n.t('默认作业说明')}<textarea
				class="mt-1 min-h-32 w-full rounded-lg dark:bg-gray-800"
				bind:value={draft.default_description}
			></textarea></label
		>
		<label class="block text-sm"
			>{$i18n.t('默认评分设置')}<select
				class="ml-3 rounded-lg dark:bg-gray-800"
				bind:value={draft.scoring_mode}
				><option value="dimensions">{$i18n.t('按维度评分')}</option><option value="total"
					>{$i18n.t('仅总分与总评')}</option
				></select
			></label
		>
		{#if draft.scoring_mode === 'total'}
			<label
				>{$i18n.t('Maximum Score')}
				<input
					type="number"
					min="1"
					max="10000"
					bind:value={draft.score_max}
					class="w-24 rounded-lg dark:bg-gray-800"
				/></label
			>
		{:else}
			{#each draft.rubric_schema.criteria as row, index}
				<div class="flex gap-2">
					<input
						aria-label={$i18n.t('Criterion name')}
						class="min-w-0 flex-1 rounded-lg dark:bg-gray-800"
						bind:value={row.label}
					/><input
						aria-label={$i18n.t('Maximum Score')}
						type="number"
						min="1"
						class="w-20 rounded-lg dark:bg-gray-800"
						bind:value={row.max_score}
					/><button
						type="button"
						on:click={() =>
							(draft!.rubric_schema.criteria = draft!.rubric_schema.criteria.filter(
								(_, i) => i !== index
							))}>{$i18n.t('Delete')}</button
					>
				</div>
			{/each}
			<button
				type="button"
				disabled={draft.rubric_schema.criteria.length >= 8}
				on:click={() =>
					(draft!.rubric_schema.criteria = [
						...draft!.rubric_schema.criteria,
						{ key: `criterion_${Date.now()}`, label: '', max_score: 10 }
					])}>{$i18n.t('Add criterion')}</button
			>
		{/if}
		<ReflectionQuestionsEditor bind:questions={draft.reflection_questions} taskMode={selected} />
		<button
			type="button"
			class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-black"
			disabled={busy}
			on:click={save}>{$i18n.t('保存为新版本')}</button
		>
	{/if}
</section>
