// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { config, models, settings, user } from '$lib/stores';

vi.mock('$lib/workers/KokoroWorker', () => ({ KokoroWorker: vi.fn() }));
vi.mock('$lib/components/common/RichTextInput/suggestions', () => ({
	getSuggestionRenderer: vi.fn()
}));
vi.mock(
	'./MessageInput/InputMenu.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'./MessageInput/VoiceRecording.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'./ToolServersModal.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock('./SkillsModal.svelte', () => import('../education/test-fixtures/WorkspaceEmpty.svelte'));
vi.mock(
	'./MessageInput/InputVariablesModal.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'./MessageInput/IntegrationsMenu.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'../workspace/common/ValvesModal.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'../common/InputModal.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock(
	'../common/Tooltip.svelte',
	() => import('../education/test-fixtures/WorkspaceEmpty.svelte')
);
vi.mock('../common/RichTextInput.svelte', () => import('./test-fixtures/ComposerInput.svelte'));

import MessageInput from './MessageInput.svelte';

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
const review = vi.fn();
const submit = vi.fn();

beforeEach(() => {
	config.set({ features: {}, audio: { stt: {} } } as any);
	settings.set({});
	models.set([{ id: 'test-model', name: 'Test model' }] as any);
	user.set({ id: 'student', role: 'user', permissions: { chat: {} } } as any);
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

function mount(props = {}) {
	return render(MessageInput, {
		context,
		props: {
			embedded: true,
			history: { messages: {}, currentId: null },
			selectedModels: [''],
			fixedModelName: 'Test model',
			createMessagePair: vi.fn(),
			stopResponse: vi.fn(),
			revisionAction: { label: '改好了，请看看', disabled: false, onClick: review },
			...props
		},
		events: { submit }
	});
}

test('改稿后只有一个发送入口，空输入点击它请求复看', async () => {
	mount();
	const button = await screen.findByRole('button', { name: '改好了，请看看' });
	expect(document.querySelectorAll('#send-message-button')).toHaveLength(1);
	expect(screen.queryByRole('button', { name: '发送说明，请看修改' })).toBeNull();
	await fireEvent.click(button);
	expect(review).toHaveBeenCalledOnce();
	expect(submit).not.toHaveBeenCalled();
});

test('有问题时按原文发送，不追加复看请求', async () => {
	mount({ prompt: '我想讨论另一处' });
	await fireEvent.click(await screen.findByRole('button', { name: 'Send message' }));
	expect(submit).toHaveBeenCalledOnce();
	expect(submit.mock.calls[0][0].detail).toBe('我想讨论另一处');
	expect(review).not.toHaveBeenCalled();
});

test('改稿后 Enter 与点击使用同一复看入口，Shift+Enter 不发送', async () => {
	mount();
	const input = await screen.findByTestId('composer-input');
	await fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
	expect(review).not.toHaveBeenCalled();
	await fireEvent.keyDown(input, { key: 'Enter' });
	expect(review).toHaveBeenCalledOnce();
});

test.each([
	{ revisionAction: null },
	{ revisionAction: { label: '改好了，请看看', disabled: true, onClick: review } },
	{ uploadPending: true }
])('未改稿、等待保存或上传时，空输入不能通过点击或 Enter 发送：%j', async (props) => {
	const { container } = mount(props);
	const input = await screen.findByTestId('composer-input');
	const button = container.querySelector('#send-message-button') as HTMLButtonElement;
	expect(button.disabled).toBe(true);
	await fireEvent.click(button);
	await fireEvent.keyDown(input, { key: 'Enter' });
	expect(review).not.toHaveBeenCalled();
	expect(submit).not.toHaveBeenCalled();
});

test('改稿但带有附件时仍走普通发送', async () => {
	mount({ files: [{ type: 'image', url: 'data:image/png;base64,', name: '材料.png' }] });
	await fireEvent.click(await screen.findByRole('button', { name: 'Send message' }));
	expect(submit).toHaveBeenCalledOnce();
	expect(review).not.toHaveBeenCalled();
});
