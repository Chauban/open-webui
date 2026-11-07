<script lang="ts">
	export let values: string[] = [];
	export let items: Array<{ value: string; label: string }> = [];
</script>

<select aria-label="Choose a model" bind:value={values[0]}>
	{#each items as item}<option value={item.value}>{item.label}</option>{/each}
</select>
