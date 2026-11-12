<script lang="ts">
	import { onMount } from 'svelte';
	export let chatIdProp = '';
	const initialChatId = chatIdProp;
	export let revisionMode = false;
	export let readingBusy = false;
	export let conversationLoading = false;
	export let onSelectedModelsChange;
	export let beforeSend: () => Promise<void>;
	let prompt = '';
	let sent = false;
	onMount(() => {
		conversationLoading = false;
		onSelectedModelsChange(['teaching-model']);
	});
</script>

<div
	data-testid="workspace-chat"
	data-chat-id={chatIdProp}
	data-initial-chat-id={initialChatId}
	aria-busy={revisionMode && readingBusy}
>
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
