<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import { getWritingMaterialAsset } from '$lib/apis/education';
	import type { WritingMaterial } from '$lib/types/writing-materials';
	import EduButton from './EduButton.svelte';

	export let material: WritingMaterial;
	export let editable = false;
	export let disabled = false;
	export let submissionId: string | null = null;
	const i18n = getContext<Writable<I18n>>('i18n');
	let previews: Record<string, string> = {};
	let loading = '';
	let failed = false;
	let disposed = false;
	$: missing = material.blocks.filter((block) => block.status === 'unreadable').length;
	onDestroy(() => {
		disposed = true;
		Object.values(previews).forEach((url) => URL.revokeObjectURL(url));
	});
	async function asset(id: string) {
		loading = id;
		failed = false;
		try {
			const blob = await getWritingMaterialAsset(localStorage.token, material.id, id, submissionId);
			if (disposed) return;
			const url = URL.createObjectURL(blob);
			if (id === 'original') {
				const anchor = document.createElement('a');
				anchor.href = url;
				anchor.download = material.filename;
				anchor.click();
				setTimeout(() => URL.revokeObjectURL(url), 1000);
			} else {
				if (previews[id]) URL.revokeObjectURL(previews[id]);
				previews = { ...previews, [id]: url };
			}
		} catch {
			failed = true;
		} finally {
			loading = '';
		}
	}
</script>

<details class="rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700" open={editable}>
	<summary class="cursor-pointer font-medium"
		>{material.filename} · {$i18n.t('Attached materials')} ({material.blocks.length})</summary
	>
	<p class="my-2 text-xs text-gray-500">
		{$i18n.t(
			'These original materials accompany every AI reading and conversation. They are separate from your current writing. Reading a source does not verify its authenticity.'
		)}
	</p>
	{#if missing}
		<p role="alert" class="mb-2 text-amber-700 dark:text-amber-300">
			{$i18n.t(
				'{{count}} material item(s) could not be fully read. Check the original or supplement the text; the AI will receive this reading gap.',
				{ count: missing }
			)}
		</p>
	{/if}
	<EduButton size="sm" disabled={!!loading} on:click={() => asset('original')}
		>{$i18n.t('Download original file')}</EduButton
	>
	{#if failed}<p role="alert">
			{$i18n.t('Could not load the original material. Please try again.')}
		</p>{/if}
	<div class="mt-3 space-y-3">
		{#each material.blocks as block (block.id)}
			<div class="border-t border-gray-200 pt-2 dark:border-gray-700">
				<p class="font-medium">{block.location} · {block.id}</p>
				{#if block.detail}<p class="my-1 text-xs text-amber-700 dark:text-amber-300">
						{$i18n.t(block.detail)}
					</p>{/if}
				{#if block.image}
					<EduButton size="sm" disabled={!!loading} on:click={() => asset(`${block.id}.jpg`)}
						>{$i18n.t('View original image')}</EduButton
					>
					{#if previews[`${block.id}.jpg`]}<img
							class="my-2 max-h-96 max-w-full object-contain"
							src={previews[`${block.id}.jpg`]}
							alt={block.location}
						/>{/if}
				{/if}
				{#if editable}
					<textarea
						class="mt-2 min-h-24 w-full rounded border border-gray-300 bg-transparent p-2 dark:border-gray-600"
						aria-label={`${$i18n.t('Material text')} ${block.id}`}
						bind:value={block.text}
						{disabled}
						maxlength={200000}
					></textarea>
				{:else}
					<p class="mt-2 whitespace-pre-wrap break-words">
						{block.text || $i18n.t('This material has not been read.')}
					</p>
				{/if}
			</div>
		{/each}
	</div>
</details>
