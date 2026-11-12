<script lang="ts">
	import { onMount } from 'svelte';
	export let loadWorkspace: () => Promise<any>;
	let title = '';
	onMount(() => {
		void loadWorkspace().then((workspace) => (title = workspace.assignment.title));
	});
</script>

{#if title}<h1>{title}</h1>{/if}
