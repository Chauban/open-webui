// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import type { Editor } from '@tiptap/core';
import { closeHistory } from '@tiptap/pm/history';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import WritingEditor from './WritingEditor.svelte';
import { textDocument } from '$lib/utils/writing-document';

afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const browserHTML = (fragment: string) =>
	`<html>\r\n<body>\r\n<!--StartFragment-->${fragment}<!--EndFragment-->\r\n</body>\r\n</html>`;

async function start(text: string) {
	const onChange = vi.fn();
	const rendered = render(WritingEditor, {
		props: { value: textDocument(text), onChange },
		context
	});
	await waitFor(() => expect(rendered.container.querySelector('.tiptap')?.textContent).toBe(text));
	const surface = rendered.container.querySelector('.tiptap') as HTMLElement & { editor: Editor };
	return { surface, editor: surface.editor, onChange };
}

async function paste(surface: HTMLElement, html: string, text = '复制的文字') {
	await fireEvent.paste(surface, {
		clipboardData: {
			files: [],
			items: [],
			getData: (type: string) => ({ 'text/html': html, 'text/plain': text })[type] ?? ''
		}
	});
}

async function copy(surface: HTMLElement) {
	const data = new Map<string, string>();
	await fireEvent.copy(surface, {
		clipboardData: {
			clearData: () => data.clear(),
			setData: (type: string, value: string) => data.set(type, value)
		}
	});
	return data;
}

test('全选复制单段正文，在末尾连续粘贴不自动另起段落', async () => {
	const { surface, editor } = await start('第一行');
	editor.commands.selectAll();
	const data = await copy(surface);
	editor.commands.setTextSelection(editor.state.doc.content.size - 1);
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	expect(editor.getText({ blockSeparator: '\n' })).toBe('第一行第一行第一行');
	expect(editor.state.doc.childCount).toBe(1);
});

test('全选复制后直接粘贴替换自己，段落和格式保持不变', async () => {
	const { surface, editor } = await start('第一行');
	editor.commands.setContent('<p><strong>第一行</strong><br>第二行</p><p></p><p>第三行</p>');
	const before = editor.getJSON();
	editor.commands.selectAll();
	const data = await copy(surface);
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	expect(editor.getJSON()).toEqual(before);
});

test('全选多段正文插入句中，只保留原稿已有的空段和软换行', async () => {
	const { surface, editor } = await start('原稿');
	editor.commands.setContent('<p><strong>甲</strong><br>乙</p><p></p><p>丙</p>');
	editor.commands.selectAll();
	const data = await copy(surface);
	editor.commands.setContent('<p>前后</p>');
	editor.commands.setTextSelection(2);
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	expect(editor.getText({ blockSeparator: '\n' })).toBe('前甲\n乙\n\n丙后');
	expect(surface.querySelector('strong')?.textContent).toBe('甲');
	expect(editor.state.selection.from).toBe(editor.state.doc.content.size - 2);
});

test('全选复制标题仍保留标题块，不把结构化内容当作普通段落拼接', async () => {
	const { surface, editor } = await start('原稿');
	editor.commands.setContent('<h2>标题</h2><p>标题后的正文</p>');
	editor.commands.selectAll();
	const data = await copy(surface);
	editor.commands.setContent('<p>前文</p>');
	editor.commands.setTextSelection(3);
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	expect(editor.state.doc.childCount).toBe(3);
	expect(editor.state.doc.child(1).type.name).toBe('heading');
	expect(editor.state.doc.child(1).attrs.level).toBe(2);
	expect(editor.getText({ blockSeparator: '\n' })).toBe('前文\n标题\n标题后的正文');
});

test('带浏览器包装和对齐格式的粘贴保留首行，不把 HTML 换行插入正文', async () => {
	const { surface, editor } = await start('原来的第一行');
	editor.commands.setTextSelection(editor.state.doc.content.size - 1);
	editor.commands.splitBlock();
	editor.view.dispatch(closeHistory(editor.state.tr));
	const before = editor.getJSON();
	const html = browserHTML('<p style="text-align: start">复制的文字</p>');
	await paste(surface, html);
	expect(editor.getText({ blockSeparator: '\n' })).toBe('原来的第一行\n复制的文字');
	expect(editor.state.doc.childCount).toBe(2);
	editor.commands.undo();
	// The paste is a distinct history event from the preceding line break.
	expect(editor.getJSON()).toEqual(before);
});

test('格式简化仍按剪贴板片段替换选区，保留两侧文字并把光标放在粘贴末尾', async () => {
	const { surface, editor } = await start('前文待替换后文');
	editor.commands.setTextSelection({ from: 3, to: 6 });
	await paste(
		surface,
		browserHTML('<p data-pm-slice="1 1 []"><a href="#note">新文字</a></p>'),
		'新文字'
	);
	expect(editor.getText()).toBe('前文新文字后文');
	expect(editor.state.doc.childCount).toBe(1);
	expect(editor.state.selection.from).toBe(6);
	expect(editor.state.selection.empty).toBe(true);
});

test('移除外部图片时文字沿用同一粘贴解析流程，不产生额外空行', async () => {
	const { surface, editor } = await start('原文');
	editor.commands.setTextSelection(3);
	await paste(
		surface,
		browserHTML('<p>图旁文字<img src="https://example.org/photo.png"></p>'),
		'图旁文字'
	);
	expect(editor.getText()).toBe('原文图旁文字');
	expect(editor.state.doc.childCount).toBe(1);
	expect(surface.querySelector('img')).toBeNull();
});

test('复制第一行再多次粘贴只插入选中的文字，保留原文和主动输入的换行', async () => {
	const { surface, editor } = await start('第一行');
	editor.commands.setTextSelection({ from: 1, to: 4 });
	const data = await copy(surface);
	expect(data.get('text/plain')).toBe('第一行');
	expect(editor.getText()).toBe('第一行');
	editor.commands.setTextSelection(4);
	editor.commands.splitBlock();
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	await paste(surface, data.get('text/html')!, data.get('text/plain'));
	expect(editor.getText({ blockSeparator: '\n' })).toBe('第一行\n第一行第一行');
	expect(editor.state.doc.childCount).toBe(2);
});

test('保留正文自身的空段、软换行和加粗，HTML 包装空白不进入稿件', async () => {
	const { surface, editor } = await start('已有正文');
	editor.commands.selectAll();
	await paste(
		surface,
		browserHTML(
			'<p style="text-align:start"><strong>第一行</strong><br>第二行</p><p></p><p>第三行</p>'
		),
		'第一行\n第二行\n\n第三行'
	);
	expect(editor.getText({ blockSeparator: '\n' })).toBe('第一行\n第二行\n\n第三行');
	expect(editor.state.doc.childCount).toBe(3);
	expect(surface.querySelector('strong')?.textContent).toBe('第一行');
	expect(editor.state.doc.firstChild?.attrs.textAlign).toBe('left');
});

test('只有无法导入的外部图片时不删除选中的原文', async () => {
	const { surface, editor, onChange } = await start('原文必须保留');
	editor.commands.selectAll();
	onChange.mockClear();
	await paste(surface, browserHTML('<img src="https://example.org/photo.png">'), '');
	expect(editor.getText()).toBe('原文必须保留');
	expect(onChange.mock.calls.some(([change]) => change.docChanged)).toBe(false);
});
