<script lang="ts">
	import { onMount } from 'svelte';
	export let revisionMode = false;
	export let readingBusy = false;
	export let onSelectedModelsChange;
	onMount(() => onSelectedModelsChange(['teaching-model']));
</script>

<div data-testid="workspace-chat" aria-busy={revisionMode && readingBusy}>
	<slot name="right-panel" />
</div>
