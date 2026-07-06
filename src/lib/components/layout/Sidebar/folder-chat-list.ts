type LoadFolderChatListOptions<T> = {
	open: boolean;
	folderId: string;
	loadChatsByFolderId: (folderId: string) => Promise<T[]>;
};

export const loadFolderChatList = async <T>({
	open,
	folderId,
	loadChatsByFolderId
}: LoadFolderChatListOptions<T>): Promise<T[] | null> => {
	if (!open) {
		return null;
	}

	return loadChatsByFolderId(folderId);
};
