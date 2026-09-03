<script lang="ts">
	// 评分维度编辑器：新建作业页与作业详情页共用。
	// 维度的 key 由前端自动生成（教师不需要、也不该填英文标识），
	// 教师只填「名称 + 满分」，并随时看到分值分配是否已经配平。
	import { getContext } from 'svelte';

	import EduButton from './EduButton.svelte';
	import { EDU_FIELD_CLASS } from './styles';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { distributeCriterionScores, nextCriterionKey } from '$lib/utils/education';

	const i18n = getContext('i18n');

	export let criteria: { key: string; label: string; maxScore: string }[] = [];
	export let scoreMax: number | string = '';
	export let disabled = false;
	export let lockedHint = '';

	// 后端 RubricSchema 限定 1-8 个维度。
	const MAX_CRITERIA = 8;

	$: parsedScoreMax = Number(scoreMax);
	$: allocated = criteria.reduce((sum, criterion) => sum + (Number(criterion.maxScore) || 0), 0);
	$: remaining = (Number.isFinite(parsedScoreMax) ? parsedScoreMax : 0) - allocated;
	$: balanced = remaining === 0 && allocated > 0;

	const updateCriterion = (index: number, patch: Record<string, string>) => {
		criteria = criteria.map((criterion, itemIndex) =>
			itemIndex === index ? { ...criterion, ...patch } : criterion
		);
	};

	const addCriterion = () => {
		if (criteria.length >= MAX_CRITERIA) return;
		criteria = [
			...criteria,
			{
				key: nextCriterionKey(criteria.map((criterion) => criterion.key)),
				label: '',
				// 还差多少就先填多少，多数情况下加完一行分值就配平了。
				maxScore: remaining > 0 ? String(remaining) : ''
			}
		];
	};

	const removeCriterion = (index: number) => {
		if (criteria.length <= 1) return;
		criteria = criteria.filter((_, itemIndex) => itemIndex !== index);
	};

	const distributeEvenly = () => {
		const scores = distributeCriterionScores(criteria.length, parsedScoreMax);
		if (scores.length === 0) return;
		criteria = criteria.map((criterion, index) => ({
			...criterion,
			maxScore: String(scores[index])
		}));
	};
</script>

<div>
	<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
		<div class="flex items-center gap-2">
			<div class="text-sm font-semibold">{$i18n.t('Rubric Criteria')}</div>
			<span
				class="rounded-full px-2 py-0.5 text-xs {balanced
					? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
					: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'}"
			>
				{$i18n.t('{{allocated}} / {{total}} allocated', {
					allocated,
					total: Number.isFinite(parsedScoreMax) ? parsedScoreMax : 0
				})}
			</span>
		</div>
		<div class="flex items-center gap-2">
			<EduButton
				size="sm"
				disabled={disabled || !(parsedScoreMax >= criteria.length)}
				on:click={distributeEvenly}
			>
				{$i18n.t('Distribute Evenly')}
			</EduButton>
			<EduButton
				size="sm"
				disabled={disabled || criteria.length >= MAX_CRITERIA}
				on:click={addCriterion}
			>
				{$i18n.t('Add Criterion')}
			</EduButton>
		</div>
	</div>

	<div class="space-y-2">
		{#each criteria as criterion, index (criterion.key)}
			<div class="flex items-center gap-2">
				<span class="w-5 shrink-0 text-center text-xs text-gray-400">{index + 1}</span>
				<input
					value={criterion.label}
					{disabled}
					class="min-w-0 flex-1 {EDU_FIELD_CLASS} disabled:opacity-60"
					placeholder={$i18n.t('Criterion label')}
					on:input={(event) => updateCriterion(index, { label: event.currentTarget.value })}
				/>
				<div class="flex shrink-0 items-center gap-1.5">
					<input
						value={criterion.maxScore}
						type="number"
						min="1"
						step="1"
						{disabled}
						class="w-24 {EDU_FIELD_CLASS} disabled:opacity-60"
						on:input={(event) => updateCriterion(index, { maxScore: event.currentTarget.value })}
					/>
					<span class="text-xs text-gray-400">{$i18n.t('pts')}</span>
				</div>
				<button
					type="button"
					disabled={disabled || criteria.length <= 1}
					title={$i18n.t('Remove')}
					aria-label={$i18n.t('Remove')}
					class="shrink-0 rounded-full p-2 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-gray-400 dark:hover:bg-red-950/40 dark:hover:text-red-400"
					on:click={() => removeCriterion(index)}
				>
					<XMark className="size-4" />
				</button>
			</div>
		{/each}
	</div>

	<div class="mt-2 text-xs {balanced ? 'text-gray-400' : 'text-amber-600 dark:text-amber-400'}">
		{#if lockedHint}
			{lockedHint}
		{:else if balanced}
			{$i18n.t('Rubric maximum scores add up to the assignment maximum.')}
		{:else if remaining > 0}
			{$i18n.t('{{count}} points still unallocated.', { count: remaining })}
		{:else}
			{$i18n.t('{{count}} points over the assignment maximum.', { count: -remaining })}
		{/if}
	</div>
</div>
