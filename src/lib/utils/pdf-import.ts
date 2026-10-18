// 在学生浏览器里读 PDF:不上传 PDF 本身,服务端也不解析 PDF。
// 有文字层的页直接取文字;几乎没有文字、却画了图片的页(扫描件)渲染成 JPEG,
// 交给与「从图片导入」同一条识图路径;既没字也没图的空白页跳过。
// pdf.js 按需加载(与 PDF 预览共用同一份),不进首屏包。

import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

import { UPLOAD_JPEG_QUALITY, UPLOAD_MAX_EDGE } from './text-import';
import { itemsToLines, type PdfLine, type PdfTextItem } from './pdf-text';

export const PDF_MAX_BYTES = 50 * 1024 * 1024;
// 一份初稿用不着更多页;防止误选整本书把浏览器卡住。
export const PDF_MAX_PAGES = 50;
// 一页去掉空白后不到这么多字、又画了图片,就当扫描页。页码、页眉之类的零星文字不算。
const SCANNED_MAX_CHARS = 10;
// pdf.js 的中日韩字符映射和标准字体,构建时从 pdfjs-dist 拷到这里(vite.config.ts),
// 只在 PDF 用到时才按需下载:有的中文 PDF 不带 ToUnicode 表,没有 CMap 就取不出字。
const CMAP_URL = '/pdfjs/cmaps/';
const STANDARD_FONT_URL = '/pdfjs/standard_fonts/';

export class PdfImportError extends Error {}

export type ReadPdfPage =
	| { kind: 'text'; lines: PdfLine[] }
	| { kind: 'scan'; pageNumber: number; image: File | null }
	| { kind: 'blank' };

type PdfJs = typeof import('pdfjs-dist');
type PdfPageProxy = import('pdfjs-dist').PDFPageProxy;

/** 一页的文字片段 → 行。导出给测试用:Node 里的 legacy 版 pdf.js 给出的页对象结构相同。 */
export const readPageLines = async (page: PdfPageProxy): Promise<PdfLine[]> => {
	const content = await page.getTextContent();
	const items: PdfTextItem[] = [];
	for (const item of content.items) {
		if (!('str' in item)) continue;
		const [, , c, d, x, y] = item.transform as number[];
		items.push({
			str: item.str,
			x,
			y,
			width: item.width,
			size: item.height || Math.hypot(c, d),
			hasEOL: item.hasEOL
		});
	}
	return itemsToLines(items);
};

export const pageHasImages = async (pdfjs: Pick<PdfJs, 'OPS'>, page: PdfPageProxy) => {
	const { fnArray } = await page.getOperatorList();
	const imageOps = new Set([
		pdfjs.OPS.paintImageXObject,
		pdfjs.OPS.paintInlineImageXObject,
		pdfjs.OPS.paintImageMaskXObject
	]);
	return fnArray.some((op) => imageOps.has(op));
};

/** 扫描页渲染成与「从图片导入」上传时同样规格的图:长边 1600、白底 JPEG 0.85。 */
const renderPage = async (page: PdfPageProxy, name: string): Promise<File | null> => {
	const base = page.getViewport({ scale: 1 });
	const viewport = page.getViewport({
		scale: UPLOAD_MAX_EDGE / Math.max(base.width, base.height)
	});
	const canvas = document.createElement('canvas');
	canvas.width = Math.floor(viewport.width);
	canvas.height = Math.floor(viewport.height);
	const context = canvas.getContext('2d');
	if (!context) return null;
	context.fillStyle = '#ffffff';
	context.fillRect(0, 0, canvas.width, canvas.height);
	await page.render({ canvas, canvasContext: context, viewport }).promise;
	const blob = await new Promise<Blob | null>((resolve) =>
		canvas.toBlob(resolve, 'image/jpeg', UPLOAD_JPEG_QUALITY)
	);
	canvas.width = 0;
	canvas.height = 0;
	return blob ? new File([blob], name, { type: 'image/jpeg' }) : null;
};

/**
 * 逐页读 PDF。renderScans=false 时扫描页只标出来、不渲染(管理员没开图片导入时用不上)。
 * 打不开、加了打开密码、页数太多时抛 PdfImportError,消息是 i18n 键。
 */
export const readPdf = async (
	file: File,
	{
		renderScans,
		onProgress
	}: { renderScans: boolean; onProgress?: (page: number, total: number) => void }
): Promise<ReadPdfPage[]> => {
	if (file.size > PDF_MAX_BYTES) throw new PdfImportError('The PDF must be 50 MB or smaller');
	const pdfjs = await import('pdfjs-dist');
	pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
	let doc: import('pdfjs-dist').PDFDocumentProxy;
	try {
		doc = await pdfjs.getDocument({
			data: new Uint8Array(await file.arrayBuffer()),
			cMapUrl: CMAP_URL,
			cMapPacked: true,
			standardFontDataUrl: STANDARD_FONT_URL,
			isEvalSupported: false
		}).promise;
	} catch (error) {
		if ((error as { name?: string })?.name === 'PasswordException') {
			throw new PdfImportError(
				'This PDF is password protected. Remove the password and try again.'
			);
		}
		throw new PdfImportError('Could not read this PDF');
	}
	try {
		if (doc.numPages > PDF_MAX_PAGES) {
			throw new PdfImportError('The PDF has more than 50 pages');
		}
		const stem = file.name.replace(/\.pdf$/i, '');
		const pages: ReadPdfPage[] = [];
		for (let number = 1; number <= doc.numPages; number += 1) {
			onProgress?.(number, doc.numPages);
			const page = await doc.getPage(number);
			const lines = await readPageLines(page);
			const chars = lines.reduce((sum, line) => sum + line.text.replace(/\s/g, '').length, 0);
			if (chars >= SCANNED_MAX_CHARS) {
				pages.push({ kind: 'text', lines });
			} else if (await pageHasImages(pdfjs, page)) {
				pages.push({
					kind: 'scan',
					pageNumber: number,
					// 文件名补页号:页序按文件名排,零填充免得第 10 页排到第 2 页前面。
					image: renderScans
						? await renderPage(page, `${stem}-p${String(number).padStart(3, '0')}.jpg`)
						: null
				});
			} else {
				pages.push(lines.length ? { kind: 'text', lines } : { kind: 'blank' });
			}
			page.cleanup();
		}
		return pages;
	} finally {
		void doc.destroy();
	}
};
