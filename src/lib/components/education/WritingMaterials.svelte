<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import { getWritingMaterials } from '$lib/apis/education';
	import type { WritingMaterial } from '$lib/types/writing-materials';
	import MaterialReview from './MaterialReview.svelte';

	export let sessionId: string | null = null;
	export let submissionId: string | null = null;
	export let materials: WritingMaterial[] = [];
	export let refresh = 0;
	const i18n = getContext<Writable<I18n>>('i18n');
	let error = false;
	let request = 0;
	$: if (sessionId) load(sessionId, refresh);
	async function load(id: string, _refresh: number) {
		const version = ++request;
		try {
			const result = await getWritingMaterials(localStorage.token, id);
			if (version === request) {
				materials = result;
				error = false;
			}
		} catch {
			if (version === request) error = true;
		}
	}
</script>

<div class="space-y-2">
	{#if error}<p role="alert" class="text-sm text-amber-700">
			{$i18n.t('Could not load the original material. Please try again.')}
		</p>{/if}
	{#each materials as material (material.id)}<MaterialReview {material} {submissionId} />{/each}
</div>
