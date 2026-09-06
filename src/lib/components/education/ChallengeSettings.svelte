<script lang="ts">
	// 作业上的「提交前读者试读」配置。
	//
	// 只给三个控件。控件一多教师就直接用默认值不配了，这个功能等于白做。
	// 焦点直接复用评分维度：教师不用学新概念，学生被追问的点就是最后被扣分的点，
	// 质疑方向和评分标准天然对齐。
	import { getContext } from 'svelte';

	import { eduSegmentClass } from '$lib/components/education/styles';

	const i18n = getContext('i18n');

	/** 当前作业的评分维度，取编辑器里的实时值而不是库里的旧值。 */
	export let criteria: Array<{ key: string; label: string }> = [];
	export let enabled = false;
	export let rounds = 3;
	export let focusKeys: string[] = [];
	export let disabled = false;

	const ROUND_CHOICES = [2, 3];
	const MAX_FOCUS = 2;

	$: usableCriteria = criteria.filter(
		(criterion) => criterion.key?.trim() && criterion.label?.trim()
	);
	// 没有评分维度就没有可对齐的方向，后端也会拒绝。
	$: configurable = usableCriteria.length > 0;

	// 维度被改名删除后，残留的焦点 key 会让保存直接 422，这里先剪掉。
	$: {
		const known = new Set(usableCriteria.map((criterion) => criterion.key));
		const pruned = focusKeys.filter((key) => known.has(key));
		if (pruned.length !== focusKeys.length) {
			focusKeys = pruned;
		}
	}

	const toggleFocus = (key: string) => {
		if (focusKeys.includes(key)) {
			focusKeys = focusKeys.filter((item) => item !== key);
		} else if (focusKeys.length < MAX_FOCUS) {
			focusKeys = [...focusKeys, key];
		}
	};
</script>

<div>
	<div class="mb-2 flex items-center gap-3">
		<span class="text-sm font-semibold">{$i18n.t('Pre-submission Read-through')}</span>
		<label class="flex cursor-pointer items-center gap-2">
			<input
				type="checkbox"
				class="size-4 accent-black dark:accent-gray-100"
				bind:checked={enabled}
				disabled={disabled || !configurable}
			/>
			<span class="text-xs text-gray-600 dark:text-gray-300">{$i18n.t('Enable')}</span>
		</label>
	</div>

	<!-- 和辅导风格是两件事，两个控件被评分维度隔开了，说明必须自带对比。 -->
	<div class="text-xs text-gray-400">
		{$i18n.t(
			'Before submitting, an AI reader challenges the draft and the student has to answer. It never writes for them.'
		)}
	</div>
	<div class="mt-1 text-xs text-gray-400">
		{$i18n.t('Coaching style shapes help while writing; this applies right before submitting.')}
	</div>

	{#if !configurable}
		<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
			{$i18n.t('Add rubric criteria first, then you can turn on the read-through.')}
		</div>
	{:else if enabled}
		<div class="mt-4">
			<div class="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
				{$i18n.t('Rounds')}
			</div>
			<div class="flex flex-wrap gap-2">
				{#each ROUND_CHOICES as choice}
					<button
						type="button"
						aria-pressed={rounds === choice}
						class={eduSegmentClass(rounds === choice)}
						{disabled}
						on:click={() => (rounds = choice)}
					>
						{choice}
					</button>
				{/each}
			</div>
		</div>

		<div class="mt-4">
			<div class="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
				{$i18n.t('Focus on these rubric criteria (up to {{max}})', { max: MAX_FOCUS })}
			</div>
			<div class="flex flex-wrap gap-2">
				{#each usableCriteria as criterion (criterion.key)}
					<button
						type="button"
						aria-pressed={focusKeys.includes(criterion.key)}
						class={eduSegmentClass(focusKeys.includes(criterion.key))}
						disabled={disabled ||
							(!focusKeys.includes(criterion.key) && focusKeys.length >= MAX_FOCUS)}
						on:click={() => toggleFocus(criterion.key)}
					>
						{criterion.label}
					</button>
				{/each}
			</div>
			{#if focusKeys.length === 0}
				<div class="mt-2 text-xs text-rose-600 dark:text-rose-400">
					{$i18n.t('Pick at least one criterion for the reader to press on.')}
				</div>
			{/if}
		</div>
	{/if}
</div>
