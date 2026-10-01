// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const submitDraftBaseline = vi.fn();
const extractDraftBaselineFile = vi.fn();
vi.mock('$lib/apis/education', () => ({
	submitDraftBaseline: (...args: unknown[]) => submitDraftBaseline(...args),
	extractDraftBaselineFile: (...args: unknown[]) => extractDraftBaselineFile(...args)
}));

import DraftBaselineStep from './DraftBaselineStep.svelte';

afterEach(() => {
	cleanup();
	submitDraftBaseline.mockReset();
	extractDraftBaselineFile.mockReset();
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
	extractDraftBaselineFile.mockResolvedValue({ text: draft });
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted: vi.fn() }, context });

	const file = new File(['docx bytes'], '初稿.docx');
	await fireEvent.change(screen.getByTestId('draft-file-input'), { target: { files: [file] } });

	const textarea = screen.getByPlaceholderText(
		'Paste your first draft here, or drop a file in'
	) as HTMLTextAreaElement;
	await waitFor(() => expect(textarea.value).toBe(draft));
	expect(extractDraftBaselineFile).toHaveBeenCalledWith(undefined, 'session-1', file);
	// 只是填进框里,还没有交
	expect(submitDraftBaseline).not.toHaveBeenCalled();
});
