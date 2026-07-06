<script lang="ts">
	// @ts-nocheck
	import { buildSourceHighlightedHtml, buildTiptapSnapshotHtml } from '$lib/utils/source-highlights';

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

<div class="prose prose-sm max-w-none whitespace-pre-wrap leading-7 break-words">
	{@html highlighted}
</div>
