// 作业写作区的「导入文件 / 导入图片」:修订初稿交初稿、从零写作往编辑器里插正文共用。
// 上限与后端 services/education/draft_import.py、writing_context.py 一致,前端先拦一遍,
// 免得学生等完上传才被拒;提示文案沿用后端的 i18n 键。

export const DOCUMENT_ACCEPT = '.docx,.doc,.txt,.md';
// 只收模型和 Pillow 都认的三种。iPhone 的 HEIC 照片在 accept 里不列 heic 时,浏览器会转成 JPEG 再交上来。
export const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp';
export const IMAGE_MAX_COUNT = 8;
export const IMAGE_MAX_BYTES = 10 * 1024 * 1024;
export const IMAGE_TOTAL_MAX_BYTES = 30 * 1024 * 1024;

export type ImportKind = 'document' | 'images';
export type ImportInfo = { kind: ImportKind; names: string[] };

const IMAGE_NAME = /\.(jpe?g|png|webp|heic|heif)$/i;

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
