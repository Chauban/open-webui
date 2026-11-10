<script lang="ts">
	import { textDocument, documentText } from '$lib/utils/writing-document';
	export let value: any = null;
	export let editable = true;
	export let placeholder = '';
	export let onChange: (content: any) => void = () => {};
	export let editor: any = null;
</script>

<textarea
	data-testid="workspace-editor"
	data-has-editor={Boolean(editor)}
	{placeholder}
	readonly={!editable}
	value={JSON.stringify(value)}
	on:input={(event) => {
		value = textDocument(event.currentTarget.value);
		onChange({
			docChanged: true,
			programmatic: false,
			json: value,
			text: documentText(value),
			md: documentText(value),
			html: ''
		});
	}}
></textarea>
