// 作业写作区的「导入文件 / 导入图片」:修订初稿交初稿、从零写作往编辑器里插正文共用。
// 上限与后端 services/education/draft_import.py、writing_context.py 一致,前端先拦一遍,
// 免得学生等完上传才被拒;提示文案沿用后端的 i18n 键。

// PDF 在浏览器里读(pdf-import.ts),其余文档交给后端解析。
export const DOCUMENT_ACCEPT = '.docx,.doc,.txt,.md,.pdf,application/pdf';
// 只收模型和 Pillow 都认的三种。iPhone 的 HEIC 照片在 accept 里不列 heic 时,浏览器会转成 JPEG 再交上来。
export const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp';
export const IMAGE_MAX_COUNT = 8;
export const IMAGE_MAX_BYTES = 10 * 1024 * 1024;
export const IMAGE_TOTAL_MAX_BYTES = 30 * 1024 * 1024;

export type ImportKind = 'document' | 'images';
// scannedPages:读 PDF 时有几页扫描页交给了识图模型(kind 因此是 images)。
export type ImportInfo = { kind: ImportKind; names: string[]; scannedPages?: number };

const IMAGE_NAME = /\.(jpe?g|png|webp|heic|heif)$/i;

export const isPdfFile = (file: File) =>
	file.type === 'application/pdf' || /\.pdf$/i.test(file.name);

export const isImageFile = (file: File) =>
	file.type.startsWith('image/') || IMAGE_NAME.test(file.name);

/**
 * 多张照片按文件名排页序(IMG_9 在 IMG_10 前面);同名(手机相册常见的 image.jpg)保持选择顺序。
 */
export const sortImageFiles = (files: File[]) =>
	[...files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));

/** 返回第一条不满足上限的提示(i18n 键),都满足返回 null。 */
export const checkImageFiles = (files: File[]): string | null => {
	if (files.length === 0) return 'Choose at least one image';
	if (files.length > IMAGE_MAX_COUNT) return 'Upload at most 8 images at a time';
	if (files.some((file) => file.size > IMAGE_MAX_BYTES)) {
		return 'Each image must be 10 MB or smaller';
	}
	const total = files.reduce((sum, file) => sum + file.size, 0);
	if (total > IMAGE_TOTAL_MAX_BYTES) return 'The images add up to more than 30 MB';
	return null;
};

const escapeHtml = (value: string) =>
	value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/**
 * 导入结果(一段一行的纯文本)→ 编辑器段落。按纯文本处理,不把 .md 里的符号解析成格式:
 * 与初稿基线一样逐段对得上编辑器的 getText({blockSeparator:'\n'})。
 */
export const importedTextToHtml = (text: string) =>
	text
		.split('\n')
		.map((line) => line.trim())
		.filter(Boolean)
		.map((line) => `<p>${escapeHtml(line)}</p>`)
		.join('');

// 上传前在浏览器里先把照片缩到长边 2048:手机原图三五兆一张,8 张在校园网或流量下光上传
// 就要十几二十秒。服务端还会再转一次(长边 1600 交给模型),这里只为少传,留些余量。
export const UPLOAD_MAX_EDGE = 2048;
export const UPLOAD_JPEG_QUALITY = 0.9;
// 本来就小的图原样上传,不白白多压一次。
const UPLOAD_KEEP_BYTES = 1.5 * 1024 * 1024;
const SHRINKABLE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * 把一张照片缩小再上传;读不了(如 Chrome 打不开 HEIC)或缩完反而更大时原样返回,
 * 由服务端照常校验。按 EXIF 摆正后再画,透明底铺白(JPEG 没有透明,不铺会变黑底)。
 */
export const shrinkImageForUpload = async (file: File): Promise<File> => {
	if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file;
	if (!SHRINKABLE_TYPES.includes(file.type)) return file;
	let bitmap: ImageBitmap | null = null;
	try {
		bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
		const scale = Math.min(1, UPLOAD_MAX_EDGE / Math.max(bitmap.width, bitmap.height));
		if (scale === 1 && file.size <= UPLOAD_KEEP_BYTES) return file;
		const canvas = document.createElement('canvas');
		canvas.width = Math.round(bitmap.width * scale);
		canvas.height = Math.round(bitmap.height * scale);
		const context = canvas.getContext('2d');
		if (!context) return file;
		context.fillStyle = '#ffffff';
		context.fillRect(0, 0, canvas.width, canvas.height);
		context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
		const blob = await new Promise<Blob | null>((resolve) =>
			canvas.toBlob(resolve, 'image/jpeg', UPLOAD_JPEG_QUALITY)
		);
		if (!blob || blob.size >= file.size) return file;
		// 保留原文件名:页序按文件名排,弹窗和提示里也显示它。
		return new File([blob], file.name, { type: 'image/jpeg', lastModified: file.lastModified });
	} catch {
		return file;
	} finally {
		bitmap?.close();
	}
};
