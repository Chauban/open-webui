export type WritingNode = {
	type: string;
	text?: string;
	attrs?: Record<string, any>;
	marks?: Array<{ type: string; attrs?: Record<string, any> }>;
	content?: WritingNode[];
};

export const textDocument = (text: string): WritingNode => ({
	type: 'doc',
	content: text.split('\n').map((line) => ({
		type: 'paragraph',
		content: line ? [{ type: 'text', text: line }] : []
	}))
});

export const documentText = (document: WritingNode): string => {
	const render = (node: WritingNode): string => {
		if (node.type === 'text') return node.text ?? '';
		if (node.type === 'hardBreak') return '\n';
		if (['writingNote', 'writingPlaceholder'].includes(node.type)) return '';
		return (node.content ?? [])
			.map(render)
			.join(['paragraph', 'heading', 'codeBlock', 'writingImage'].includes(node.type) ? '' : '\n');
	};
	return render(document).trim();
};

export const writingReferences = (node: WritingNode): WritingNode[] => [
	...(node.type.startsWith('writing') ? [node] : []),
	...(node.content ?? []).flatMap(writingReferences)
];

export const hasDocumentContent = (node: WritingNode) =>
	Boolean(documentText(node) || writingReferences(node).length);
