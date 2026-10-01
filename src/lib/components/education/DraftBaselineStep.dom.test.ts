// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const submitDraftBaseline = vi.fn();
vi.mock('$lib/apis/education', () => ({
	submitDraftBaseline: (...args: unknown[]) => submitDraftBaseline(...args)
}));

import DraftBaselineStep from './DraftBaselineStep.svelte';

afterEach(() => {
	cleanup();
	submitDraftBaseline.mockReset();
});
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('初稿不足 200 字(不计空白)时不能确认,够了才提交并通知外层刷新', async () => {
	const onSubmitted = vi.fn();
	submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	render(DraftBaselineStep, { props: { sessionId: 'session-1', onSubmitted }, context });

	const button = screen.getByText('Confirm this is my first draft').closest('button')!;
	const textarea = screen.getByPlaceholderText('Paste your first draft here');

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
