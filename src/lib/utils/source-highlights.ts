type SourceSegment = {
	segment_id?: string;
	segment_text: string;
	source_type: string;
	start_offset?: number | null;
	end_offset?: number | null;
};

type HighlightRange = {
	start: number;
	end: number;
	segment: SourceSegment;
};

type TiptapNode = {
	type?: string;
	text?: string;
	attrs?: Record<string, any>;
	marks?: Array<{ type: string; attrs?: Record<string, any> }>;
	content?: TiptapNode[];
};

const escapeHtml = (value: string) => {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('\n', '<br />');
};

const escapeAttribute = (value: string) => {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('"', '&quot;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;');
};

const stripMarkdownFormatting = (value: string) => {
	return value
		.replace(/```[\s\S]*?```/g, (match) => match.replace(/```[a-z]*\n?|```/gi, ''))
		.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
		.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
		.replace(/(?:\*\*|__)(.*?)(?:\*\*|__)/g, '$1')
		.replace(/(?:[*_])(.*?)(?:[*_])/g, '$1')
		.replace(/~~(.*?)~~/g, '$1')
		.replace(/`([^`]+)`/g, '$1')
		.replace(/^#{1,6}\s+/gm, '')
		.replace(/^\s*[-*+]\s+/gm, '')
		.replace(/^\s*\d+\.\s+/gm, '')
		.trim();
};

const isLowSignalTypedSegment = (segment: SourceSegment) => {
	if (segment.source_type !== 'user_typed') return false;
	const text = stripMarkdownFormatting(segment.segment_text ?? '').trim();
	if (!text) return true;
	if (/^[A-Za-z]{1,3}$/.test(text)) return true;
	return text.length < 2;
};

const colorClass = (sourceType: string) => {
	if (sourceType === 'ai_inserted') return 'bg-amber-100 text-amber-950';
	if (sourceType === 'ai_pasted') return 'bg-sky-100 text-sky-950';
	if (sourceType === 'external_paste') return 'bg-rose-100 text-rose-950';
	if (sourceType === 'suspected_unmarked_import') return 'bg-rose-100 text-rose-950';
	if (sourceType === 'unknown') return 'bg-gray-100 text-gray-700';
	return 'bg-emerald-100 text-emerald-950';
};

const overlaps = (range: HighlightRange, ranges: HighlightRange[]) => {
	return ranges.some((existing) => range.start < existing.end && range.end > existing.start);
};

const findRange = (text: string, segment: SourceSegment, ranges: HighlightRange[]) => {
	const segmentText = segment.segment_text ?? '';
	if (!segmentText) return null;

	const hasValidOffsets =
		Number.isInteger(segment.start_offset) &&
		Number.isInteger(segment.end_offset) &&
		(segment.start_offset ?? -1) >= 0 &&
		(segment.end_offset ?? -1) > (segment.start_offset ?? -1) &&
		(segment.end_offset ?? 0) <= text.length;

	if (hasValidOffsets) {
		const start = segment.start_offset as number;
		const end = segment.end_offset as number;
		if (text.slice(start, end) === segmentText) {
			return { start, end, segment };
		}
	}

	let searchFrom = 0;
	while (searchFrom < text.length) {
		const start = text.indexOf(segmentText, searchFrom);
		if (start === -1) return null;
		const range = { start, end: start + segmentText.length, segment };
		if (!overlaps(range, ranges)) return range;
		searchFrom = start + 1;
	}

	return null;
};

export const buildSourceHighlightedHtml = ({
	text = '',
	segments = [],
	activeSegmentId = ''
}: {
	text: string;
	segments: SourceSegment[];
	activeSegmentId?: string;
}) => {
	if (!text) return '';

	const ranges: HighlightRange[] = [];
	for (const segment of segments) {
		const range = findRange(text, segment, ranges);
		if (range) {
			ranges.push(range);
		}
	}

	ranges.sort((left, right) => left.start - right.start || right.end - left.end);

	let cursor = 0;
	let html = '';
	for (const range of ranges) {
		if (range.start < cursor) continue;

		html += escapeHtml(text.slice(cursor, range.start));

		const segmentId = range.segment.segment_id ?? '';
		const activeClass =
			activeSegmentId && activeSegmentId === segmentId ? ' ring-2 ring-black/40' : '';
		html += `<mark data-segment-id="${escapeAttribute(segmentId)}" class="rounded px-1 ${colorClass(
			range.segment.source_type
		)}${activeClass}">${escapeHtml(text.slice(range.start, range.end))}</mark>`;
		cursor = range.end;
	}

	html += escapeHtml(text.slice(cursor));
	return html;
};

const WHITESPACE_RE = /\s+/g;

// Walk the Tiptap document once and produce (a) a plain-text reconstruction in
// document order and (b) the absolute [start, end) offset of every text node's
// contents inside that reconstruction. This mirrors ProseMirror's textBetween
// closely, but exact whitespace does not matter because matching is done on a
// whitespace-stripped copy (see buildWhitespaceIndex / findFuzzyRange).
const collectTiptapText = (root: TiptapNode | null | undefined) => {
	let text = '';
	let separated = true;
	const textNodes: Array<{ start: number; end: number }> = [];

	const isLeafType = (type?: string) =>
		type === 'hardBreak' || type === 'image' || type === 'horizontalRule';

	const visit = (node: TiptapNode | null | undefined) => {
		if (!node) return;
		const type = node.type;
		if (type === 'text') {
			const value = node.text ?? '';
			const start = text.length;
			text += value;
			textNodes.push({ start, end: text.length });
			separated = false;
		} else if (isLeafType(type)) {
			separated = false;
		} else if (!separated) {
			text += '\n';
			separated = true;
		}
		for (const child of node.content ?? []) visit(child);
	};

	visit(root);
	return { text, textNodes };
};

// Index of `text` with all whitespace removed, plus a map back to the original
// offsets. Matching against this makes highlighting immune to block-separator
// and line-break differences between the stored snapshot text (derived from
// editor.getText) and the reconstructed Tiptap text.
const buildWhitespaceIndex = (text: string) => {
	let stripped = '';
	const map: number[] = [];
	for (let index = 0; index < text.length; index += 1) {
		const char = text[index];
		if (!/\s/.test(char)) {
			stripped += char;
			map.push(index);
		}
	}
	return { stripped, map };
};

const findFuzzyRange = (
	index: { stripped: string; map: number[] },
	segment: SourceSegment,
	ranges: HighlightRange[]
): HighlightRange | null => {
	const rawNeedle = (segment.segment_text ?? '').replace(WHITESPACE_RE, '');
	const strippedNeedle = stripMarkdownFormatting(segment.segment_text ?? '').replace(WHITESPACE_RE, '');
	const needles = [...new Set([rawNeedle, strippedNeedle].filter(Boolean))];

	for (const needle of needles) {
		const candidates: HighlightRange[] = [];
		let from = 0;
		while (from <= index.stripped.length - needle.length) {
			const hit = index.stripped.indexOf(needle, from);
			if (hit === -1) break;
			const start = index.map[hit];
			const end = index.map[hit + needle.length - 1] + 1;
			const range = { start, end, segment };
			if (!overlaps(range, ranges)) candidates.push(range);
			from = hit + 1;
		}

		if (candidates.length === 0) continue;
		if (candidates.length === 1) return candidates[0];

		// Multiple identical occurrences: use the recorded offset to pick the right
		// one when available, otherwise fall back to the first free match.
		const target = segment.start_offset;
		if (Number.isInteger(target) && (target ?? -1) >= 0) {
			candidates.sort(
				(left, right) =>
					Math.abs(left.start - (target as number)) - Math.abs(right.start - (target as number))
			);
		}
		return candidates[0];
	}

	return null;
};

const markHtml = ({
	segment,
	content,
	activeSegmentId
}: {
	segment: SourceSegment;
	content: string;
	activeSegmentId: string;
}) => {
	const segmentId = segment.segment_id ?? '';
	const activeClass =
		activeSegmentId && activeSegmentId === segmentId ? ' ring-2 ring-black/40' : '';
	return `<mark data-segment-id="${escapeAttribute(segmentId)}" class="rounded px-1 ${colorClass(
		segment.source_type
	)}${activeClass}">${content}</mark>`;
};

const applyTextMarks = (
	html: string,
	marks: Array<{ type: string; attrs?: Record<string, any> }> = []
) => {
	return marks.reduce((value, mark) => {
		if (mark.type === 'bold') return `<strong>${value}</strong>`;
		if (mark.type === 'italic') return `<em>${value}</em>`;
		if (mark.type === 'strike') return `<s>${value}</s>`;
		if (mark.type === 'code') return `<code>${value}</code>`;
		if (mark.type === 'link') {
			return `<a href="${escapeAttribute(mark.attrs?.href ?? '')}" rel="noopener noreferrer">${value}</a>`;
		}
		return value;
	}, html);
};

const renderTextNode = (
	node: TiptapNode,
	ranges: HighlightRange[],
	state: { textIndex: number; offsets: Array<{ start: number; end: number }> },
	activeSegmentId: string
) => {
	const text = node.text ?? '';
	const offset = state.offsets[state.textIndex] ?? { start: 0, end: text.length };
	state.textIndex += 1;
	const start = offset.start;
	const end = offset.end;

	let localCursor = start;
	let html = '';
	const relevantRanges = ranges.filter((range) => range.start < end && range.end > start);

	for (const range of relevantRanges) {
		if (range.start > localCursor) {
			html += applyTextMarks(escapeHtml(text.slice(localCursor - start, range.start - start)), node.marks);
		}

		const chunkStart = Math.max(range.start, start);
		const chunkEnd = Math.min(range.end, end);
		const markedChunk = markHtml({
			segment: range.segment,
			content: escapeHtml(text.slice(chunkStart - start, chunkEnd - start)),
			activeSegmentId
		});
		html += applyTextMarks(markedChunk, node.marks);
		localCursor = chunkEnd;
	}

	if (localCursor < end) {
		html += applyTextMarks(escapeHtml(text.slice(localCursor - start)), node.marks);
	}

	return html;
};

const renderTiptapNode = (
	node: TiptapNode | null | undefined,
	ranges: HighlightRange[],
	state: { textIndex: number; offsets: Array<{ start: number; end: number }> },
	activeSegmentId: string
): string => {
	if (!node) return '';
	if (node.type === 'text') return renderTextNode(node, ranges, state, activeSegmentId);
	if (node.type === 'hardBreak') return '<br />';

	const children = (node.content ?? [])
		.map((child) => renderTiptapNode(child, ranges, state, activeSegmentId))
		.join('');

	if (node.type === 'paragraph') return `<p>${children}</p>`;
	if (node.type === 'heading') {
		const level = Math.min(Math.max(Number(node.attrs?.level ?? 1), 1), 6);
		return `<h${level}>${children}</h${level}>`;
	}
	if (node.type === 'orderedList') return `<ol>${children}</ol>`;
	if (node.type === 'bulletList') return `<ul>${children}</ul>`;
	if (node.type === 'listItem') return `<li>${children}</li>`;
	if (node.type === 'blockquote') return `<blockquote>${children}</blockquote>`;
	if (node.type === 'codeBlock') return `<pre><code>${children}</code></pre>`;

	return children;
};

export const buildTiptapSnapshotHtml = ({
	json,
	fallbackText = '',
	segments = [],
	activeSegmentId = ''
}: {
	json?: TiptapNode | null;
	fallbackText?: string;
	segments: SourceSegment[];
	activeSegmentId?: string;
}) => {
	if (!json) {
		return buildSourceHighlightedHtml({ text: fallbackText, segments, activeSegmentId });
	}

	const { text: visibleText, textNodes } = collectTiptapText(json);
	if (!visibleText.trim()) {
		return buildSourceHighlightedHtml({ text: fallbackText, segments, activeSegmentId });
	}

	const index = buildWhitespaceIndex(visibleText);
	const ranges: HighlightRange[] = [];
	for (const segment of segments) {
		if (isLowSignalTypedSegment(segment)) continue;
		const range = findFuzzyRange(index, segment, ranges);
		if (range) ranges.push(range);
	}
	ranges.sort((left, right) => left.start - right.start || right.end - left.end);

	return renderTiptapNode(json, ranges, { textIndex: 0, offsets: textNodes }, activeSegmentId);
};
