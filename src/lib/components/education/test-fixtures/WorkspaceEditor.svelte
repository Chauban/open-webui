<script lang="ts">
	export let value = null;
	export let editable = true;
</script>

<textarea data-testid="workspace-editor" readonly={!editable} value={JSON.stringify(value)}></textarea>
