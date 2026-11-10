// @vitest-environment jsdom
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/dom';
import { cleanup, render } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import WritingPaste from './test-fixtures/WritingPaste.svelte';
import { writingExtensions, writingAssetView } from './writing-document-extensions';
import { documentText, textDocument } from '$lib/utils/writing-document';
import { buildTiptapSnapshotHtml } from '$lib/utils/source-highlights';

const api = vi.hoisted(() => ({ getWritingMaterialAsset: vi.fn(), readWritingImage: vi.fn() }));
vi.mock('$lib/apis/education', async (original) => ({
	...(await original<typeof import('$lib/apis/education')>()),
	...api
}));
let editor: Editor;
let element: HTMLElement;
const figure = {
	type: 'writingImage',
	attrs: { materialId: 'file', blockId: 'm1', width: 70, transcription: '图片识别文字' },
	content: [{ type: 'text', text: '图一说明' }]
};
const document = () => ({
	type: 'doc',
	content: [textDocument('前文').content![0], figure, textDocument('后文').content![0]]
});
beforeEach(() => {
	api.getWritingMaterialAsset.mockResolvedValue(new Blob(['image']));
	URL.createObjectURL = vi.fn(() => 'blob:preview');
	URL.revokeObjectURL = vi.fn();
	element = globalThis.document.createElement('div');
	globalThis.document.body.append(element);
	editor = new Editor({
		element,
		extensions: [
			StarterKit,
			...writingExtensions({ t: (k) => k, sessionId: () => 'session', imageReading: () => true })
		],
		content: document()
	});
});
afterEach(() => {
	cleanup();
	editor.destroy();
	element.remove();
	vi.clearAllMocks();
});

test('粘贴图片先走文件核对，不提前给后续键入标记粘贴来源', async () => {
	const onImportFiles = vi.fn();
	const onProsePaste = vi.fn();
	const rendered = render(WritingPaste, {
		props: { onImportFiles, onProsePaste },
		context: new Map([['i18n', readable({ t: (key: string) => key })]])
	});
	await waitFor(() =>
		expect(rendered.container.querySelector('.tiptap')?.textContent).toBe('已有正文')
	);
	const file = new File(['image'], 'photo.png', { type: 'image/png' });
	await fireEvent.paste(rendered.container.querySelector('.tiptap')!, {
		clipboardData: { files: [file], items: [], getData: () => '' }
	});
	expect(onImportFiles).toHaveBeenCalledWith([file], 'paste');
	expect(onProsePaste).not.toHaveBeenCalled();
	expect(rendered.container.querySelector('.tiptap')?.textContent).toBe('已有正文');
});

test('真实编辑器保留图文位置，纯文字投影不包含识别结果', async () => {
	await waitFor(() => expect(element.querySelector('img')?.src).toBe('blob:preview'));
	expect(editor.getJSON().content?.map((n) => n.type)).toEqual([
		'paragraph',
		'writingImage',
		'paragraph'
	]);
	expect(documentText(editor.getJSON() as any)).toBe('前文\n图一说明\n后文');
	expect(element.querySelector('figcaption')?.textContent).toBe('图一说明');
});

test('移动图片携带图注，撤销恢复完整顺序', async () => {
	const move = [...element.querySelectorAll('button')].find((b) => b.textContent === '下移')!;
	await fireEvent.click(move);
	expect(
		editor
			.getJSON()
			.content?.slice(0, 3)
			.map((n) => n.type)
	).toEqual(['paragraph', 'paragraph', 'writingImage']);
	expect(editor.getJSON().content?.[2].content?.[0]).toMatchObject({ text: '图一说明' });
	editor.commands.undo();
	expect(editor.getJSON().content?.[1].type).toBe('writingImage');
});

test('富文本复制保留图片资源引用和图注', () => {
	const html = editor.getHTML();
	editor.commands.setContent(html);
	const image = editor.getJSON().content?.find((node) => node.type === 'writingImage');
	expect(image?.attrs?.materialId).toBe('file');
	expect(image?.attrs?.width).toBe(70);
	expect(image?.content?.[0]).toMatchObject({ text: '图一说明' });
});

test('图片宽度修改是文档事务，删除和撤销不会遗失资产引用', async () => {
	await fireEvent.change(element.querySelector('select')!, { target: { value: '40' } });
	expect(editor.getJSON().content?.[1].attrs?.width).toBe(40);
	await fireEvent.click(
		[...element.querySelectorAll('button')].find((b) => b.textContent === '删除图片')!
	);
	expect(editor.getJSON().content?.some((n) => n.type === 'writingImage')).toBe(false);
	editor.commands.undo();
	expect(editor.getJSON().content?.[1].attrs?.materialId).toBe('file');
});

test('图片识别结果只有明确插入才成为正文', async () => {
	const before = documentText(editor.getJSON() as any);
	await fireEvent.change(element.querySelector('textarea')!, { target: { value: '学生校对文字' } });
	expect(documentText(editor.getJSON() as any)).toBe(before);
	await fireEvent.click(
		[...element.querySelectorAll('button')].find((b) => b.textContent === '将这些文字插入正文')!
	);
	expect(documentText(editor.getJSON() as any)).toContain('学生校对文字');
});

test('只有图片的只读稿件也显示图片，并用提交权限下载资源', async () => {
	const output = globalThis.document.createElement('div');
	output.innerHTML = buildTiptapSnapshotHtml({
		json: { type: 'doc', content: [figure] },
		segments: []
	});
	const action = writingAssetView(output, { submissionId: 'submitted', t: (k) => k });
	await waitFor(() => expect(output.querySelector('img')?.src).toBe('blob:preview'));
	expect(api.getWritingMaterialAsset).toHaveBeenCalledWith(
		undefined,
		'file',
		'm1.jpg',
		'submitted'
	);
	action.destroy();
	expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview');
});
