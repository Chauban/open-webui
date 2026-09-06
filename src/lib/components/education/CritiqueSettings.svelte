<script lang="ts">
	// 作业上的「写作前评析」配置。
	//
	// 和提交前试读是一对：写之前评别人的文章建立判断标准，写完之后用同一标准挨质疑。
	// 所以这个控件紧挨着试读配置，教师一次配完「写前评什么、写后打什么」。
	//
	// 靶文来源决定这个功能会不会因为没人配而空转：教师不会自己写靶文，实践里应该
	// 从往届提交里挑一段脱敏，或者让 AI 生成后**逐条确认漏洞标注**——AI 指出的漏洞
	// 未必成立，直接挂上去就是教错。所以这里不提供「一键生成并启用」。
	import { getContext } from 'svelte';

	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import EduButton from '$lib/components/education/EduButton.svelte';

	const i18n = getContext('i18n');

	/** 当前作业的评分维度，取编辑器里的实时值而不是库里的旧值。 */
	export let criteria: Array<{ key: string; label: string }> = [];
	export let enabled = false;
	export let text = '';
	export let flaws: Array<{ key: string; description: string; focus_key: string }> = [];
	export let disabled = false;

	$: usableCriteria = criteria.filter(
		(criterion) => criterion.key?.trim() && criterion.label?.trim()
	);
	// 漏洞要绑到评分维度上，命中情况才能并进按维度的班级统计。
	$: configurable = usableCriteria.length > 0;

	// 维度被改名删除后，残留的绑定会让保存直接 422，这里先剪掉那几条。
	$: {
		const known = new Set(usableCriteria.map((criterion) => criterion.key));
		const pruned = flaws.filter((flaw) => known.has(flaw.focus_key));
		if (pruned.length !== flaws.length) {
			flaws = pruned;
		}
	}

	const addFlaw = () => {
		flaws = [
			...flaws,
			{
				key: `flaw-${flaws.length + 1}-${Math.random().toString(36).slice(2, 7)}`,
				description: '',
				focus_key: usableCriteria[0]?.key ?? ''
			}
		];
	};

	const removeFlaw = (key: string) => {
		flaws = flaws.filter((flaw) => flaw.key !== key);
	};
</script>

<div>
	<div class="mb-2 flex items-center gap-3">
		<span class="text-sm font-semibold">{$i18n.t('Pre-writing Critique')}</span>
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

	<div class="text-xs text-gray-400">
		{$i18n.t(
			'Before writing, students read a flawed text and point out what does not hold up. No score, no grade.'
		)}
	</div>
	<div class="mt-1 text-xs text-gray-400">
		{$i18n.t('The read-through presses on their own draft; this one trains the same eye first.')}
	</div>

	{#if !configurable}
		<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
			{$i18n.t('Add rubric criteria first, then you can turn on the critique.')}
		</div>
	{:else if enabled}
		<div class="mt-4">
			<div class="mb-2 text-xs font-medium text-gray-700 dark:text-gray-300">
				{$i18n.t('Target text')}
			</div>
			<textarea
				bind:value={text}
				{disabled}
				rows="6"
				class="w-full {EDU_FIELD_CLASS}"
				placeholder={$i18n.t(
					'Paste a passage with real problems — a redacted piece from a past class works best.'
				)}
			/>
		</div>

		<div class="mt-4">
			<div class="mb-2 flex items-center justify-between">
				<span class="text-xs font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('Problems planted in it')}
				</span>
				<EduButton variant="link" {disabled} on:click={addFlaw}>
					{$i18n.t('Add a problem')}
				</EduButton>
			</div>

			<!--
				这是判定的标准答案，必须由教师自己确认过。命中与否只用于记录，
				不给分、不设及格线。
			-->
			<div class="space-y-2">
				{#each flaws as flaw (flaw.key)}
					<div class="rounded-2xl bg-gray-50 px-3 py-3 dark:bg-gray-800">
						<textarea
							bind:value={flaw.description}
							{disabled}
							rows="2"
							class="w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t('What is wrong here')}
						/>
						<div class="mt-2 flex flex-wrap items-center gap-2">
							{#each usableCriteria as criterion (criterion.key)}
								<button
									type="button"
									aria-pressed={flaw.focus_key === criterion.key}
									class={eduSegmentClass(flaw.focus_key === criterion.key)}
									{disabled}
									on:click={() => (flaw.focus_key = criterion.key)}
								>
									{criterion.label}
								</button>
							{/each}
							<EduButton variant="link" {disabled} on:click={() => removeFlaw(flaw.key)}>
								{$i18n.t('Remove')}
							</EduButton>
						</div>
					</div>
				{/each}
			</div>

			{#if flaws.length === 0}
				<div class="mt-2 text-xs text-rose-600 dark:text-rose-400">
					{$i18n.t('Plant at least one problem for students to find.')}
				</div>
			{/if}
		</div>
	{/if}
</div>
