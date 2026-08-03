// 表单控件的类名常量。input / select / textarea 用组件包一层反而碍事
// （bind:value、option 插槽、原生属性），所以只把类名收成一处。

export const EDU_FIELD_CLASS =
	'rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none focus:border-gray-500 ' +
	'dark:border-gray-700 dark:bg-gray-850 dark:text-gray-100 dark:focus:border-gray-500';

// 未选中态：筛选与分段按钮共用。
const IDLE = 'border-gray-300 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-850 dark:text-gray-300';

// 筛选区的开关按钮：选中时按语义色高亮，未选中回落到普通描边。
const FILTER_TONES = {
	rose: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
	amber:
		'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
	sky: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300'
};

export const eduFilterClass = (active: boolean, tone: keyof typeof FILTER_TONES = 'rose') =>
	`rounded-full border px-4 py-2 text-sm transition ${active ? FILTER_TONES[tone] : IDLE}`;

// 分段选择器（全部 / 待批改 / 已批改…）：选中项反白。
export const eduSegmentClass = (active: boolean) =>
	`rounded-full border px-4 py-2 text-sm transition ${
		active
			? 'border-black bg-black text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
			: IDLE
	}`;
