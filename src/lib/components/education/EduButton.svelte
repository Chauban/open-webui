<script lang="ts">
	// 教学模块的按钮。此前主按钮 9 种、次按钮 17 种逐字变体，
	// 内距、字号、hover、disabled 处理各不相同。
	export let variant: 'primary' | 'secondary' | 'danger' | 'link' = 'secondary';
	export let size: 'sm' | 'md' = 'md';
	export let type: 'button' | 'submit' = 'button';
	export let disabled = false;
	let className = '';
	export { className as class };

	const VARIANTS = {
		primary:
			'rounded-full bg-black text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white',
		secondary:
			'rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800',
		danger:
			'rounded-full border border-red-300 text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40',
		// 分区标题右侧的「查看全部」这类跳转，无边框无底色。
		link: 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
	};
	const SIZES = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm' };

	$: padding = variant === 'link' ? 'text-sm' : SIZES[size];
</script>

<button
	{type}
	{disabled}
	class="transition-colors disabled:opacity-60 {VARIANTS[variant]} {padding} {className}"
	on:click
>
	<slot />
</button>
