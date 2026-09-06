// @vitest-environment jsdom
import { render, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { describe, expect, test, vi } from 'vitest';
import RichTextInput from '$lib/components/common/RichTextInput.svelte';

// 写作工作区靠这两个标志判断「这次 onChange 是不是学生在改稿」。
// 判断错的代价见 f7ac3c140：整篇被记成一次删除、source map 被清空，
// 回填后又整体标成 user_typed，来源追踪和过程指标一起失真。
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

const doc = (text: string) => ({
	type: 'doc',
	content: [{ type: 'paragraph', content: [{ type: 'text', text }] }]
});

const emissions = (onChange: ReturnType<typeof vi.fn>) =>
	onChange.mock.calls.map(([change]) => ({
		docChanged: change.docChanged,
		programmatic: change.programmatic,
		text: change.text
	}));

describe('writing editor change emissions', () => {
	test('marks content the component itself pushes in, so it never reads as an edit', async () => {
		const onChange = vi.fn();
		const rendered = render(RichTextInput, {
			props: { value: null, json: true, editable: true, onChange },
			context
		});

		// 挂载时正文还没灌回来，编辑器是空文档 —— ProseMirror 照样报 docChanged。
		await waitFor(() => expect(onChange).toHaveBeenCalled());
		expect(emissions(onChange)).toEqual([{ docChanged: true, programmatic: true, text: '' }]);

		await rendered.rerender({ value: doc('已经写好的正文') });
		await waitFor(() => expect(emissions(onChange)).toHaveLength(2));
		expect(emissions(onChange)[1]).toEqual({
			docChanged: true,
			programmatic: true,
			text: '已经写好的正文'
		});
	});

	test('leaves transactions it did not cause unmarked, and reports selection-only ones as no-ops', async () => {
		const onChange = vi.fn();
		const rendered = render(RichTextInput, {
			props: { value: null, json: true, editable: true, onChange },
			context
		});
		await waitFor(() => expect(onChange).toHaveBeenCalled());
		await rendered.rerender({ value: doc('已经写好的正文') });
		await waitFor(() => expect(emissions(onChange)).toHaveLength(2));

		onChange.mockClear();
		await rendered.rerender({ value: doc('已经写好的正文'), editable: false });
		await waitFor(() => expect(onChange).toHaveBeenCalled());

		// 标志位用完即还原，否则后续真实编辑会被一起吞掉。
		expect(emissions(onChange).every(({ programmatic }) => programmatic === false)).toBe(true);
		// 选区/格式变化正文没动，由 docChanged 挡掉。
		expect(emissions(onChange).every(({ docChanged }) => docChanged === false)).toBe(true);
	});
});
