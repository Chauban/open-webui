// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import Stub from './test-fixtures/TimelineMessage.svelte';
import type { RevisionReading } from '$lib/apis/education';
vi.mock('./Messages/Message.svelte', () => ({ default: Stub }));
vi.mock('./ChatPlaceholder.svelte', () => ({ default: Stub }));
vi.mock('$lib/stores', () => ({
	config: readable({}),
	settings: readable({}),
	user: readable({ id: 'student' }),
	mobile: readable(false),
	temporaryChatEnabled: readable(false)
}));
vi.mock('$lib/stores/chatList', () => ({ refreshChatList: vi.fn() }));
vi.mock('$lib/utils', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/utils')>()),
	copyToClipboard: vi.fn(),
	extractCurlyBraceWords: () => []
}));
import Messages from './Messages.svelte';
afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (s: string) => s })]]);
test('刷新直接显示已有消息；追加回复后初读和旧对话都仍在原顺序', async () => {
	const history = {
		currentId: 'a1',
		messages: {
			u1: { id: 'u1', parentId: null, role: 'user', timestamp: 2 },
			a1: { id: 'a1', parentId: 'u1', role: 'assistant', timestamp: 3 }
		}
	};
	const reading: RevisionReading = {
		sequence_no: 1,
		purpose: 'first_read',
		source_text: '稿件',
		source_version_id: null,
		source_hash: 'hash',
		completed_at: 1,
		model_id: null,
		thinking: null,
		context: { teaching_version: 1, description_version: 1, title: '测试', description: null },
		id: 'r1',
		created_at: 1,
		status: 'ready',
		feedback: { understanding: '初读反馈', strength: null, focus: [], overview: '概览' }
	};
	const { rerender } = render(Messages, {
		props: {
			history,
			prompt: '',
			selectedModels: [],
			revisionMode: true,
			revisionReadings: [reading],
			messagesCount: null,
			autoScroll: false,
			atSelectedModel: undefined,
			sendMessage: vi.fn(),
			continueResponse: vi.fn(),
			regenerateResponse: vi.fn(),
			mergeResponses: vi.fn(),
			chatActionHandler: vi.fn()
		},
		context
	});
	expect(await screen.findByText('u1')).toBeTruthy();
	expect(screen.getByText('a1')).toBeTruthy();
	expect(screen.getByText('初读反馈')).toBeTruthy();
	await rerender({
		history: {
			currentId: 'u2',
			messages: {
				...history.messages,
				u2: { id: 'u2', parentId: 'a1', role: 'user', timestamp: 4 }
			}
		}
	});
	await waitFor(() => expect(screen.getByText('u2')).toBeTruthy());
	const text = screen.getByRole('log').textContent!;
	expect(text.indexOf('初读反馈')).toBeLessThan(text.indexOf('u1'));
	expect(text.indexOf('u1')).toBeLessThan(text.indexOf('a1'));
	expect(text.indexOf('a1')).toBeLessThan(text.indexOf('u2'));
});
