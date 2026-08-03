<script lang="ts">
	// 卡片内部的列表行。比 EduCard 一档：圆角更小、无底色，
	// 用于「待批改」「近期提交」这类嵌套列表。
	export let interactive = false;
	export let tone: 'default' | 'rose' | 'amber' = 'default';
	let className = '';
	export { className as class };

	const TONES = {
		default: 'border-gray-200',
		rose: 'border-rose-200 bg-rose-50',
		amber: 'border-amber-200 bg-amber-50'
	};

	$: base = `rounded-2xl border ${TONES[tone]} px-4 py-4 text-sm`;
</script>

{#if interactive}
	<button
		type="button"
		class="{base} w-full text-left transition hover:border-gray-300 {className}"
		on:click
	>
		<slot />
	</button>
{:else}
	<div class="{base} {className}">
		<slot />
	</div>
{/if}
