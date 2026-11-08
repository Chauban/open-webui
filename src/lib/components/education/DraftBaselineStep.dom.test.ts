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
import DraftBaselineStep from './DraftBaselineStep.svelte';

afterEach(() => {
	cleanup();
	submitDraftBaseline.mockReset();
	extractImportDocument.mockReset();
	extractImportImages.mockReset();
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
	expect(submitDraftBaseline).toHaveBeenCalledWith(undefined, 'session-1', draft, []);
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

const material = {
	id: 'material-1',
	filename: '混排.pdf',
	model_id: null,
	blocks: [
		{
			id: 'm1',
			kind: 'page',
			location: '第 1 页',
			text: '',
			extracted_text: '',
			status: 'unreadable',
			detail: 'Some content could not be read',
			image: false
		}
	]
};

test('PDF 与 Word 使用同一后端导入，未识读材料持续显示并随初稿确认', async () => {
	config.set({ features: { enable_education_draft_image_import: false } });
	const draft = '正文'.repeat(120);
	extractImportDocument.mockResolvedValue({ text: draft, material: structuredClone(material) });
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	const pdf = new File(['%PDF'], '混排.pdf', { type: 'application/pdf' });
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [pdf] } });
	await waitFor(() =>
		expect(screen.getByRole('alert').textContent).toContain('could not be fully read')
	);
	expect(extractImportDocument).toHaveBeenCalledWith(undefined, 'session-1', pdf);
	expect(extractImportImages).not.toHaveBeenCalled();
	await fireEvent.input(screen.getByLabelText('Material text m1'), {
		target: { value: '截图来源：卷三第42页' }
	});
	await fireEvent.click(screen.getByText('Confirm this is my first draft').closest('button')!);
	await waitFor(() =>
		expect(submitDraftBaseline).toHaveBeenCalledWith(undefined, 'session-1', draft, [
			{ id: 'material-1', corrections: { m1: '截图来源：卷三第42页' } }
		])
	);
});

test('导入新文件替换预览时不携带上一文件的附件', async () => {
	extractImportDocument
		.mockResolvedValueOnce({ text: '正文'.repeat(120), material: structuredClone(material) })
		.mockResolvedValueOnce({ text: '新稿'.repeat(120) });
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	const input = screen.getByTestId('draft-file-input');
	await fireEvent.change(input, { target: { files: [new File(['x'], 'a.pdf')] } });
	await waitFor(() => expect(screen.getByLabelText('Material text m1')).toBeTruthy());
	await fireEvent.change(input, { target: { files: [new File(['x'], 'b.txt')] } });
	await waitFor(() => expect(screen.queryByLabelText('Material text m1')).toBeNull());
	await fireEvent.click(screen.getByText('Confirm this is my first draft').closest('button')!);
	await waitFor(() =>
		expect(submitDraftBaseline).toHaveBeenCalledWith(undefined, 'session-1', '新稿'.repeat(120), [])
	);
});

test('导入说明按需显示，支持聚焦和点击，不常驻占用正文高度', async () => {
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	const help = screen.getByRole('button', { name: 'Import help' });
	expect(screen.queryByRole('tooltip')).toBeNull();
	await fireEvent.focusIn(help);
	await waitFor(() => expect(screen.getByRole('tooltip').textContent).toContain('Supports .docx'));
	await fireEvent.focusOut(help);
	await fireEvent.click(help);
	await waitFor(() =>
		expect(screen.getByRole('tooltip').textContent).toContain('up to 8 at a time')
	);
});
