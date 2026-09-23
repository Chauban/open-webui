<script lang="ts">
	// 作业上的「提交前 AI 读者试读」配置。
	//
	// 只给三个控件。控件一多教师就直接用默认值不配了，这个功能等于白做。
	// 焦点直接复用评分维度：教师不用学新概念，学生被追问的点就是最后被扣分的点，
	// 质疑方向和评分标准天然对齐。
	//
	// 这一块单独框起来：它和上面几项不是一个量级——开了就会在交卷那一步拦人，
	// 混在普通表单项里教师会顺手划过去。
	import { getContext } from 'svelte';

	import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte';
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

	$: focusLabels = usableCriteria
		.filter((criterion) => focusKeys.includes(criterion.key))
		.map((criterion) => criterion.label);

	const toggleFocus = (key: string) => {
		if (focusKeys.includes(key)) {
			focusKeys = focusKeys.filter((item) => item !== key);
		} else if (focusKeys.length < MAX_FOCUS) {
			focusKeys = [...focusKeys, key];
		}
	};
</script>

<div
	class="rounded-2xl border p-4 transition-colors {enabled && configurable
		? 'border-gray-900 bg-gray-50 dark:border-gray-100 dark:bg-gray-900'
		: 'border-gray-300 bg-white dark:border-gray-700 dark:bg-gray-900'}"
>
	<div class="flex items-start gap-3">
		<span
			class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full border border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-200"
		>
			<QuestionMarkCircle className="size-5" />
		</span>

		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<span class="text-sm font-semibold">{$i18n.t('AI Reader Check Before Submitting')}</span>
				<span
					class="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300"
				>
					{$i18n.t('The last gate before the draft is handed in')}
				</span>
			</div>
			<div class="mt-1.5 text-xs leading-relaxed text-gray-600 dark:text-gray-300">
				{$i18n.t(
					'The student is stopped at submit: an AI reader who is not convinced points at specific sentences and asks why. Only after answering can the draft go in. It asks; it never hands over the sentence.'
				)}
			</div>
		</div>

		<!-- 开关做成拨杆：这一项是「拦不拦人」，勾选框太轻了。 -->
		<label
			class="flex shrink-0 items-center gap-2 {disabled || !configurable
				? 'cursor-not-allowed opacity-60'
				: 'cursor-pointer'}"
		>
			<span class="relative inline-flex h-5 w-9 shrink-0 items-center">
				<input
					type="checkbox"
					class="peer sr-only"
					bind:checked={enabled}
					disabled={disabled || !configurable}
				/>
				<span
					class="absolute inset-0 rounded-full bg-gray-300 transition-colors peer-checked:bg-gray-900 dark:bg-gray-600 dark:peer-checked:bg-gray-100"
				></span>
				<span
					class="absolute left-0.5 size-4 rounded-full bg-white transition-transform peer-checked:translate-x-4 dark:bg-gray-300 dark:peer-checked:bg-gray-900"
				></span>
			</span>
			<span class="text-xs font-medium text-gray-700 dark:text-gray-200">
				{enabled ? $i18n.t('On') : $i18n.t('Off')}
			</span>
		</label>
	</div>

	<!-- 和辅导风格是两件事，两个控件被评分维度隔开了，说明必须自带对比。 -->
	<div class="mt-2 pl-12 text-xs text-gray-400 dark:text-gray-500">
		{$i18n.t(
			'Coaching style decides how much help the student gets while writing. This one is separate, and only runs at the moment of submitting.'
		)}
	</div>

	{#if !configurable}
		<div class="mt-3 pl-12 text-xs text-amber-600 dark:text-amber-400">
			{$i18n.t('Add rubric criteria first, then you can turn on the read-through.')}
		</div>
	{:else if enabled}
		<div class="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
			<div class="grid gap-4 sm:grid-cols-[auto_1fr] sm:gap-6">
				<div>
					<div class="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
						{$i18n.t('Rounds of questioning')}
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
					<div class="mt-2 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t("Every round has to be answered in the student's own words.")}
					</div>
				</div>

				<div>
					<div class="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
						{$i18n.t('Press on these rubric criteria (up to {{max}})', { max: MAX_FOCUS })}
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
					{:else}
						<div class="mt-2 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('What the reader presses on is what you will be grading.')}
						</div>
					{/if}
				</div>
			</div>

			{#if focusKeys.length > 0}
				<div
					class="mt-4 rounded-xl bg-white px-3 py-2 text-xs text-gray-600 dark:bg-gray-850 dark:text-gray-300"
				>
					{$i18n.t(
						'Students will face {{rounds}} rounds of questions on {{focus}} before the draft goes in.',
						{
							rounds,
							focus: focusLabels.join(' · ')
						}
					)}
				</div>
			{/if}
		</div>
	{/if}
</div>
