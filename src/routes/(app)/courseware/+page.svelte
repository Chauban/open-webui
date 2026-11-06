<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { config, showSidebar } from '$lib/stores';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';

	const i18n = getContext('i18n');
	let ready = false;
	let unavailable = false;

	onMount(async () => {
		if (!$config?.features?.enable_courseware) {
			unavailable = true;
			return;
		}
		try {
			// Use the same cookie as the iframe and video requests, not a token in URLs.
			const response = await fetch(`${WEBUI_API_BASE_URL}/courseware/`, {
				credentials: 'include',
				cache: 'no-store'
			});
			if (response.status === 401) {
				await goto('/auth?redirect=%2Fcourseware');
				return;
			}
			if (!response.ok) throw new Error('Courseware unavailable');
			ready = true;
		} catch {
			unavailable = true;
		}
	});
</script>

<svelte:head><title>{$i18n.t('Courseware')} · Right Write</title></svelte:head>

<div
	class="flex h-full min-w-0 w-full flex-col {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<header
		class="flex shrink-0 items-center gap-3 border-b border-gray-200 px-3 py-2 dark:border-gray-800"
	>
		<button
			class="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-800"
			aria-label={$i18n.t('Toggle sidebar')}
			on:click={() => showSidebar.set(!$showSidebar)}><SidebarIcon className="size-5" /></button
		>
		<h1 class="flex-1 font-medium">{$i18n.t('Courseware')}</h1>
		<a class="rounded-lg px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800" href="/">
			{$i18n.t('Back to Right Write')}
		</a>
	</header>
	{#if ready}
		<iframe
			class="min-h-0 w-full flex-1 border-0 bg-white"
			title={$i18n.t('Courseware')}
			src={`${WEBUI_API_BASE_URL}/courseware/content/index.html`}
			allow="fullscreen"
		></iframe>
	{:else}
		<p class="p-8 text-center text-gray-500" role="status">
			{unavailable ? $i18n.t('Courseware is not available') : $i18n.t('Loading...')}
		</p>
	{/if}
</div>
