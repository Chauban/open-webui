<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';

	const i18n = getContext('i18n');

	const links = [
		{ href: '/teacher', label: 'Overview' },
		{ href: '/teacher/classrooms', label: 'Classrooms' },
		{ href: '/teacher/assignments', label: 'Assignments' },
		{ href: '/teacher/review', label: 'Review' }
	];

	const isActive = (href: string, pathname: string) => {
		if (href === '/teacher') {
			return pathname === '/teacher';
		}

		return pathname === href || pathname.startsWith(`${href}/`);
	};
</script>

<div class="mb-6 flex flex-wrap gap-2">
	{#each links as link}
		<a
			href={link.href}
			class={`rounded-full border px-4 py-2 text-sm transition ${
				isActive(link.href, $page.url.pathname)
					? 'border-black dark:border-gray-100 bg-black dark:bg-gray-100 text-white dark:text-gray-900'
					: 'border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-850 text-gray-700 dark:text-gray-300'
			}`}
		>
			{get(i18n).t(link.label)}
		</a>
	{/each}
</div>
