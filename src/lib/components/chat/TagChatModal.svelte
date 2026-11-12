<script lang="ts">
	import { getContext } from 'svelte';
	import Modal from '../common/Modal.svelte';

	import Tags from '../common/Tags.svelte';

	const i18n = getContext('i18n');

	export let tags;
	export let deleteTag: Function;
	export let addTag: Function;

	export let show = false;
</script>

<Modal bind:show size="xs" title={$i18n.t('Tags')}>
	<div class="w-full flex flex-col">
		<Tags
			{tags}
			on:delete={(e) => {
				deleteTag(e.detail);
			}}
			on:add={(e) => {
				addTag(e.detail);
			}}
		/>
	</div>
</Modal>
