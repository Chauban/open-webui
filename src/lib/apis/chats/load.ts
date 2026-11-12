import { getTaskIdsByChatId } from '$lib/apis';
import { getChatById, getTagsById } from '$lib/apis/chats';
import { workspaceBackground } from '$lib/utils/workspace-background';

/** These reads are independent; restoring a conversation should take one round trip. */
export const getChatLoadState = async (token: string, id: string, current = () => true) => {
	const [chat, taskIds] = await Promise.all([
		getChatById(token, id),
		getTaskIdsByChatId(token, id).then((result) => result?.task_ids ?? [])
	]);
	const tags = workspaceBackground(
		`tags:${token}:${id}`,
		() => getTagsById(token, id),
		current
	).catch((error) => {
		console.warn('Could not load chat tags:', error);
		return [];
	});
	return { chat, tags, taskIds };
};
