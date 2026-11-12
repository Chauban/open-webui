// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { textDocument } from '$lib/utils/writing-document';
import { createWritingBackup } from '$lib/utils/writing-backup';
const api = vi.hoisted(() => ({
	submitDraftBaseline: vi.fn(),
	extractImportDocument: vi.fn(),
	extractImportImages: vi.fn(),
	getPendingWritingDraft: vi.fn(),
	savePendingWritingDraft: vi.fn(),
	downloadWritingWord: vi.fn()
}));
vi.mock('$lib/apis/education', async (original) => ({
	...(await original<typeof import('$lib/apis/education')>()),
	...api
}));
vi.mock('./WritingEditor.svelte', () => import('./test-fixtures/WritingEditor.svelte'));
vi.mock('$lib/stores', () => ({
	user: readable({ id: 'student-1' }),
	config: readable({
		features: {
			enable_education_photo_transcription: true,
			enable_education_draft_image_import: true
		}
	})
}));
import DraftBaselineStep from './DraftBaselineStep.svelte';
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
beforeEach(() => {
	localStorage.clear();
	api.getPendingWritingDraft.mockResolvedValue({
		content_json: textDocument(''),
		materials: [],
		revision: 0
	});
	api.savePendingWritingDraft.mockResolvedValue({ revision: 1 });
	api.submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});
const start = async (imageReadingEnabled = false, photoTranscriptionEnabled = false) => {
	const onSubmitted = vi.fn();
	render(DraftBaselineStep, {
		props: { sessionId: 'session-1', imageReadingEnabled, photoTranscriptionEnabled, onSubmitted },
		context
	});
	await waitFor(() =>
		expect((screen.getByRole('button', { name: 'Upload' }) as HTMLButtonElement).disabled).toBe(
			false
		)
	);
	return onSubmitted;
};
const pick = async (files: File[]) =>
	fireEvent.change(screen.getByTestId('draft-upload-input'), { target: { files } });
const input = () => screen.getByTestId('workspace-editor') as HTMLTextAreaElement;

test('初稿输入同步备份，刷新后明确选择恢复，保存失败保留备份和原因', async () => {
	await start();
	const text = '尚未确认的初稿。'.repeat(30);
	await fireEvent.input(input(), { target: { value: text } });
	expect(createWritingBackup('student-1', 'session-1', 'baseline').list()[0].data.document).toEqual(
		textDocument(text)
	);
	cleanup();
	api.savePendingWritingDraft.mockRejectedValue({ status: 401 });
	await start();
	expect(input().value).toBe(JSON.stringify(textDocument('')));
	await fireEvent.click(screen.getByRole('button', { name: '恢复此稿并保存' }));
	await waitFor(
		() => expect(screen.getByText('登录已过期，请先保留稿件，再重新登录。')).toBeTruthy(),
		{ timeout: 2000 }
	);
	expect(input().value).toBe(JSON.stringify(textDocument(text)));
	expect(api.submitDraftBaseline).not.toHaveBeenCalled();
});
test('正文门槛不计空白，确认提交完整文档', async () => {
	const done = await start();
	await fireEvent.input(input(), { target: { value: '字'.repeat(199) + '  \n' } });
	expect((screen.getByText('Confirm this is my first draft') as HTMLButtonElement).disabled).toBe(
		true
	);
	const text = '字'.repeat(220);
	await fireEvent.input(input(), { target: { value: text } });
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
	await waitFor(() => expect(done).toHaveBeenCalledOnce());
	expect(api.submitDraftBaseline).toHaveBeenCalledWith(
		undefined,
		'session-1',
		text,
		[],
		textDocument(text),
		1
	);
});
test('恢复确认前保存的图文稿件', async () => {
	const document = {
		type: 'doc',
		content: [
			{ type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: '已保存标题' }] }
		]
	};
	api.getPendingWritingDraft.mockResolvedValue({
		content_json: document,
		materials: [],
		revision: 3
	});
	await start();
	expect(JSON.parse(input().value)).toEqual(document);
	expect(api.savePendingWritingDraft).not.toHaveBeenCalled();
});
test('Word 图文和格式进入同一个编辑器，核对后完整确认', async () => {
	const document = textDocument('字'.repeat(220));
	document.content!.push({
		type: 'writingImage',
		attrs: { materialId: 'm', blockId: 'm1', width: 70 }
	});
	const material = { id: 'm', filename: 'draft.docx', blocks: [] };
	api.extractImportDocument.mockResolvedValue({
		text: '字'.repeat(220),
		content_json: document,
		material
	});
	await start();
	await pick([new File(['x'], 'draft.docx')]);
	await waitFor(() => expect(JSON.parse(input().value)).toEqual(document));
	expect(api.submitDraftBaseline).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
	await waitFor(() =>
		expect(api.submitDraftBaseline).toHaveBeenCalledWith(
			undefined,
			'session-1',
			'字'.repeat(220),
			[{ id: 'm', corrections: {} }],
			document,
			1
		)
	);
});
test('识图关闭仍能上传照片，图像内容不充当字数', async () => {
	api.extractImportImages.mockResolvedValue({
		text: '',
		content_json: {
			type: 'doc',
			content: [
				{
					type: 'writingImage',
					attrs: { materialId: 'm', blockId: 'm1', transcription: '字'.repeat(300) }
				}
			]
		},
		materials: []
	});
	await start(false);
	expect((screen.getByTestId('draft-upload-input') as HTMLInputElement).accept).toContain(
		'image/png'
	);
	await pick([new File(['x'], 'photo.png', { type: 'image/png' })]);
	await fireEvent.click(screen.getByText('插入图片'));
	await waitFor(() => expect(api.extractImportImages).toHaveBeenCalledOnce());
	expect((screen.getByText('Confirm this is my first draft') as HTMLButtonElement).disabled).toBe(
		true
	);
	expect(
		screen.getByText('请补充至少 200 字正文。图片和未转入正文的识别文字不计入字数。')
	).toBeTruthy();
});
test('照片按文件名自然排序并保留原件，不在浏览器压缩替换原件', async () => {
	api.extractImportImages.mockResolvedValue({
		text: '',
		content_json: textDocument(''),
		materials: []
	});
	await start();
	const ten = new File(['10'], 'IMG_10.jpg', { type: 'image/jpeg' });
	const nine = new File(['9'], 'IMG_9.jpg', { type: 'image/jpeg' });
	await pick([ten, nine]);
	await fireEvent.click(screen.getByText('插入图片'));
	expect(api.extractImportImages).toHaveBeenCalledWith(
		undefined,
		'session-1',
		[nine, ten],
		'reference'
	);
});
test('超过八张照片和图文混选均在上传前阻止', async () => {
	await start();
	await pick(
		Array.from({ length: 9 }, (_, i) => new File(['x'], i + '.png', { type: 'image/png' }))
	);
	expect(api.extractImportImages).not.toHaveBeenCalled();
	await pick([new File(['x'], 'a.docx'), new File(['x'], 'p.png', { type: 'image/png' })]);
	expect(screen.getByRole('alert').textContent).toContain('do not mix');
	expect(api.extractImportDocument).not.toHaveBeenCalled();
});
test('下载当前稿先保存，导出不触发确认', async () => {
	await start();
	const doc = textDocument('还未确认的稿件');
	await fireEvent.input(input(), { target: { value: '还未确认的稿件' } });
	await fireEvent.click(screen.getByText('下载当前稿（Word）'));
	await waitFor(() =>
		expect(api.downloadWritingWord).toHaveBeenCalledWith(undefined, {
			sessionId: 'session-1',
			pending: true,
			contentJson: doc
		})
	);
	expect(api.savePendingWritingDraft.mock.invocationCallOrder[0]).toBeLessThan(
		api.downloadWritingWord.mock.invocationCallOrder[0]
	);
	expect(api.submitDraftBaseline).not.toHaveBeenCalled();
});
test('保存冲突时保留内容，不确认也不导出旧稿', async () => {
	api.savePendingWritingDraft.mockRejectedValueOnce({ status: 409, detail: 'another window' });
	await start();
	await fireEvent.input(input(), { target: { value: '字'.repeat(230) } });
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
	await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('稿件状态已变化'));
	expect(api.submitDraftBaseline).not.toHaveBeenCalled();
	expect(JSON.parse(input().value)).toEqual(textDocument('字'.repeat(230)));
});
test('读取暂存失败时不允许空稿覆盖已有稿件', async () => {
	api.getPendingWritingDraft.mockRejectedValueOnce(new Error('offline'));
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });
	await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('offline'));
	expect(input().readOnly).toBe(true);
	expect(api.savePendingWritingDraft).not.toHaveBeenCalled();
});

test('手写稿转录直接进入正文并保留已有内容，确认可用且携带原件', async () => {
	const original = { id: 'photo', filename: 'handwriting.png', blocks: [] };
	api.extractImportImages.mockResolvedValue({
		text: '字'.repeat(220),
		content_json: textDocument('字'.repeat(220)),
		materials: [original]
	});
	const done = await start(false, true);
	await fireEvent.input(input(), { target: { value: '已有标题' } });
	await pick([new File(['x'], 'handwriting.png', { type: 'image/png' })]);
	expect(api.extractImportImages).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByText('照片转正文'));
	await waitFor(() => expect(input().value).toContain('字'.repeat(220)));
	expect(input().value).toContain('已有标题');
	expect(input().value).not.toContain('writingImage');
	expect(api.extractImportImages.mock.calls[0][3]).toBe('photo_to_text');
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
	await waitFor(() => expect(done).toHaveBeenCalledOnce());
	expect(api.submitDraftBaseline.mock.calls[0][3]).toEqual([{ id: 'photo', corrections: {} }]);
});

test('关闭照片转正文时仍能插图，取消不改变正文', async () => {
	await start(true, false);
	await fireEvent.input(input(), { target: { value: '保留原稿' } });
	await pick([new File(['x'], 'reference.png', { type: 'image/png' })]);
	expect((screen.getByText('照片转正文') as HTMLButtonElement).disabled).toBe(true);
	expect((screen.getByText('插入图片') as HTMLButtonElement).disabled).toBe(false);
	await fireEvent.click(screen.getByText('Cancel'));
	expect(input().value).toContain('保留原稿');
	expect(api.extractImportImages).not.toHaveBeenCalled();
});

test('调整照片顺序后按当前页序转录，失败保留选择供重试', async () => {
	await start(false, true);
	const a = new File(['a'], 'a.png', { type: 'image/png' });
	const b = new File(['b'], 'b.png', { type: 'image/png' });
	api.extractImportImages
		.mockRejectedValueOnce('识别失败')
		.mockResolvedValueOnce({ text: '完成', content_json: textDocument('完成'), materials: [] });
	await pick([a, b]);
	await fireEvent.click(screen.getAllByRole('button', { name: '下移 {{name}}' })[0]);
	await fireEvent.click(screen.getByText('照片转正文'));
	await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('识别失败'));
	expect(api.extractImportImages.mock.calls[0][2]).toEqual([b, a]);
	await fireEvent.click(screen.getByText('照片转正文'));
	await waitFor(() => expect(input().value).toContain('完成'));
});
