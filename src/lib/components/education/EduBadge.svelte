<script lang="ts">
	// 风险/状态药丸。此前 20 余处逐字重复，且 py-1 与 py-1.5 两种高度混用。
	export let tone: 'gray' | 'rose' | 'amber' | 'sky' | 'emerald' = 'gray';
	// soft 用于标题旁的状态小标签：无描边、底色更实、更紧凑。
	export let soft = false;
	let className = '';
	export { className as class };

	const TONES = {
		gray: 'border-gray-200 bg-gray-50 text-gray-700',
		rose: 'border-rose-200 bg-rose-50 text-rose-700',
		amber: 'border-amber-200 bg-amber-50 text-amber-700',
		sky: 'border-sky-200 bg-sky-50 text-sky-700',
		emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700'
	};
	const SOFT_TONES = {
		gray: 'bg-gray-100 text-gray-600',
		rose: 'bg-rose-100 text-rose-700',
		amber: 'bg-amber-100 text-amber-700',
		sky: 'bg-sky-100 text-sky-700',
		emerald: 'bg-emerald-100 text-emerald-700'
	};

	$: shape = soft
		? `px-2.5 py-0.5 text-xs ${SOFT_TONES[tone]}`
		: `border px-3 py-1.5 ${TONES[tone]}`;
</script>

<span class="rounded-full {shape} {className}" {...$$restProps}>
	<slot />
</span>
