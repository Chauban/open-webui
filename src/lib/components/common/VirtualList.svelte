<script lang="ts">
	export let items = [];
	export let rowHeight = 40;
	export let height = 320;
	export let overscan = 4;

	let scrollTop = 0;

	$: totalHeight = items.length * rowHeight;
	$: visibleCount = Math.max(1, Math.ceil(height / rowHeight) + overscan * 2);
	$: startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
	$: endIndex = Math.min(items.length, startIndex + visibleCount);
	$: visibleItems = items.slice(startIndex, endIndex);
</script>

<div
	class="w-full overflow-y-auto"
	style={`height: ${height}px;`}
	on:scroll={(event) => {
		scrollTop = event.currentTarget.scrollTop;
	}}
>
	<div class="relative w-full" style={`height: ${totalHeight}px;`}>
		{#each visibleItems as item, offset (startIndex + offset)}
			<div
				class="absolute left-0 w-full"
				style={`top: ${(startIndex + offset) * rowHeight}px; height: ${rowHeight}px;`}
			>
				<slot {item} />
			</div>
		{/each}
	</div>
</div>
