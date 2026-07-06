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
					? 'border-black bg-black text-white'
					: 'border-gray-300 bg-white text-gray-700'
			}`}
		>
			{get(i18n).t(link.label)}
		</a>
	{/each}
</div>
