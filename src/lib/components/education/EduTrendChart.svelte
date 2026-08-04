<script lang="ts">
	import { getContext } from 'svelte';

	// 成长画像的趋势折线。教学模块不引第三方图表库，纯 SVG 就够：
	// 数据点个数是「提交次数」，量级很小，交互只需要点上的原生 tooltip。
	//
	// 同一张图里的所有序列共用一套 y 轴刻度，所以调用方要自己把量纲相同的指标
	// 放在一起（比率一张、指数一张、字数一张），不要混着传。

	type TrendSeries = {
		key: string;
		label: string;
		tone?: 'sky' | 'emerald' | 'amber' | 'rose' | 'violet' | 'gray';
		values: (number | null)[];
	};

	export let series: TrendSeries[] = [];
	export let labels: string[] = [];
	/** 固定 y 轴范围（指数固定 0-100、比率固定 0-1），不传则按数据自适应。 */
	export let min: number | null = null;
	export let max: number | null = null;
	export let formatValue: (value: number) => string = (value) => `${value}`;

	const i18n = getContext('i18n');

	const TONE_CLASSES = {
		sky: 'text-sky-500 dark:text-sky-400',
		emerald: 'text-emerald-500 dark:text-emerald-400',
		amber: 'text-amber-500 dark:text-amber-400',
		rose: 'text-rose-500 dark:text-rose-400',
		violet: 'text-violet-500 dark:text-violet-400',
		gray: 'text-gray-400 dark:text-gray-500'
	};

	const VIEW_WIDTH = 640;
	const VIEW_HEIGHT = 200;
	const PADDING = { top: 12, right: 12, bottom: 26, left: 44 };

	$: pointCount = Math.max(...series.map((item) => item.values.length), 0);
	$: allValues = series
		.flatMap((item) => item.values)
		.filter((value): value is number => typeof value === 'number');

	$: lowerBound = min ?? (allValues.length ? Math.min(...allValues) : 0);
	$: upperBound = max ?? (allValues.length ? Math.max(...allValues) : 1);
	// 全部数据相同时给一条基线留出上下空间，否则折线会贴在边框上。
	$: span = upperBound - lowerBound || Math.abs(upperBound) || 1;
	$: scaleLow = min ?? lowerBound - span * 0.1;
	$: scaleHigh = max ?? upperBound + span * 0.1;

	const plotWidth = VIEW_WIDTH - PADDING.left - PADDING.right;
	const plotHeight = VIEW_HEIGHT - PADDING.top - PADDING.bottom;

	const toX = (index: number, count: number) =>
		count <= 1 ? PADDING.left + plotWidth / 2 : PADDING.left + (index / (count - 1)) * plotWidth;
	const toY = (value: number, low: number, high: number) =>
		PADDING.top + plotHeight - ((value - low) / (high - low || 1)) * plotHeight;

	/** 缺值断线而不是连一条假的直线过去。 */
	const buildPath = (values: (number | null)[], count: number, low: number, high: number) => {
		let path = '';
		let penDown = false;
		values.forEach((value, index) => {
			if (typeof value !== 'number') {
				penDown = false;
				return;
			}
			const command = penDown ? 'L' : 'M';
			path += `${command}${toX(index, count).toFixed(2)},${toY(value, low, high).toFixed(2)} `;
			penDown = true;
		});
		return path.trim();
	};

	$: gridValues = [scaleHigh, (scaleHigh + scaleLow) / 2, scaleLow];
</script>

{#if pointCount < 2}
	<div class="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
		{$i18n.t('At least two submissions are needed to show a trend.')}
	</div>
{:else}
	<div class="overflow-x-auto">
		<svg
			viewBox="0 0 {VIEW_WIDTH} {VIEW_HEIGHT}"
			class="h-auto w-full min-w-[320px]"
			role="img"
			aria-label={series.map((item) => item.label).join(', ')}
		>
			{#each gridValues as gridValue}
				{@const y = toY(gridValue, scaleLow, scaleHigh)}
				<line
					x1={PADDING.left}
					x2={VIEW_WIDTH - PADDING.right}
					y1={y}
					y2={y}
					class="stroke-gray-200 dark:stroke-gray-800"
					stroke-width="1"
				/>
				<text
					x={PADDING.left - 8}
					y={y + 4}
					text-anchor="end"
					class="fill-gray-400 dark:fill-gray-500"
					font-size="11"
				>
					{formatValue(gridValue)}
				</text>
			{/each}

			{#each series as item}
				<g class={TONE_CLASSES[item.tone ?? 'sky']}>
					<path
						d={buildPath(item.values, pointCount, scaleLow, scaleHigh)}
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
					{#each item.values as value, index}
						{#if typeof value === 'number'}
							<circle
								cx={toX(index, pointCount)}
								cy={toY(value, scaleLow, scaleHigh)}
								r="3.5"
								fill="currentColor"
							>
								<title>{item.label} · {labels[index] ?? index + 1}: {formatValue(value)}</title>
							</circle>
						{/if}
					{/each}
				</g>
			{/each}

			{#each labels as label, index}
				{#if index === 0 || index === labels.length - 1 || labels.length <= 6}
					<text
						x={toX(index, pointCount)}
						y={VIEW_HEIGHT - 8}
						text-anchor={index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'}
						class="fill-gray-400 dark:fill-gray-500"
						font-size="11"
					>
						{label}
					</text>
				{/if}
			{/each}
		</svg>
	</div>

	<div class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-gray-500 dark:text-gray-400">
		{#each series as item}
			<span class="inline-flex items-center gap-1.5">
				<span class="h-2 w-2 rounded-full bg-current {TONE_CLASSES[item.tone ?? 'sky']}"></span>
				{item.label}
			</span>
		{/each}
	</div>
{/if}
