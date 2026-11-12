// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable, type Writable } from 'svelte/store';
import { tick } from 'svelte';
import { page } from '$app/stores';
import { goto } from '$app/navigation';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

const api = vi.hoisted(() => ({
	submitDraftBaseline: vi.fn(),
	getRevisionReadings: vi.fn(),
	requestRevisionReading: vi.fn(),
	getWritingProcessSummary: vi.fn(),
	getPendingWritingDraft: vi.fn(),
	savePendingWritingDraft: vi.fn(),
	teachingApi: vi.fn(),
	autosaveWritingSession: vi.fn(),
	createWritingVersion: vi.fn(),
	createEditorOperations: vi.fn(),
	createProvenanceSegments: vi.fn()
}));
const sidebar = vi.hoisted(() => ({
	refreshFolderChatLists: vi.fn(),
	refreshChatList: vi.fn()
}));
const chatApi = vi.hoisted(() => ({ getChatById: vi.fn() }));
vi.mock('$lib/apis/chats', () => chatApi);
vi.mock('$lib/apis/education', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/apis/education')>()),
	...api
}));
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: api.teachingApi }));
vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return {
		user: writable({ id: 'student-1' }),
		config: writable({}),
		models: writable([]),
		selectedFolder: writable(null)
	};
});
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/assignments/assignment-1/write') }) };
});
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/chatList', () => sidebar);
vi.mock('svelte-sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('$lib/components/chat/Chat.svelte', () => import('./test-fixtures/WorkspaceChat.svelte'));
vi.mock('./WritingEditor.svelte', () => import('./test-fixtures/WritingEditor.svelte'));
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
import { createWritingBackup } from '$lib/utils/writing-backup';
import { textDocument } from '$lib/utils/writing-document';

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
		owner_user_id: 'student-1',
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
	localStorage.clear();
	(page as unknown as Writable<{ url: URL }>).set({
		url: new URL('http://localhost/assignments/assignment-1/write')
	});
	sidebar.refreshFolderChatLists.mockResolvedValue(undefined);
	chatApi.getChatById.mockResolvedValue({ id: 'chat-1' });
	api.autosaveWritingSession.mockResolvedValue({ ok: true });
	api.createWritingVersion.mockResolvedValue({ id: 'version-1' });
	api.createEditorOperations.mockResolvedValue([]);
	api.createProvenanceSegments.mockResolvedValue([]);
	api.getPendingWritingDraft.mockResolvedValue({
		content_json: { type: 'doc', content: [] },
		materials: [],
		revision: 0
	});
	api.savePendingWritingDraft.mockResolvedValue({ revision: 1 });
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
	await waitFor(() =>
		expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).readOnly).toBe(false)
	);
	await fireEvent.input(
		screen.getByPlaceholderText('Paste your first draft here, or drop a file in'),
		{ target: { value: draft } }
	);
	await fireEvent.click(screen.getByText('Confirm this is my first draft'));
}

test.each([false, true])('past-due writing stays editable unless graded (%s)', async (graded) => {
	const data = {
		...workspace(true),
		assignment: { id: 'assignment-1', task_mode: 'from_scratch', reflection_questions: [] },
		effective_due_at: 1,
		review: graded ? { review_status: 'reviewed' } : null
	};
	render(WritingWorkspaceShell, {
		props: { loadWorkspace: vi.fn().mockResolvedValue(data) },
		context
	});
	const editor = (await screen.findByTestId('workspace-editor')) as HTMLTextAreaElement;
	expect(editor.readOnly).toBe(graded);
	if (graded) {
		expect(screen.queryByRole('button', { name: 'Submit Assignment' })).toBeNull();
	} else {
		expect(
			(screen.getByRole('button', { name: 'Submit Assignment' }) as HTMLButtonElement).disabled
		).toBe(false);
		expect(
			screen.getByText(
				'You can still write and submit. Your teacher will see a late submission label.'
			)
		).toBeTruthy();
		await fireEvent.input(editor, { target: { value: 'Late draft edits' } });
		await fireEvent.click(screen.getByText('Test send'));
		await waitFor(() => expect(api.autosaveWritingSession).toHaveBeenCalled());
		expect(await screen.findByText('Test sent')).toBeTruthy();
	}
});

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

async function openWriting() {
	api.getRevisionReadings.mockResolvedValue([{ purpose: 'first_read', status: 'ready' }]);
	const result = render(WritingWorkspaceShell, {
		props: { loadWorkspace: vi.fn().mockResolvedValue(workspace(true)) },
		context
	});
	await waitFor(() =>
		expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).readOnly).toBe(false)
	);
	return result;
}

test.each(['from_scratch', 'revise_draft', 'revise_argument'])(
	'打开 %s 作业后同步侧栏项目，不依赖发送消息',
	async (taskMode) => {
		const tree = deferred<void>();
		sidebar.refreshFolderChatLists.mockReturnValueOnce(tree.promise);
		const data = workspace();
		data.assignment.task_mode = taskMode;
		render(WritingWorkspaceShell, {
			props: { loadWorkspace: vi.fn().mockResolvedValue(data) },
			context
		});
		await waitFor(() => expect(sidebar.refreshFolderChatLists).toHaveBeenCalledWith(null));
		expect(sidebar.refreshFolderChatLists).not.toHaveBeenCalledWith('project-1', null);
		tree.resolve();
		await waitFor(() =>
			expect(sidebar.refreshFolderChatLists).toHaveBeenCalledWith('project-1', null)
		);
	}
);

test('初读生成唯一对话后刷新侧栏并跳入作业对话', async () => {
	api.getRevisionReadings
		.mockResolvedValueOnce([])
		.mockResolvedValue([
			{ purpose: 'first_read', status: 'ready', context: { chat_id: 'chat-1' } }
		]);
	api.requestRevisionReading.mockResolvedValue(undefined);
	render(WritingWorkspaceShell, {
		props: {
			projectBaseUrl: '/assignments/assignment-1/write',
			loadWorkspace: vi.fn().mockResolvedValue(workspace(true))
		},
		context
	});
	await waitFor(() =>
		expect(sidebar.refreshFolderChatLists).toHaveBeenCalledWith('project-1', { id: 'chat-1' })
	);
	expect(goto).toHaveBeenCalledWith('/assignments/assignment-1/write?chat=chat-1', {
		replaceState: true
	});
});

test('已批改作业仍显示唯一对话，同页点击作业入口后继续原对话', async () => {
	const setUrl = (suffix = '') =>
		(page as unknown as Writable<{ url: URL }>).set({
			url: new URL(`http://localhost/assignments/assignment-1/write${suffix}`)
		});
	api.getRevisionReadings.mockResolvedValue([{ purpose: 'first_read', status: 'ready' }]);
	render(WritingWorkspaceShell, {
		props: {
			projectBaseUrl: '/assignments/assignment-1/write',
			loadWorkspace: vi.fn().mockResolvedValue({
				...workspace(true),
				writing_session: { ...workspace(true).writing_session, active_chat_id: 'chat-1' },
				review: { review_status: 'reviewed' }
			})
		},
		context
	});
	await waitFor(() =>
		expect(goto).toHaveBeenCalledWith('/assignments/assignment-1/write?chat=chat-1', {
			replaceState: true
		})
	);
	expect(sidebar.refreshFolderChatLists).toHaveBeenCalledWith('project-1', { id: 'chat-1' });
	setUrl('?chat=chat-1');
	await tick();
	vi.mocked(goto).mockClear();
	setUrl();
	await waitFor(() =>
		expect(goto).toHaveBeenCalledWith('/assignments/assignment-1/write?chat=chat-1', {
			replaceState: true
		})
	);
	expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).readOnly).toBe(true);
	expect(api.requestRevisionReading).not.toHaveBeenCalled();
});

test('格式失败保留本地稿，停止自动重试；聊天输入不清空，手动重试成功后才发送', async () => {
	api.autosaveWritingSession.mockRejectedValue({
		status: 400,
		detail: 'Invalid paragraph alignment',
		requestId: 'request-safe',
		field: 'content_json.content.0.attrs.textAlign'
	});
	await openWriting();
	await fireEvent.input(screen.getByTestId('workspace-editor'), {
		target: { value: '尚未保存的修改' }
	});
	expect(createWritingBackup('student-1', 'session-1', 'draft').list()[0].data.document).toEqual(
		textDocument('尚未保存的修改')
	);
	await waitFor(() => expect(api.autosaveWritingSession).toHaveBeenCalledTimes(1), {
		timeout: 2500
	});
	await waitFor(() => expect(screen.getByText('错误编号', { exact: false })).toBeTruthy());
	expect(api.createWritingVersion).not.toHaveBeenCalled();
	await new Promise((resolve) => setTimeout(resolve, 2100));
	expect(api.autosaveWritingSession).toHaveBeenCalledTimes(1);
	await fireEvent.input(screen.getByLabelText('Test message'), {
		target: { value: '请看我的修改' }
	});
	await fireEvent.click(screen.getByText('Test send'));
	await waitFor(() =>
		expect(
			screen.getAllByText('消息尚未发送，输入已保留。请先处理稿件保存，再点击发送。').length
		).toBeGreaterThan(0)
	);
	expect((screen.getByLabelText('Test message') as HTMLInputElement).value).toBe('请看我的修改');
	expect(screen.queryByText('Test sent')).toBeNull();
	api.autosaveWritingSession.mockResolvedValue({ ok: true });
	await fireEvent.click(screen.getByRole('button', { name: '重试保存' }));
	await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalledTimes(1));
	expect(createWritingBackup('student-1', 'session-1', 'draft').list()).toEqual([]);
	await fireEvent.click(screen.getByText('Test send'));
	await waitFor(() => expect(screen.getByText('Test sent')).toBeTruthy());
}, 10000);

test('重新打开时先显示服务器稿，确认恢复后才上传本地正文和原有来源记录', async () => {
	const page = await openWriting();
	await fireEvent.input(screen.getByTestId('workspace-editor'), {
		target: { value: '刷新前的修改' }
	});
	page.unmount();
	expect(api.autosaveWritingSession).not.toHaveBeenCalled();
	await openWriting();
	expect((screen.getByTestId('workspace-editor') as HTMLTextAreaElement).value).toBe(
		JSON.stringify(draftJson)
	);
	expect(screen.getByText('发现本浏览器中尚未同步的稿件。')).toBeTruthy();
	expect(api.autosaveWritingSession).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: '恢复此稿并保存' }));
	await waitFor(() => expect(api.autosaveWritingSession).toHaveBeenCalledTimes(1), {
		timeout: 2500
	});
	expect(api.autosaveWritingSession.mock.calls[0][2].content_json).toEqual(
		textDocument('刷新前的修改')
	);
	expect(api.createEditorOperations.mock.calls[0][2].operations[0].inserted_text).toBe(
		'刷新前的修改'
	);
});

test('保存旧快照期间继续输入，旧响应不能删除新输入的备份', async () => {
	const flight = deferred<unknown>();
	api.autosaveWritingSession.mockReturnValueOnce(flight.promise);
	await openWriting();
	await fireEvent.input(screen.getByTestId('workspace-editor'), { target: { value: '第一版' } });
	await waitFor(() => expect(api.autosaveWritingSession).toHaveBeenCalledTimes(1), {
		timeout: 2500
	});
	await fireEvent.input(screen.getByTestId('workspace-editor'), { target: { value: '第二版' } });
	flight.resolve({ ok: true });
	await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalled());
	expect(createWritingBackup('student-1', 'session-1', 'draft').list()[0].data.document).toEqual(
		textDocument('第二版')
	);
});

test('部分保存失败后重试继续补来源记录，不跳过已创建版本的来源保存', async () => {
	api.createProvenanceSegments.mockRejectedValueOnce({ status: 400 });
	await openWriting();
	await fireEvent.input(screen.getByTestId('workspace-editor'), {
		target: { value: '来源需要保存' }
	});
	await waitFor(() => expect(screen.getByRole('button', { name: '重试保存' })).toBeTruthy(), {
		timeout: 2500
	});
	await fireEvent.click(screen.getByRole('button', { name: '重试保存' }));
	await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalledTimes(2));
	expect(api.createWritingVersion).toHaveBeenCalledTimes(1);
	expect(api.createProvenanceSegments.mock.calls[1][2].version_id).toBe('version-1');
});

test('来源保存失败后继续改稿，重试使用各版本当时的来源而不混用新稿', async () => {
	api.createProvenanceSegments.mockRejectedValueOnce({ status: 400 });
	api.createWritingVersion
		.mockResolvedValueOnce({ id: 'first-version' })
		.mockResolvedValueOnce({ id: 'second-version' });
	await openWriting();
	await fireEvent.input(screen.getByTestId('workspace-editor'), {
		target: { value: '第一次修改' }
	});
	await waitFor(() => expect(screen.getByRole('button', { name: '重试保存' })).toBeTruthy(), {
		timeout: 2500
	});
	await fireEvent.input(screen.getByTestId('workspace-editor'), {
		target: { value: '第二次修改' }
	});
	await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalledTimes(3), {
		timeout: 2500
	});
	expect(api.createProvenanceSegments.mock.calls[1][2]).toMatchObject({
		version_id: 'first-version'
	});
	expect(
		api.createProvenanceSegments.mock.calls[1][2].segments.map((s) => s.segment_text).join('')
	).toBe('第一次修改');
	expect(
		api.createProvenanceSegments.mock.calls[2][2].segments.map((s) => s.segment_text).join('')
	).toBe('第二次修改');
});

test('浏览器空间不足明确告警，仍尝试正常保存到服务器', async () => {
	await openWriting();
	const original = Storage.prototype.setItem;
	const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (key, value) {
		if (key.startsWith('writing-backup:')) throw new DOMException('Full', 'QuotaExceededError');
		return original.call(this, key, value);
	});
	try {
		await fireEvent.input(screen.getByTestId('workspace-editor'), {
			target: { value: '容量不足时也不能阻止远程保存' }
		});
		await waitFor(() =>
			expect(screen.getByText('本浏览器无法备份稿件，请立即复制全文或下载文字备份。')).toBeTruthy()
		);
		await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalled(), { timeout: 2500 });
	} finally {
		spy.mockRestore();
	}
});

test('已批改作业的本地备份只能下载，不能通过恢复绕过只读限制', async () => {
	createWritingBackup<any>('student-1', 'session-1', 'draft').write({
		document: textDocument('本地未提交修改'),
		runs: [],
		operations: [],
		baseline: 1,
		pendingVersion: null
	});
	api.getRevisionReadings.mockResolvedValue([{ purpose: 'first_read', status: 'ready' }]);
	render(WritingWorkspaceShell, {
		props: {
			loadWorkspace: vi
				.fn()
				.mockResolvedValue({ ...workspace(true), review: { review_status: 'reviewed' } })
		},
		context
	});
	await waitFor(() =>
		expect(
			(screen.getByRole('button', { name: '恢复此稿并保存' }) as HTMLButtonElement).disabled
		).toBe(true)
	);
	expect((screen.getByRole('button', { name: '下载所选备份' }) as HTMLButtonElement).disabled).toBe(
		false
	);
	expect(api.autosaveWritingSession).not.toHaveBeenCalled();
});

test('离线积累超过千条编辑记录后分批同步，完整成功才移除备份', async () => {
	const text = '字'.repeat(1005);
	createWritingBackup<any>('student-1', 'session-1', 'draft').write({
		document: textDocument(text),
		baseline: 1,
		pendingVersion: null,
		runs: [{ startOffset: 0, endOffset: text.length, sourceType: 'user_typed' }],
		operations: Array.from({ length: 1005 }, (_, i) => ({
			op_type: 'keyboard_input',
			source_type: 'user_typed',
			start_offset: i,
			end_offset: i + 1,
			inserted_text: '字',
			batch_id: `test-${i}`,
			occurred_at_ms: 1794400000000 + i,
			client_sequence: i
		}))
	});
	await openWriting();
	await fireEvent.click(screen.getByRole('button', { name: '恢复此稿并保存' }));
	await waitFor(() => expect(api.createProvenanceSegments).toHaveBeenCalled(), { timeout: 2500 });
	expect(api.createEditorOperations.mock.calls.map((call) => call[2].operations.length)).toEqual([
		1000, 5
	]);
	expect(createWritingBackup('student-1', 'session-1', 'draft').list()).toEqual([]);
});
