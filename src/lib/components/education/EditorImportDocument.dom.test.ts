// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import { textDocument, documentText } from '$lib/utils/writing-document';
const api = vi.hoisted(() => ({
	extractImportDocument: vi.fn(),
	extractImportImages: vi.fn(),
	getWritingMaterialAsset: vi.fn()
}));
vi.mock('$lib/apis/education', async (original) => ({
	...(await original<typeof import('$lib/apis/education')>()),
	...api
}));
vi.mock('focus-trap', () => ({
	createFocusTrap: () => ({ activate() {}, deactivate() {}, pause() {}, unpause() {} })
}));
import EditorImportDialog from './EditorImportDialog.svelte';
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

test('预览中粘贴图片保留已经核对的文字，确认时携带两份来源', async () => {
	URL.createObjectURL = vi.fn(() => 'blob:image');
	URL.revokeObjectURL = vi.fn();
	const original = { id: 'word', filename: 'draft.docx', blocks: [] };
	const photo = { id: 'photo', filename: 'photo.png', blocks: [] };
	api.extractImportDocument.mockResolvedValue({
		text: '已经核对的文字',
		content_json: textDocument('已经核对的文字'),
		material: original
	});
	api.extractImportImages.mockResolvedValue({
		text: '',
		materials: [photo],
		content_json: {
			type: 'doc',
			content: [{ type: 'writingImage', attrs: { materialId: 'photo', blockId: 'm1' } }]
		}
	});
	api.getWritingMaterialAsset.mockResolvedValue(new Blob(['image']));
	const onInsert = vi.fn();
	const rendered = render(EditorImportDialog, {
		props: { show: true, sessionId: 'session', hasContent: false, onInsert },
		context: new Map([['i18n', readable({ t: (key: string) => key })]])
	});
	await fireEvent.change(screen.getByTestId('draft-upload-input'), {
		target: { files: [new File(['word'], 'draft.docx')] }
	});
	const body = rendered.container.ownerDocument.querySelector('.tiptap')!;
	await waitFor(() => expect(body.textContent).toContain('已经核对的文字'));
	await fireEvent.paste(body, {
		clipboardData: {
			files: [new File(['image'], 'photo.png', { type: 'image/png' })],
			items: [],
			getData: () => ''
		}
	});
	await fireEvent.click(screen.getByText('插入图片'));
	await waitFor(() => expect(body.querySelector('.writing-figure')).toBeTruthy());
	expect(body.textContent).toContain('已经核对的文字');
	await fireEvent.click(screen.getByText('Insert at cursor').closest('button')!);
	await waitFor(() => expect(onInsert).toHaveBeenCalledOnce());
	const info = onInsert.mock.calls[0][2];
	expect(documentText(info.document)).toContain('已经核对的文字');
	expect(info.materials.map((material) => material.id)).toEqual(['word', 'photo']);
});
