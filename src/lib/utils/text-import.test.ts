import { describe, expect, test } from 'vitest';

import { checkImageFiles, importedTextToHtml, isImageFile, sortImageFiles } from './text-import';

const file = (name: string, size = 1, type = '') => {
	const value = new File(['x'], name, { type });
	Object.defineProperty(value, 'size', { value: size });
	return value;
};

describe('text import', () => {
	test('导入的纯文本逐段转成编辑器段落,不解析成 HTML 或 Markdown', () => {
		expect(importedTextToHtml('　第一段 <b>不是粗体</b>\n\n# 不是标题 & 符号\n')).toBe(
			'<p>第一段 &lt;b&gt;不是粗体&lt;/b&gt;</p><p># 不是标题 &amp; 符号</p>'
		);
		expect(importedTextToHtml('  \n ')).toBe('');
	});

	test('照片按文件名的数字顺序排页,同名保持选择顺序', () => {
		const a = file('image.jpg');
		const b = file('image.jpg');
		const sorted = sortImageFiles([file('IMG_10.jpg'), file('IMG_9.jpg'), a, b]);
		expect(sorted.map((item) => item.name)).toEqual([
			'image.jpg',
			'image.jpg',
			'IMG_9.jpg',
			'IMG_10.jpg'
		]);
		expect(sorted[0]).toBe(a);
		expect(sorted[1]).toBe(b);
	});

	test('图片按类型或扩展名识别,数量与大小上限与后端一致', () => {
		expect(isImageFile(file('scan.PNG'))).toBe(true);
		expect(isImageFile(file('blob', 1, 'image/webp'))).toBe(true);
		expect(isImageFile(file('draft.docx'))).toBe(false);

		expect(checkImageFiles([])).toBe('Choose at least one image');
		expect(checkImageFiles(Array.from({ length: 9 }, () => file('a.jpg')))).toBe(
			'Upload at most 8 images at a time'
		);
		expect(checkImageFiles([file('a.jpg', 10 * 1024 * 1024 + 1)])).toBe(
			'Each image must be 10 MB or smaller'
		);
		expect(checkImageFiles(Array.from({ length: 4 }, () => file('a.jpg', 8 * 1024 * 1024)))).toBe(
			'The images add up to more than 30 MB'
		);
		expect(checkImageFiles([file('a.jpg', 5 * 1024 * 1024)])).toBeNull();
	});
});
