// @vitest-environment jsdom
import { readFileSync, writeFileSync } from 'node:fs';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { TableKit } from '@tiptap/extension-table';
import { ListKit } from '@tiptap/extension-list';
import { expect, test, vi } from 'vitest';
import { writingExtensions } from './writing-document-extensions';
import { prepareWritingPaste } from '$lib/utils/writing-paste';
import { documentText } from '$lib/utils/writing-document';

vi.mock('$lib/apis/education', () => ({
	getWritingMaterialAsset: vi.fn(() => Promise.resolve(new Blob())),
	readWritingImage: vi.fn(),
	extractImportImages: vi.fn()
}));
const fixturePath = 'src/lib/utils/fixtures/writing-save-contract.json';
test('真实编辑器输出与后端保存接口共享格式契约，粘贴不丢文字、图片和脚注', () => {
	URL.createObjectURL = vi.fn(() => 'blob:fixture');
	URL.revokeObjectURL = vi.fn();
	const inputs = [
		{
			name: 'word-and-web',
			html: '<h2 style="text-align:start">标题</h2><p style="text-align:inherit">正文 <strong>加粗</strong> <em>斜体</em> <a href="#_ftn1">[1]</a></p><p dir="rtl" style="text-align:end">右向文字</p>'
		},
		{
			name: 'lists-and-table',
			html: '<ol start="3"><li><p>论点</p><ul><li>证据</li></ul></li></ol><table><tbody><tr><th>甲</th><th>乙</th></tr><tr><td colspan="2">内容</td></tr></tbody></table>'
		},
		{
			name: 'links-code-and-notes',
			html: '<p><a href="https://example.org/paper">文献</a> <a href="mailto:test@example.org" title="联系作者">邮箱</a> H<sub>2</sub>O <sup>2</sup></p><pre><code>line 1\nline 2</code></pre><hr>'
		},
		{
			name: 'image-and-footnote',
			document: {
				type: 'doc',
				content: [
					{
						type: 'paragraph',
						content: [
							{ type: 'text', text: '有脚注的正文' },
							{
								type: 'writingNote',
								attrs: {
									materialId: 'test-material',
									blockId: 'note',
									label: '1',
									note: '注释',
									kind: 'footnote'
								}
							}
						]
					},
					{
						type: 'writingImage',
						attrs: { materialId: 'test-material', blockId: 'image', width: 80 },
						content: [{ type: 'text', text: '图注' }]
					}
				]
			}
		}
	];
	const output = inputs.map((input) => {
		const element = document.createElement('div');
		const prepared = input.html ? prepareWritingPaste(input.html) : null;
		const editor = new Editor({
			element,
			extensions: [
				StarterKit.configure({
					bulletList: false,
					orderedList: false,
					listItem: false,
					listKeymap: false
				}),
				TableKit,
				ListKit.configure({ taskItem: { nested: true } }),
				...writingExtensions({
					t: (key) => key,
					sessionId: () => 'test-session',
					imageReading: () => false
				})
			],
			content: prepared?.html ?? input.document
		});
		const json = editor.getJSON();
		const result = { name: input.name, document: json, text: documentText(json as any) };
		if (input.name === 'word-and-web') {
			expect(prepared?.simplified).toBe(true);
			expect(result.text).toContain('正文 加粗 斜体 [1]');
			expect(json.content?.[0].attrs?.textAlign).toBe('left');
		}
		editor.destroy();
		return result;
	});
	if (process.env.UPDATE_WRITING_CONTRACT === '1')
		writeFileSync(fixturePath, JSON.stringify(output, null, 2) + '\n');
	else expect(output).toEqual(JSON.parse(readFileSync(fixturePath, 'utf8')));
});
