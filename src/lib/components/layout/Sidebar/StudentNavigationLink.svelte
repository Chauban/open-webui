<script lang="ts">
	import { getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';
	import { writingHomeIdentity, writingHomeRequests } from '$lib/apis/education/home';
	import Clipboard from '$lib/components/icons/Clipboard.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import HotkeyHint from '$lib/components/common/HotkeyHint.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');
	export let kind: 'assignments' | 'free-chat' = 'assignments';
	export let collapsed = false;
	export let active = false;
	export let unread = 0;
	export let onNavigate: () => void = () => {};
	$: label = kind === 'assignments' ? 'My Assignments' : 'Free Chat';
	$: href = kind === 'assignments' ? '/me/writing' : '/';
</script>

<Tooltip content={collapsed ? $i18n.t(label) : ''} placement="right" className="block">
	<a
		{href}
		aria-label={$i18n.t(label)}
		aria-current={active ? 'page' : undefined}
		draggable="false"
		class="group relative flex items-center gap-2 rounded-xl text-[0.8125rem] leading-5 outline-none transition focus-visible:ring-2 focus-visible:ring-[#20406A] {collapsed
			? 'size-8 justify-center'
			: 'mx-1 px-2 py-1.5'} {active
			? 'bg-black/[0.035] text-[#20406A] dark:bg-white/[0.06] dark:text-gray-100'
			: 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-900'}"
		on:click={(event) => {
			// The collapsed sidebar opens on bubbled clicks. Since this also stops
			// SvelteKit's delegated link handler, route plain clicks explicitly.
			event.stopPropagation();
			if (
				event.defaultPrevented ||
				event.button !== 0 ||
				event.metaKey ||
				event.ctrlKey ||
				event.shiftKey ||
				event.altKey
			)
				return;
			event.preventDefault();
			// Start the safe list GET at the user's click, overlapping long-editor teardown.
			// The destination shares this in-flight read; no hover or workspace prefetch.
			if (kind === 'assignments' && $user?.id && localStorage.token) {
				void writingHomeRequests
					.load(writingHomeIdentity($user, localStorage.token, location.origin), localStorage.token)
					.catch(() => {});
			}
			onNavigate();
			goto(href);
		}}
	>
		{#if kind === 'assignments'}
			<Clipboard className="size-4 shrink-0" />
		{:else}
			<Plus className="size-4 shrink-0" />
		{/if}
		{#if !collapsed}
			<span class:font-medium={kind === 'assignments'} class="min-w-0 flex-1">{$i18n.t(label)}</span
			>
			{#if kind === 'free-chat'}<HotkeyHint name="newChat" className="hover-reveal" />{/if}
		{/if}
		{#if kind === 'assignments' && unread > 0}
			<span
				class="flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] text-white {collapsed
					? 'absolute -right-1 -top-1'
					: ''}">{unread > 99 ? '99+' : unread}</span
			>
		{/if}
	</a>
</Tooltip>
