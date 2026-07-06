<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';
	import { showSidebar, mobile } from '$lib/stores';

	const i18n = getContext('i18n');

	export let assignmentId = '';
	export let title = '';
	export let status = 'not_started';
	export let updatedAt: number | null = null;

	$: isSelected = $page.url.pathname === `/assignments/${assignmentId}/write`;

	const formatUpdatedAt = (value: number | null) => {
		if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
			return null;
		}

		const date = new Date(value * 1000);
		if (Number.isNaN(date.getTime())) {
			return null;
		}

		return date.toLocaleDateString();
	};

	const statusLabel = (value: string) => {
		if (value === 'submitted') return $i18n.t('Submitted');
		if (value === 'draft') return $i18n.t('In progress');
		return $i18n.t('Not started');
	};

	const statusClass = (value: string) => {
		if (value === 'submitted') return 'bg-emerald-100 text-emerald-700';
		if (value === 'draft') return 'bg-amber-100 text-amber-700';
		return 'bg-stone-100 text-gray-600';
	};
</script>

<a
	id="sidebar-assignment-item"
	class="flex w-full items-center justify-between rounded-xl px-[11px] py-[8px] whitespace-nowrap text-ellipsis {isSelected
		? 'bg-gray-100 dark:bg-gray-900 selected'
		: 'group-hover:bg-gray-100 dark:group-hover:bg-gray-950'}"
	href="/assignments/{assignmentId}/write"
	on:click={() => {
		if ($mobile) {
			showSidebar.set(false);
		}
	}}
>
	<div class="min-w-0 flex-1">
		<div dir="auto" class="truncate text-left text-sm">
			{title}
		</div>
		{#if formatUpdatedAt(updatedAt)}
			<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
				{formatUpdatedAt(updatedAt)}
			</div>
		{/if}
	</div>

	<div class="ml-2 rounded-full px-2 py-1 text-[10px] font-medium {statusClass(status)}">
		{statusLabel(status)}
	</div>
</a>
