<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import { config, mobile, showSidebar, user } from '$lib/stores';
	import NotesIcon from './Sidebar/icons/Notes.svelte';

	export let collapsed = false;
	const i18n = getContext('i18n');
</script>

{#if $config?.features?.enable_courseware && ['user', 'admin'].includes($user?.role)}
	<div class={collapsed ? '' : 'px-1 text-gray-700 dark:text-gray-300'}>
		<a
			href="/courseware"
			aria-label={$i18n.t('Courseware')}
			aria-current={$page.url.pathname === '/courseware' ? 'page' : undefined}
			title={$i18n.t('Courseware')}
			class="flex items-center rounded-xl hover:bg-gray-100 dark:hover:bg-gray-900 {collapsed
				? 'size-8 justify-center'
				: 'gap-2 px-2 py-1.5 text-[0.8125rem] leading-5'}"
			on:click={() => {
				if ($mobile) showSidebar.set(false);
			}}
		>
			<NotesIcon className="size-4 shrink-0" strokeWidth="1.5" />
			{#if !collapsed}<span>{$i18n.t('Courseware')}</span>{/if}
		</a>
	</div>
{/if}
