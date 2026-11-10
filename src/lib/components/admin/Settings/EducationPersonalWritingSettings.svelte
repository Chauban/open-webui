<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	export let student: boolean;
	export let teacher: boolean;
	export let disabled = false;
	export let onSave: (student: boolean, teacher: boolean) => void;
	const i18n: Writable<i18nType> = getContext('i18n');
</script>

<section class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
	<h3 class="text-sm font-medium">{$i18n.t('Personal Writing')}</h3>
	<p class="text-xs text-gray-500">
		{$i18n.t(
			'Control personal writing for each role. Assignment writing is unaffected. Existing drafts are kept when disabled. Administrators retain access.'
		)}
	</p>
	<fieldset {disabled} class="space-y-3">
		<label class="flex items-center justify-between gap-4 text-sm">
			{$i18n.t('Allow students to use personal writing')}
			<input type="checkbox" bind:checked={student} />
		</label>
		<label class="flex items-center justify-between gap-4 text-sm">
			{$i18n.t('Allow teachers to use personal writing')}
			<input type="checkbox" bind:checked={teacher} />
		</label>
		<button
			type="button"
			class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-black"
			on:click={() => onSave(student, teacher)}>{$i18n.t('Save')}</button
		>
	</fieldset>
</section>
