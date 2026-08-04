<script lang="ts">
	import { getContext } from 'svelte';

	// 单个指标的「最近值 + 相对首次的变化」。画像里成长看的是变化率，
	// 所以数值旁边一定要带方向，否则跟旧的静态统计卡没区别。

	export let label = '';
	/** 指标含义与算法的一句话解释，鼠标悬停可见——画像不做黑箱数字。 */
	export let hint = '';
	export let value: number | null = null;
	export let delta: number | null = null;
	export let direction: 'up' | 'down' | 'flat' | null = null;
	/** 该指标变大是不是好事；unknown 表示中性，只显示方向不着色。 */
	export let higherIsBetter: 'yes' | 'no' | 'unknown' = 'unknown';
	export let format: (value: number) => string = (input) => `${input}`;

	const i18n = getContext('i18n');

	const ARROWS = { up: '↑', down: '↓', flat: '→' };

	$: tone =
		direction == null || direction === 'flat' || higherIsBetter === 'unknown'
			? 'text-gray-500 dark:text-gray-400'
			: (direction === 'up') === (higherIsBetter === 'yes')
				? 'text-emerald-600 dark:text-emerald-400'
				: 'text-amber-600 dark:text-amber-400';
</script>

<div class="flex flex-col gap-1">
	<div
		class="text-xs uppercase tracking-[0.12em] text-gray-400 dark:text-gray-500"
		title={hint ? $i18n.t(hint) : undefined}
	>
		{$i18n.t(label)}
	</div>
	<div class="text-2xl font-semibold text-gray-900 dark:text-gray-100">
		{value == null ? '—' : format(value)}
	</div>
	{#if direction}
		<div class="text-xs {tone}">
			{ARROWS[direction]}
			{delta == null ? '' : format(Math.abs(delta))}
			<span class="text-gray-400 dark:text-gray-500">{$i18n.t('vs first submission')}</span>
		</div>
	{/if}
</div>
