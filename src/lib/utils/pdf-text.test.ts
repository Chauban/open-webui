import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, test } from 'vitest';

import { buildPdfText, itemsToLines, joinText, removeRunningLines, type PdfLine } from './pdf-text';
import { pageHasImages, readPageLines } from './pdf-import';

const line = (text: string, y: number, extra: Partial<PdfLine> = {}): PdfLine => ({
	text,
	left: 72,
	right: 520,
	y,
	size: 11,
	leadingSpaces: false,
	...extra
});

describe('pdf text rebuilding', () => {
	test('中文行直接接上,西文补空格,行尾连字符去掉', () => {
		expect(joinText('城市更新研究逐渐', '转向社会过程')).toBe('城市更新研究逐渐转向社会过程');
		expect(joinText('community', 'participation')).toBe('community participation');
		expect(joinText('compare participa-', 'tion across')).toBe('compare participation across');
		expect(joinText('so-called', 'Smith')).toBe('so-called Smith');
	});

	test('片段按行尾标记和基线拼成行,行首两个空格算缩进', () => {
		const lines = itemsToLines([
			{ str: '  First', x: 72, y: 700, width: 40, size: 11, hasEOL: false },
			{ str: 'line', x: 118, y: 700, width: 20, size: 11, hasEOL: true },
			{ str: '', x: 72, y: 686, width: 0, size: 0, hasEOL: true },
			{ str: '第二行', x: 72, y: 686, width: 33, size: 11, hasEOL: false },
			{ str: '还在这一行', x: 105, y: 686, width: 55, size: 11, hasEOL: false },
			{ str: '换了基线', x: 72, y: 672, width: 44, size: 11, hasEOL: false }
		]);
		expect(lines.map((item) => [item.text, item.leadingSpaces])).toEqual([
			['First line', true],
			['第二行还在这一行', false],
			['换了基线', false]
		]);
	});

	test('每页最上、最下一行是页码或在多数页重复时去掉,正文不动', () => {
		const page = (number: number, first: string) => [
			line('城市更新研究', 780, { left: 270, right: 324 }),
			line(first, 700),
			line(`— ${number} —`, 30, { left: 285, right: 310 })
		];
		const cleaned = removeRunningLines([page(1, '正文甲'), page(2, '正文乙'), page(3, '正文丙')]);
		expect(cleaned.map((lines) => lines.map((item) => item.text))).toEqual([
			['正文甲'],
			['正文乙'],
			['正文丙']
		]);
		// 只有一页时,标题不会被当成页眉,但页码照样去掉
		expect(
			removeRunningLines([
				[line('标题', 780), line('正文。', 700), line('Page 1 of 1', 30)]
			])[0].map((item) => item.text)
		).toEqual(['标题', '正文。']);
	});

	test('段落:空行、缩进、提前收行都另起一段;没写完的段接到下一页', () => {
		const text = buildPdfText([
			{
				kind: 'text',
				lines: [
					line('题目', 760, { left: 250, right: 300 }),
					line('第一段第一行写满了整行', 720, { left: 94 }),
					line('第一段第二行没写满。', 706, { right: 300 }),
					line('第二段缩进开头写满了', 692, { left: 94 }),
					line('第二段写到页尾还没完', 678)
				]
			},
			{ kind: 'ocr', text: '' },
			{
				kind: 'text',
				lines: [
					line('接着上一页写完。', 760, { right: 200 }),
					line('第三段另起。', 720, { left: 94 })
				]
			},
			{ kind: 'ocr', text: '扫描页第一段\n\n扫描页第二段' }
		]);
		expect(text.split('\n')).toEqual([
			'题目',
			'第一段第一行写满了整行第一段第二行没写满。',
			'第二段缩进开头写满了第二段写到页尾还没完接着上一页写完。',
			'第三段另起。',
			'扫描页第一段',
			'扫描页第二段'
		]);
	});
});

// 下面用 pdf.js 的 Node 版(legacy)读真实 PDF,走与浏览器同一套 readPageLines / buildPdfText。
// 样本由 fixtures/make_pdfs.py 生成。
describe('pdf.js fixtures', () => {
	const load = async (name: string) => {
		const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
		const data = new Uint8Array(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)));
		const doc = await pdfjs.getDocument({
			data,
			cMapUrl: fileURLToPath(new URL('../../../node_modules/pdfjs-dist/cmaps/', import.meta.url)),
			cMapPacked: true,
			verbosity: 0
		}).promise;
		const pages = [];
		for (let number = 1; number <= doc.numPages; number += 1) {
			const page = await doc.getPage(number);
			pages.push({
				lines: await readPageLines(page as never),
				hasImages: await pageHasImages(pdfjs, page as never)
			});
		}
		await doc.destroy();
		return pages;
	};

	test('中文三页:去掉页眉和页码,段落还原,跨页的段接上', async () => {
		const pages = await load('zh_draft.pdf');
		const paragraphs = buildPdfText(
			pages.map((page) => ({ kind: 'text' as const, lines: page.lines }))
		).split('\n');
		expect(paragraphs[0]).toBe('社区参与的文献综述（初稿）');
		expect(paragraphs).toHaveLength(6);
		expect(paragraphs[1].startsWith('近二十年来')).toBe(true);
		expect(paragraphs[1].endsWith('成为讨论的核心议题之一。')).toBe(true);
		expect(paragraphs[2].startsWith('已有研究多以个案为主')).toBe(true);
		// 第三段从第一页写到第二页
		expect(paragraphs[3].startsWith('本文梳理了相关文献')).toBe(true);
		expect(paragraphs[3].endsWith('并指出现有研究的不足。')).toBe(true);
		expect(paragraphs[3]).toHaveLength(
			'本文梳理了相关文献，按参与主体、参与方式和参与效果三个维度进行归纳，并指出现有研究的不足。'
				.length * 18
		);
		expect(paragraphs.slice(4)).toEqual([
			'最后一段讨论未来研究的方向。',
			'第三页的内容从这里开始，说明研究方法。'
		]);
		expect(paragraphs.some((text) => text.includes('—'))).toBe(false);
	});

	test('英文:段间空行分段,行尾连字符接回', async () => {
		const pages = await load('en_draft.pdf');
		expect(
			buildPdfText(pages.map((page) => ({ kind: 'text' as const, lines: page.lines }))).split('\n')
		).toEqual([
			'Urban Renewal and Participation',
			'Community participation has become a central topic in urban renewal research over the past two decades, and many scholars have examined how residents take part in decision making.',
			'Existing studies are mostly single cases, and only a few of them try to compare participation across cities and outlines open questions.'
		]);
	});

	test('混合 PDF:文字页有字;扫描页没字但画了图;空白页两样都没有', async () => {
		const pages = await load('mixed.pdf');
		expect(pages.map((page) => [page.lines.length > 0, page.hasImages])).toEqual([
			[true, false],
			[false, true],
			[false, false]
		]);
	});
});
