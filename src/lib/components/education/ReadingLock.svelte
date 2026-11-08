<script lang="ts">
	import ReadingProgress from './ReadingProgress.svelte';
	export let locked = false;
	export let showProgress = true;
</script>

<div class="relative flex min-h-0 flex-1 flex-col" aria-busy={locked}>
	<div class="flex min-h-0 flex-1 flex-col" inert={locked}>
		<slot />
	</div>
	{#if locked}
		<div
			class="absolute inset-0 z-20 flex items-center justify-center bg-white/75 px-6 backdrop-blur-[2px] dark:bg-gray-900/80"
		>
			{#if showProgress}<ReadingProgress />{/if}
		</div>
	{/if}
</div>
