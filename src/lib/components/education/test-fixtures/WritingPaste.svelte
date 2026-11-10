<script lang="ts">
	import WritingEditor from '../WritingEditor.svelte';
	import { textDocument } from '$lib/utils/writing-document';
	export let onImportFiles: (files: File[], source: string) => void;
	export let onProsePaste: () => void;
</script>

<WritingEditor
	value={textDocument('已有正文')}
	sessionId="session"
	{onImportFiles}
	on:paste={onProsePaste}
/>
