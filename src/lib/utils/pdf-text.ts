// PDF 文字层 → 一段一行的纯文本(与导入 Word 文件的结果同一形式)。纯函数,不依赖 pdf.js:
// pdf-import.ts 负责在浏览器里读 PDF,把每页的文字片段交到这里拼成段落。
//
// PDF 里没有「段落」,只有一个个定位好的文字片段。这里按位置还原:
// 片段按行拼起来;两行之间空得比行距大、下一行缩进、或上一行没写到右边距,就算新起一段;
// 每页最上和最下一行若是页码、或在多数页上重复(页眉页脚),就丢掉;
// 上一页最后一段没写完(没到句末、也没提前收行)而下一页第一行不缩进,就接成一段。

export type PdfTextItem = {
	str: string;
	x: number;
	// PDF 坐标:y 是基线到页面底边的距离,越往下越小。
	y: number;
	width: number;
	// 字号;pdf.js 偶尔给 0,外面已按变换矩阵补上。
	size: number;
	hasEOL: boolean;
};

export type PdfLine = {
	text: string;
	left: number;
	right: number;
	y: number;
	size: number;
	// 行首有两个以上空格(有的 PDF 用空格而不是位移表示首行缩进)。
	leadingSpaces: boolean;
};

export type PdfPage =
	| { kind: 'text'; lines: PdfLine[] }
	// 扫描页交给识图模型转录后的结果(一段一行)。
	| { kind: 'ocr'; text: string };

const CJK = /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]/;
// 段末标点:句末、冒号、分号,连同收尾的引号括号。
const TERMINAL = /[。！？!?.…:：;；]["'”’」』）)\]]*$/;
const PAGE_NUMBER =
	/^(?:[-–—~·.\s]*(?:第\s*)?\d{1,4}\s*页?(?:\s*(?:\/|of|共)\s*\d{1,4}\s*页?)?[-–—~·.\s]*|page\s+\d{1,4}(?:\s+of\s+\d{1,4})?|(?=[ivxlc])(?:c[d]|d?c{0,3})(?:x[cl]|l?x{0,3})(?:i[xv]|v?i{0,3}))$/i;

const lastChar = (text: string) => text.charAt(text.length - 1);

/** 同一段里两行(或同一行里两个片段)怎么接:中文直接接,西文补空格,行尾连字符去掉。 */
export const joinText = (left: string, right: string) => {
	if (!left) return right;
	if (!right) return left;
	if (/[A-Za-z]-$/.test(left) && /^[a-z]/.test(right)) return left.slice(0, -1) + right;
	if (/\s$/.test(left) || /^\s/.test(right)) return left + right;
	if (CJK.test(lastChar(left)) || CJK.test(right.charAt(0))) return left + right;
	return `${left} ${right}`;
};

/** 片段 → 行:遇到行尾标记或基线明显变了就换行。 */
export const itemsToLines = (items: PdfTextItem[]): PdfLine[] => {
	const lines: PdfLine[] = [];
	let current: { raw: string; left: number; right: number; y: number; size: number } | null = null;

	const flush = () => {
		if (current) {
			const text = current.raw.trim();
			if (text) {
				lines.push({
					text,
					left: current.left,
					right: current.right,
					y: current.y,
					size: current.size,
					leadingSpaces: /^[\s\u3000]{2,}/.test(current.raw)
				});
			}
		}
		current = null;
	};

	for (const item of items) {
		if (item.str) {
			if (current && Math.abs(item.y - current.y) > Math.max(current.size, item.size) * 0.5) {
				flush();
			}
			if (!current) {
				current = {
					raw: item.str,
					left: item.x,
					right: item.x + item.width,
					y: item.y,
					size: item.size
				};
			} else {
				const gap = item.x - current.right;
				const spaced = gap > current.size * 0.2 ? joinText(current.raw, item.str) : null;
				current.raw = spaced ?? current.raw + item.str;
				current.right = Math.max(current.right, item.x + item.width);
				current.size = Math.max(current.size, item.size);
			}
		}
		if (item.hasEOL) flush();
	}
	flush();
	return lines;
};

const textKey = (text: string) => text.replace(/\d+/g, '#').replace(/\s+/g, '');

const extremes = (lines: PdfLine[]) => {
	if (lines.length === 0) return { top: null, bottom: null };
	let top = lines[0];
	let bottom = lines[0];
	for (const line of lines) {
		if (line.y > top.y) top = line;
		if (line.y < bottom.y) bottom = line;
	}
	return { top, bottom: bottom === top ? null : bottom };
};

/**
 * 去掉页码和页眉页脚:只看每页最上和最下一行。是页码就丢;同一行字(数字不计)在至少两页、
 * 且过半页面的同一位置出现,就当页眉页脚丢掉。正文第一行碰巧和别页一样的概率很小。
 */
export const removeRunningLines = (pages: PdfLine[][]): PdfLine[][] => {
	const counts = { top: new Map<string, number>(), bottom: new Map<string, number>() };
	const found = pages.map(extremes);
	for (const { top, bottom } of found) {
		if (top) counts.top.set(textKey(top.text), (counts.top.get(textKey(top.text)) ?? 0) + 1);
		if (bottom) {
			counts.bottom.set(textKey(bottom.text), (counts.bottom.get(textKey(bottom.text)) ?? 0) + 1);
		}
	}
	const threshold = Math.max(2, Math.ceil(pages.length / 2));
	const isRunning = (line: PdfLine | null, zone: Map<string, number>) =>
		!!line && (PAGE_NUMBER.test(line.text) || (zone.get(textKey(line.text)) ?? 0) >= threshold);

	return pages.map((lines, index) => {
		const { top, bottom } = found[index];
		const drop = new Set<PdfLine>();
		if (isRunning(top, counts.top)) drop.add(top!);
		if (isRunning(bottom, counts.bottom)) drop.add(bottom!);
		return lines.filter((line) => !drop.has(line));
	});
};

const percentile = (values: number[], ratio: number) => {
	if (values.length === 0) return 0;
	const sorted = [...values].sort((a, b) => a - b);
	return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))];
};

type Layout = { left: number; right: number; gap: number };

/** 全文的版心:左边距取多数行的起点,右边距取大多数整行的终点,行距取中位数。 */
const measureLayout = (pages: PdfLine[][]): Layout => {
	const lines = pages.flat();
	const gaps: number[] = [];
	for (const page of pages) {
		for (let i = 1; i < page.length; i += 1) {
			const gap = page[i - 1].y - page[i].y;
			if (gap > 0 && gap < page[i].size * 3) gaps.push(gap);
		}
	}
	return {
		left: percentile(
			lines.map((line) => line.left),
			0.2
		),
		right: percentile(
			lines.map((line) => line.right),
			0.9
		),
		gap: gaps.length ? percentile(gaps, 0.5) : 0
	};
};

type PageParagraphs = { paragraphs: string[]; startsNew: boolean; ended: boolean };

const toParagraphs = (lines: PdfLine[], layout: Layout): PageParagraphs => {
	if (lines.length === 0) return { paragraphs: [], startsNew: true, ended: true };
	const indented = (line: PdfLine) =>
		line.leadingSpaces || line.left > layout.left + line.size * 0.8;
	const short = (line: PdfLine) => line.right < layout.right - line.size * 2;
	const paragraphs: string[] = [lines[0].text];
	for (let i = 1; i < lines.length; i += 1) {
		const previous = lines[i - 1];
		const line = lines[i];
		const gap = previous.y - line.y;
		const limit = layout.gap ? layout.gap * 1.4 : line.size * 1.8;
		const breaks = gap <= 0 || gap > limit || indented(line) || short(previous);
		if (breaks) paragraphs.push(line.text);
		else paragraphs[paragraphs.length - 1] = joinText(paragraphs[paragraphs.length - 1], line.text);
	}
	const last = lines[lines.length - 1];
	return {
		paragraphs,
		startsNew: indented(lines[0]),
		ended: short(last) || TERMINAL.test(last.text)
	};
};

/** 各页(文字页与转录过的扫描页)按页序拼成一段一行的纯文本。 */
export const buildPdfText = (pages: PdfPage[]): string => {
	const textPages = pages.filter((page) => page.kind === 'text') as Array<{
		kind: 'text';
		lines: PdfLine[];
	}>;
	const cleaned = removeRunningLines(textPages.map((page) => page.lines));
	const layout = measureLayout(cleaned);
	const out: string[] = [];
	let previousEnded = true;
	let textIndex = 0;
	for (const page of pages) {
		if (page.kind === 'ocr') {
			const transcribed = page.text
				.split('\n')
				.map((line) => line.trim())
				.filter(Boolean);
			// 识图模型没读出字的页(空白扫描页)当它不存在,前后的段照常接续。
			if (transcribed.length === 0) continue;
			out.push(...transcribed);
			previousEnded = true;
			continue;
		}
		const { paragraphs, startsNew, ended } = toParagraphs(cleaned[textIndex], layout);
		textIndex += 1;
		if (paragraphs.length === 0) continue;
		const rest = [...paragraphs];
		if (!previousEnded && !startsNew && out.length > 0) {
			out[out.length - 1] = joinText(out[out.length - 1], rest.shift()!);
		}
		out.push(...rest);
		previousEnded = ended;
	}
	return out.join('\n');
};
