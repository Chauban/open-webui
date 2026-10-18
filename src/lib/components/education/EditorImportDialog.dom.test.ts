// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const extractImportDocument = vi.fn();
const extractImportImages = vi.fn();
vi.mock('$lib/apis/education', () => ({
	extractImportDocument: (...args: unknown[]) => extractImportDocument(...args),
	extractImportImages: (...args: unknown[]) => extractImportImages(...args)
}));
// jsdom 没有布局,focus-trap 找不到可聚焦元素会报错;弹窗的焦点管理不在这里测。
vi.mock('focus-trap', () => ({
	createFocusTrap: () => ({
		activate: () => {},
		deactivate: () => {},
		pause: () => {},
		unpause: () => {}
	})
}));
vi.mock('$lib/stores', () => ({
	config: readable({ features: { enable_education_draft_image_import: true } })
}));

import EditorImportDialog from './EditorImportDialog.svelte';

afterEach(() => {
	cleanup();
	extractImportDocument.mockReset();
	extractImportImages.mockReset();
});
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const importDocument = async (text: string) => {
	extractImportDocument.mockResolvedValue({ text });
	const file = new File(['docx bytes'], '提纲.docx');
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [file] } });
	const preview = screen.getByTestId('import-preview') as HTMLTextAreaElement;
	await waitFor(() => expect(preview.value).toBe(text));
	return preview;
};

test('导入的文字先进预览,学生可以改,再插到光标处', async () => {
	const onInsert = vi.fn();
	render(EditorImportDialog, {
		props: { show: true, sessionId: 'session-1', hasText: false, onInsert },
		context
	});
	const insertButton = screen.getByText('Insert at cursor').closest('button')!;
	expect(insertButton.disabled).toBe(true);

	const preview = await importDocument('第一段。\n第二段。');
	await fireEvent.input(preview, { target: { value: '第一段。\n改过的第二段。' } });
	await fireEvent.click(insertButton);

	expect(onInsert).toHaveBeenCalledWith('第一段。\n改过的第二段。', 'insert', {
		kind: 'document',
		names: ['提纲.docx']
	});
});

test('编辑器里已有正文时,替换全文要再点一次确认', async () => {
	const onInsert = vi.fn();
	render(EditorImportDialog, {
		props: { show: true, sessionId: 'session-1', hasText: true, onInsert },
		context
	});
	await importDocument('新的全文。');

	await fireEvent.click(screen.getByText('Replace all text').closest('button')!);
	expect(onInsert).not.toHaveBeenCalled();
	expect(
		screen.getByText('This replaces everything you have written so far. Click again to confirm.')
	).toBeTruthy();

	await fireEvent.click(screen.getByText('Confirm replacing all text').closest('button')!);
	expect(onInsert).toHaveBeenCalledWith('新的全文。', 'replace', {
		kind: 'document',
		names: ['提纲.docx']
	});
});
