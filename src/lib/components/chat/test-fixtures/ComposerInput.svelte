<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	const dispatch = createEventDispatcher();
</script>

<textarea
	id="chat-input"
	data-testid="composer-input"
	on:keydown={(event) => dispatch('keydown', { event })}
></textarea>
