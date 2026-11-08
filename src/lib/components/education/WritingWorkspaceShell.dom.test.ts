// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

const api = vi.hoisted(() => ({
	submitDraftBaseline: vi.fn(),
	getRevisionReadings: vi.fn(),
	requestRevisionReading: vi.fn(),
	getWritingProcessSummary: vi.fn(),
	teachingApi: vi.fn()
}));
vi.mock('$lib/apis/education', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/apis/education')>()),
	...api
}));
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: api.teachingApi }));
vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return { config: writable({}), models: writable([]), selectedFolder: writable(null) };
});
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ url: new URL('http://localhost/assignments/assignment-1/write') }) };
});
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/chatList', () => ({}));
vi.mock('svelte-sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('$lib/components/chat/Chat.svelte', () => import('./test-fixtures/WorkspaceChat.svelte'));
vi.mock(
	'$lib/components/common/RichTextInput.svelte',
	() => import('./test-fixtures/WorkspaceEditor.svelte')
);
vi.mock('./TextImportActions.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./ReviewResultCard.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./WritingComposition.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./SubmissionHistoryModal.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./AssignmentBrief.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./EduDataNotice.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./ChallengeDialog.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./ChallengeChecklist.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./ReflectionAnswerForm.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./EditorImportDialog.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./ThinkingSwitch.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock('./EduActionMenu.svelte', () => import('./test-fixtures/WorkspaceEmpty.svelte'));
vi.mock(
	'$lib/components/common/ConfirmDialog.svelte',
	() => import('./test-fixtures/WorkspaceEmpty.svelte')
);

import WritingWorkspaceShell from './WritingWorkspaceShell.svelte';

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const draft = '确认后的初稿。'.repeat(40);
const draftJson = {
	type: 'doc',
	content: [{ type: 'paragraph', content: [{ type: 'text', text: draft }] }]
};
const workspace = (confirmed = false) => ({
	assignment: { id: 'assignment-1', task_mode: 'revise_argument', reflection_questions: [] },
	writing_session: {
		id: 'session-1',
		draft_baseline_at: confirmed ? 1 : null,
		draft_baseline_text: confirmed ? draft : ''
	},
	project: { id: 'project-1' },
	note: { data: { content: { json: confirmed ? draftJson : null, md: confirmed ? draft : '' } } }
});

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	api.teachingApi.mockResolvedValue({ revision: 1 });
	api.getWritingProcessSummary.mockResolvedValue({ clarification_answered_count: 0 });
	api.submitDraftBaseline.mockResolvedValue({ id: 'session-1' });
	api.getRevisionReadings.mockResolvedValue([]);
});
afterEach(() => {
	cleanup();
	vi.resetAllMocks();
	sessionStorage.clear();
});

async function confirmDraft() {
	await screen.findByPlaceholderText('Paste your first draft here, or drop a file in');
	await fireEvent.input(
		screen.getByPlaceholderText('Paste your first draft here, or drop a file in'),
		{ target: { value: draft } }
	);
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
}

function expectWaitingWithDraft() {
	const editor = screen.getByTestId('workspace-editor') as HTMLTextAreaElement;
	expect(editor.value).toBe(JSON.stringify(draftJson));
	expect(editor.readOnly).toBe(true);
	expect(screen.getByTestId('workspace-chat').getAttribute('aria-busy')).toBe('true');
	expect(
		(screen.getByText('Submit Assignment').closest('button') as HTMLButtonElement).disabled
	).toBe(true);
}

test('确认初稿后，配置加载、阅读记录加载与初读请求之间持续等待，编辑器首次挂载即有完整稿件', async () => {
	const summary = deferred<unknown>();
	const readings = deferred<unknown[]>();
	const reading = deferred<void>();
	api.teachingApi.mockResolvedValueOnce({ revision: 1 }).mockReturnValueOnce(summary.promise);
	api.getRevisionReadings
		.mockReturnValueOnce(readings.promise)
		.mockResolvedValueOnce([{ purpose: 'first_read', status: 'ready' }]);
	api.requestRevisionReading.mockReturnValueOnce(reading.promise);
	render(WritingWorkspaceShell, {
		props: {
			loadWorkspace: vi
				.fn()
				.mockResolvedValueOnce(workspace())
				.mockResolvedValueOnce(workspace(true))
		},
		context
	});
	await confirmDraft();
	await waitFor(() => expect(api.teachingApi).toHaveBeenCalledTimes(2));
	expectWaitingWithDraft();
	summary.resolve({ revision: 1 });
	await waitFor(() => expect(api.getRevisionReadings).toHaveBeenCalledTimes(1));
	expectWaitingWithDraft();
	readings.resolve([]);
	await waitFor(() => expect(api.requestRevisionReading).toHaveBeenCalledTimes(1));
	expectWaitingWithDraft();
	reading.resolve();
	await waitFor(() =>
		expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).readOnly).toBe(false)
	);
	expect(screen.getByTestId('workspace-chat').getAttribute('aria-busy')).toBe('false');
});

test.each(['records', 'request'])('初读 %s 失败后退出等待并保留确认稿，仍可提交', async (stage) => {
	const failure = deferred<never>();
	if (stage === 'records') api.getRevisionReadings.mockReturnValueOnce(failure.promise);
	else api.requestRevisionReading.mockReturnValueOnce(failure.promise);
	render(WritingWorkspaceShell, {
		props: {
			loadWorkspace: vi
				.fn()
				.mockResolvedValueOnce(workspace())
				.mockResolvedValueOnce(workspace(true))
		},
		context
	});
	await confirmDraft();
	await waitFor(() =>
		expect(
			stage === 'records' ? api.getRevisionReadings : api.requestRevisionReading
		).toHaveBeenCalledTimes(1)
	);
	expectWaitingWithDraft();
	failure.reject(new Error('Network unavailable'));
	await waitFor(() =>
		expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).readOnly).toBe(false)
	);
	expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).value).toBe(
		JSON.stringify(draftJson)
	);
	expect(
		(screen.getByText('Submit Assignment').closest('button') as HTMLButtonElement).disabled
	).toBe(false);
});
