<script lang="ts">
	// 列表区的加载 / 空 / 报错三态盒子。此前报错框 15 处、
	// 空态与加载态 12 处，全是逐字重复的同一串类名。
	export let tone: 'muted' | 'error' = 'muted';
	let className = '';
	export { className as class };

	const TONES = {
		muted: 'border-gray-200 bg-white text-gray-500 dark:border-gray-800 dark:bg-gray-850 dark:text-gray-400',
		error:
			'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300'
	};
</script>

<div class="rounded-3xl border p-6 text-sm {TONES[tone]} {className}">
	<slot />
</div>
