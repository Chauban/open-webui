<script lang="ts">
	import Modal from './Modal.svelte';
	export let show = false;
	export let className = '';
	export let onClose = () => {};
	let wasOpen = show;
	$: {
		if (wasOpen && !show) onClose();
		wasOpen = show;
	}
</script>

<Modal bind:show size="full" placement="bottom" {className}>
	<slot />
</Modal>
