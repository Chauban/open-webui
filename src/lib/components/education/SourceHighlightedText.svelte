<script lang="ts">
	import { getContext } from 'svelte';
	import { writingAssetView } from './writing-document-extensions';
	const i18n: any = getContext('i18n');
	export let submissionId: string | null = null;
	import {
		buildSourceHighlightedHtml,
		buildTiptapSnapshotHtml
	} from '$lib/utils/source-highlights';

	export let text = '';
	export let json = null;
	export let segments: Array<{
		segment_id?: string;
		segment_text: string;
		source_type: string;
		start_offset?: number | null;
		end_offset?: number | null;
	}> = [];
	export let activeSegmentId = '';

	$: highlighted = json
		? buildTiptapSnapshotHtml({ json, fallbackText: text, segments, activeSegmentId })
		: buildSourceHighlightedHtml({ text, segments, activeSegmentId });
</script>

{#key highlighted + (submissionId ?? '')}<div
		use:writingAssetView={{ submissionId, t: (key) => $i18n.t(key) }}
		class="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap leading-7 break-words"
	>
		{@html highlighted}
	</div>{/key}
