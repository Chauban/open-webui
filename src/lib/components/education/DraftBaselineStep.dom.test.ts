// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const submitDraftBaseline = vi.fn();
const extractImportDocument = vi.fn();
const extractImportImages = vi.fn();
vi.mock('$lib/apis/education', () => ({
	submitDraftBaseline: (...args: unknown[]) => submitDraftBaseline(...args),
	extractImportDocument: (...args: unknown[]) => extractImportDocument(...args),
	extractImportImages: (...args: unknown[]) => extractImportImages(...args)
}));
// 学生端是否提供「从图片导入」看 /api/config 的 features。
const { config } = vi.hoisted(() => {
	// vi.mock 的工厂先于 import 执行,这里手写一个最小的 store。
	type Value = { features: { enable_education_draft_image_import: boolean } };
	let value: Value = { features: { enable_education_draft_image_import: true } };
	const subscribers = new Set<(value: Value) => void>();
	return {
		config: {
			subscribe(run: (value: Value) => void) {
				subscribers.add(run);
				run(value);
				return () => subscribers.delete(run);
			},
			set(next: Value) {
				value = next;
				subscribers.forEach((run) => run(value));
			}
		}
	};
});
vi.mock('$lib/stores', () => ({ config }));
// PDF 在浏览器里读;这里替换掉 pdf.js 那一层,只测读出来之后的流程。
const readPdf = vi.fn();
vi.mock('$lib/utils/pdf-import', () => ({
	readPdf: (...args: unknown[]) => readPdf(...args),
	PdfImportError: class PdfImportError extends Error {}
}));

import DraftBaselineStep from './DraftBaselineStep.svelte';

afterEach(() => {
	cleanup();
	submitDraftBaseline.mockReset();
	extractImportDocument.mockReset();
	extractImportImages.mockReset();
	readPdf.mockReset();
	config.set({ features: { enable_education_draft_image_import: true } });
});
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('初稿不足 200 字(不计空白)时不能确认,够了才提交并通知外层刷新', async () => {
	const onSubmitted = vi.fn();
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted }, context });

	const button = screen.getByText('Confirm this is my first draft').closest('button')!;
	const textarea = screen.getByPlaceholderText('Paste your first draft here, or drop a file in');

	// 199 个字加一堆空白,仍然不够
	await fireEvent.input(textarea, { target: { value: `${'字'.repeat(199)}   \n\n  ` } });
	expect(button.disabled).toBe(true);

	const draft = `${'字'.repeat(100)}\n\n${'字'.repeat(100)}`;
	await fireEvent.input(textarea, { target: { value: draft } });
	expect(button.disabled).toBe(false);

	await fireEvent.click(button);
	await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
	expect(submitDraftBaseline).toHaveBeenCalledWith(undefined, 'session-1', draft);
});

test('上传的文件解析成正文填进框里,学生核对后再确认', async () => {
	const draft = '字'.repeat(250);
	extractImportDocument.mockResolvedValue({ text: draft });
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const file = new File(['docx bytes'], '初稿.docx');
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [file] } });

	const textarea = screen.getByPlaceholderText(
		'Paste your first draft here, or drop a file in'
	) as HTMLTextAreaElement;
	await waitFor(() => expect(textarea.value).toBe(draft));
	expect(extractImportDocument).toHaveBeenCalledWith(undefined, 'session-1', file);
	// 只是填进框里,还没有交
	expect(submitDraftBaseline).not.toHaveBeenCalled();
});

test('初稿照片按文件名排页序交给识图,结果填进框里等学生核对', async () => {
	const draft = '照片里的初稿。'.repeat(40);
	extractImportImages.mockResolvedValue({ text: draft });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const page10 = new File(['b'], 'IMG_10.jpg', { type: 'image/jpeg' });
	const page9 = new File(['a'], 'IMG_9.jpg', { type: 'image/jpeg' });
	await fireEvent.change(screen.getByTestId('draft-image-input'), {
		target: { files: [page10, page9] }
	});

	const textarea = screen.getByPlaceholderText(
		'Paste your first draft here, or drop a file in'
	) as HTMLTextAreaElement;
	await waitFor(() => expect(textarea.value).toBe(draft));
	expect(extractImportImages).toHaveBeenCalledWith(undefined, 'session-1', [page9, page10]);
	expect(submitDraftBaseline).not.toHaveBeenCalled();
});

test('管理员没选识图模型时,图片导入按钮不可用并说明原因', async () => {
	config.set({ features: { enable_education_draft_image_import: false } });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const button = screen.getByText('Import from images').closest('button')!;
	expect(button.disabled).toBe(true);
	expect(screen.getByTestId('image-import-unavailable')).toBeTruthy();
	expect(screen.getByText('Import from file').closest('button')!.disabled).toBe(false);
});

test('一次超过 8 张照片在前端就拦下,不上传', async () => {
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	const files = Array.from(
		{ length: 9 },
		(_, index) => new File(['x'], `${index}.jpg`, { type: 'image/jpeg' })
	);
	await fireEvent.change(screen.getByTestId('draft-image-input'), { target: { files } });
	expect(extractImportImages).not.toHaveBeenCalled();
});

const pdfLine = (text: string, y: number) => ({
	text,
	left: 72,
	right: 520,
	y,
	size: 11,
	leadingSpaces: false
});

test('PDF 在浏览器里读:文字页直接取字,扫描页交给识图,按原页序填回', async () => {
	const scan = new File(['jpeg'], '初稿-p002.jpg', { type: 'image/jpeg' });
	readPdf.mockResolvedValue([
		{ kind: 'text', lines: [pdfLine('第一页写满了整行没有结束', 700)] },
		{ kind: 'scan', pageNumber: 2, image: scan },
		{ kind: 'blank' },
		{ kind: 'text', lines: [pdfLine('第三页另起一段。', 700)] }
	]);
	extractImportImages.mockResolvedValue({ text: '扫描页的字。', pages: ['扫描页的字。'] });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const pdf = new File(['%PDF'], '初稿.pdf', { type: 'application/pdf' });
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [pdf] } });

	const textarea = screen.getByPlaceholderText(
		'Paste your first draft here, or drop a file in'
	) as HTMLTextAreaElement;
	await waitFor(() =>
		expect(textarea.value).toBe('第一页写满了整行没有结束\n扫描页的字。\n第三页另起一段。')
	);
	expect(readPdf).toHaveBeenCalledWith(pdf, expect.objectContaining({ renderScans: true }));
	expect(extractImportImages).toHaveBeenCalledWith(undefined, 'session-1', [scan]);
	// PDF 不交给后端的文档解析
	expect(extractImportDocument).not.toHaveBeenCalled();
});

test('没开图片导入时,PDF 只取文字页,扫描页跳过不渲染', async () => {
	config.set({ features: { enable_education_draft_image_import: false } });
	readPdf.mockResolvedValue([
		{ kind: 'text', lines: [pdfLine('只有这一页有文字。', 700)] },
		{ kind: 'scan', pageNumber: 2, image: null }
	]);
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const pdf = new File(['%PDF'], '初稿.pdf', { type: 'application/pdf' });
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [pdf] } });

	const textarea = screen.getByPlaceholderText(
		'Paste your first draft here, or drop a file in'
	) as HTMLTextAreaElement;
	await waitFor(() => expect(textarea.value).toBe('只有这一页有文字。'));
	expect(readPdf).toHaveBeenCalledWith(pdf, expect.objectContaining({ renderScans: false }));
	expect(extractImportImages).not.toHaveBeenCalled();
});

test('扫描页超过 8 页时不调识图,也不填框', async () => {
	readPdf.mockResolvedValue(
		Array.from({ length: 9 }, (_, index) => ({
			kind: 'scan',
			pageNumber: index + 1,
			image: new File(['jpeg'], `p${index}.jpg`, { type: 'image/jpeg' })
		}))
	);
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	const pdf = new File(['%PDF'], '扫描.pdf', { type: 'application/pdf' });
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [pdf] } });
	await waitFor(() => expect(readPdf).toHaveBeenCalled());
	expect(extractImportImages).not.toHaveBeenCalled();
	expect(
		(
			screen.getByPlaceholderText(
				'Paste your first draft here, or drop a file in'
			) as HTMLTextAreaElement
		).value
	).toBe('');
});
