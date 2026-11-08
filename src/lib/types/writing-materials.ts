export type MaterialBlock = {
	id: string;
	kind: string;
	location: string;
	text: string;
	extracted_text: string;
	status: 'read' | 'unreadable' | 'corrected';
	detail: string;
	image: boolean;
};

export type WritingMaterial = {
	id: string;
	filename: string;
	model_id: string | null;
	blocks: MaterialBlock[];
};

export type MaterialSelection = { id: string; corrections: Record<string, string> };

export const selectMaterial = (material: WritingMaterial): MaterialSelection => ({
	id: material.id,
	corrections: Object.fromEntries(
		material.blocks
			.filter((block) => block.text !== block.extracted_text)
			.map((block) => [block.id, block.text])
	)
});
