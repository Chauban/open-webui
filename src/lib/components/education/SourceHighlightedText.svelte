<script lang="ts">
	// @ts-nocheck
	export let text = '';
	export let segments: Array<{
		segment_text: string;
		source_type: string;
	}> = [];

	const colorClass = (sourceType: string) => {
		if (sourceType === 'ai_inserted') return 'bg-amber-100 text-amber-950';
		if (sourceType === 'ai_pasted') return 'bg-sky-100 text-sky-950';
		return 'bg-emerald-100 text-emerald-950';
	};

	$: highlighted = (() => {
		if (!text) return '';

		let output = text
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('\n', '<br />');

		for (const segment of segments) {
			if (!segment.segment_text) continue;
			const safeText = segment.segment_text
				.replaceAll('&', '&amp;')
				.replaceAll('<', '&lt;')
				.replaceAll('>', '&gt;')
				.replaceAll('\n', '<br />');
			if (!output.includes(safeText)) continue;
			output = output.replace(
				safeText,
				`<mark class="rounded px-1 ${colorClass(segment.source_type)}">${safeText}</mark>`
			);
		}

		return output;
	})();
</script>

<div class="prose prose-sm max-w-none whitespace-pre-wrap leading-7 break-words">
	{@html highlighted}
</div>
