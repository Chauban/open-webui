<script lang="ts">
	import ChevronDown from '../icons/ChevronDown.svelte';

	export let open = false;
	export let className = 'size-4';
	export let strokeWidth = '2';
</script>

<span class="disclosure-chevron" class:open aria-hidden="true">
	<ChevronDown {className} {strokeWidth} />
</span>

<style>
	.disclosure-chevron {
		display: inline-flex;
		flex-shrink: 0;
		vertical-align: middle;
		transform: rotate(-90deg);
		transition: transform 220ms ease;
	}
	.open {
		transform: rotate(0deg);
	}
	@media (prefers-reduced-motion: reduce) {
		.disclosure-chevron {
			transition: none;
		}
	}
</style>
