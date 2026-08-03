<script lang="ts">
	// 教学模块的基础卡片面。此前 60 余处逐字重复 rounded-3xl border ... bg-white p-5，
	// 内距散落 p-4/p-5/p-6/p-8、悬停边框 gray-300/gray-400 各行其是。
	export let tone: 'default' | 'muted' | 'rose' | 'amber' | 'sky' = 'default';
	// none 用于内部自带内距的场景（表格容器）。
	export let padding: 'none' | 'md' | 'lg' = 'md';
	export let interactive = false;
	let className = '';
	export { className as class };

	const TONES = {
		default: 'border-gray-200 bg-white',
		muted: 'border-gray-200 bg-gray-50',
		rose: 'border-rose-200 bg-rose-50',
		amber: 'border-amber-200 bg-amber-50',
		sky: 'border-sky-200 bg-sky-50'
	};
	const PADDINGS = { none: 'overflow-hidden', md: 'p-5', lg: 'p-6' };

	$: surface = `rounded-3xl border ${TONES[tone]} ${PADDINGS[padding]} ${className}`;
</script>

{#if interactive}
	<button
		type="button"
		class="{surface} w-full text-left transition hover:border-gray-400"
		on:click
	>
		<slot />
	</button>
{:else}
	<div class={surface}>
		<slot />
	</div>
{/if}
