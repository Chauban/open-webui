import { describe, expect, test, vi } from 'vitest';

import { loadFolderChatList } from './folder-chat-list';

describe('loadFolderChatList', () => {
	test('reloads chats for an open folder', async () => {
		const loadChatsByFolderId = vi.fn().mockResolvedValue([{ id: 'chat-2' }]);

		const chats = await loadFolderChatList({
			open: true,
			folderId: 'writing-folder',
			loadChatsByFolderId
		});

		expect(loadChatsByFolderId).toHaveBeenCalledWith('writing-folder');
		expect(chats).toEqual([{ id: 'chat-2' }]);
	});

	test('clears chats for a closed folder', async () => {
		const loadChatsByFolderId = vi.fn();

		const chats = await loadFolderChatList({
			open: false,
			folderId: 'writing-folder',
			loadChatsByFolderId
		});

		expect(loadChatsByFolderId).not.toHaveBeenCalled();
		expect(chats).toBeNull();
	});
});
