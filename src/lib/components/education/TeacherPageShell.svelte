<script lang="ts">
	import { getContext } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	const i18n = getContext('i18n');
	export let title = '';
	export let eyebrow = 'Teaching';
</script>

<div
	class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<nav class="w-full px-2.5 pt-1.5 backdrop-blur-xl drag-region">
		<div class="flex items-center">
			{#if $mobile}
				<div class="{$showSidebar ? 'md:hidden' : ''} mt-1.5 flex flex-none items-center self-end">
					<Tooltip
						content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
						interactive={true}
					>
						<button
							id="sidebar-toggle-button"
							class="flex cursor-pointer rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-850"
							on:click={() => showSidebar.set(!$showSidebar)}
						>
							<div class="self-center p-1.5">
								<SidebarIcon />
							</div>
						</button>
					</Tooltip>
				</div>
			{/if}

			<div class="ml-2 flex w-full items-center justify-between py-1">
				<div>
					<div class="text-xs uppercase tracking-[0.2em] text-gray-500">{$i18n.t(eyebrow)}</div>
					<h1 class="text-2xl font-semibold">{$i18n.t(title)}</h1>
				</div>
				<slot name="nav-actions" />
			</div>
		</div>
	</nav>

	<div class="flex-1 overflow-y-auto">
		<slot />
	</div>
</div>
