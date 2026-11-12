<script>
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';

	import Dashboard from './Analytics/Dashboard.svelte';
	import ModelHealth from './Analytics/ModelHealth.svelte';
	let view =
		typeof window !== 'undefined' &&
		new URLSearchParams(window.location.search).get('model-health') === '1'
			? 'health'
			: 'usage';

	const i18n = getContext('i18n');

	let loaded = false;

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
		}
		loaded = true;
	});
</script>

{#if loaded}
	<div class="w-full h-full pb-2">
		<div
			class="flex gap-4 mb-3 border-b border-gray-200 dark:border-gray-800"
			role="group"
			aria-label={$i18n.t('Analytics')}
		>
			<button
				class="py-2"
				class:font-semibold={view === 'usage'}
				aria-pressed={view === 'usage'}
				on:click={() => (view = 'usage')}>{$i18n.t('Usage')}</button
			>
			<button
				class="py-2"
				class:font-semibold={view === 'health'}
				aria-pressed={view === 'health'}
				on:click={() => (view = 'health')}>{$i18n.t('Model health')}</button
			>
		</div>
		{#if view === 'health'}<ModelHealth />{:else}<Dashboard />{/if}
	</div>
{/if}
