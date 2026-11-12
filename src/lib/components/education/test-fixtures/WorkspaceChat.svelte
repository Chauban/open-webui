<script lang="ts">
	import { onMount } from 'svelte';
	export let revisionMode = false;
	export let readingBusy = false;
	export let onSelectedModelsChange;
	export let beforeSend: () => Promise<void>;
	let prompt = '';
	let sent = false;
	onMount(() => onSelectedModelsChange(['teaching-model']));
</script>

<div data-testid="workspace-chat" aria-busy={revisionMode && readingBusy}>
	<slot name="input-accessory" />
	<input aria-label="Test message" bind:value={prompt} />
	<button
		on:click={async () => {
			try {
				await beforeSend();
				prompt = '';
				sent = true;
			} catch {
				/* retain input */
			}
		}}>Test send</button
	>
	{#if sent}<span>Test sent</span>{/if}
	<slot name="right-panel" />
</div>
