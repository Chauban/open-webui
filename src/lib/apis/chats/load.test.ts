import { afterEach, expect, test, vi } from 'vitest';

const api = vi.hoisted(() => ({
	getChatById: vi.fn(),
	getTagsById: vi.fn(),
	getTaskIdsByChatId: vi.fn()
}));
vi.mock('$lib/apis/chats', () => api);
vi.mock('$lib/apis', () => api);
import { getChatLoadState } from './load';

afterEach(() => {
	vi.resetAllMocks();
});

test('历史与任务并行，标签等必要读取完成后开始且不阻塞返回', async () => {
	let finishChat!: (chat: unknown) => void;
	api.getChatById.mockReturnValue(new Promise((resolve) => (finishChat = resolve)));
	api.getTagsById.mockResolvedValue(['课程写作']);
	api.getTaskIdsByChatId.mockResolvedValue({ task_ids: ['running-task'] });
	const result = getChatLoadState('token', 'chat-1');
	expect(api.getTagsById).not.toHaveBeenCalled();
	expect(api.getTaskIdsByChatId).toHaveBeenCalledWith('token', 'chat-1');
	finishChat({ id: 'chat-1', chat: { history: { messages: {} } } });
	const loaded = await result;
	expect({ ...loaded, tags: await loaded.tags }).toEqual({
		chat: { id: 'chat-1', chat: { history: { messages: {} } } },
		tags: ['课程写作'],
		taskIds: ['running-task']
	});
});

test('慢标签不挡住历史，标签失败不影响必要恢复状态', async () => {
	const warning = vi.spyOn(console, 'warn').mockImplementation(() => {});
	try {
		api.getChatById.mockResolvedValue({ id: 'chat-1' });
		let failTags;
		api.getTagsById.mockReturnValue(new Promise((_, reject) => (failTags = reject)));
		api.getTaskIdsByChatId.mockResolvedValue({ task_ids: [] });
		const loaded = await getChatLoadState('token', 'chat-1');
		expect(loaded.chat.id).toBe('chat-1');
		failTags(new Error('Tags unavailable'));
		expect(await loaded.tags).toEqual([]);
	} finally {
		warning.mockRestore();
	}
});

test('任务状态失败不能伪装为空任务并解锁', async () => {
	api.getChatById.mockResolvedValue({ id: 'chat-1' });
	api.getTagsById.mockResolvedValue([]);
	api.getTaskIdsByChatId.mockRejectedValue(new Error('Tasks unavailable'));
	await expect(getChatLoadState('token', 'chat-1')).rejects.toThrow('Tasks unavailable');
});

test('历史读取失败不以标签或任务状态冒充恢复成功', async () => {
	api.getChatById.mockRejectedValue(new Error('Chat unavailable'));
	api.getTagsById.mockResolvedValue([]);
	api.getTaskIdsByChatId.mockResolvedValue({ task_ids: [] });
	await expect(getChatLoadState('token', 'chat-1')).rejects.toThrow('Chat unavailable');
});
