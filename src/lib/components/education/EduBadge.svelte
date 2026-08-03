<script lang="ts">
	// 风险/状态药丸。此前 20 余处逐字重复，且 py-1 与 py-1.5 两种高度混用。
	export let tone: 'gray' | 'rose' | 'amber' | 'sky' | 'emerald' = 'gray';
	// soft 用于标题旁的状态小标签：无描边、底色更实、更紧凑。
	export let soft = false;
	let className = '';
	export { className as class };

	const TONES = {
		gray: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300',
		rose: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300',
		amber:
			'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300',
		sky: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300',
		emerald:
			'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
	};
	const SOFT_TONES = {
		gray: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
		rose: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300',
		amber: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
		sky: 'bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300',
		emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
	};

	$: shape = soft
		? `px-2.5 py-0.5 text-xs ${SOFT_TONES[tone]}`
		: `border px-3 py-1.5 ${TONES[tone]}`;
</script>

<span class="rounded-full {shape} {className}" {...$$restProps}>
	<slot />
</span>
