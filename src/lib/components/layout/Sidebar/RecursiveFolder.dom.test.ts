// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores', () => ({
	chatId: writable(null),
	mobile: writable(false),
	selectedFolder: writable(null),
	showSidebar: writable(true),
	user: writable({ id: 'student', education_role: 'student' })
}));
vi.mock('svelte-sonner', () => ({ toast: Object.assign(vi.fn(), { error: vi.fn() }) }));
vi.mock('./ChatItem.svelte', () => import('$lib/components/common/Spinner.svelte'));
vi.mock('./Folders/FolderMenu.svelte', () => import('$lib/components/common/Spinner.svelte'));
vi.mock('./Folders/FolderModal.svelte', () => import('$lib/components/common/Spinner.svelte'));
vi.mock(
	'$lib/components/common/ConfirmDialog.svelte',
	() => import('$lib/components/common/Spinner.svelte')
);

import { goto } from '$app/navigation';
import { toast } from 'svelte-sonner';
import RecursiveFolder from './RecursiveFolder.svelte';
import zh from '$lib/i18n/locales/zh-CN/translation.json';

const folder = {
	id: 'writing-project',
	name: '自我介绍',
	parent_id: null,
	is_expanded: false,
	meta: { mode: 'assignment_writing', hidden_from_sidebar: false }
};
const mountFolder = (onCloseFolder: (folder: unknown) => Promise<void>) =>
	render(RecursiveFolder, {
		context: new Map([['i18n', readable({ t: (key: string) => zh[key] ?? key })]]),
		props: {
			folders: { [folder.id]: folder },
			folderId: folder.id,
			lockFolders: true,
			showVisibilityToggle: true,
			folderHrefBuilder: () => '/assignments/assignment/write',
			onCloseFolder
		}
	});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

test('关闭立即调用回调，不展示等待状态、不重复请求或打开写作区', async () => {
	let complete!: () => void;
	const onClose = vi.fn(() => new Promise<void>((resolve) => (complete = resolve)));
	mountFolder(onClose);
	await fireEvent.click(screen.getByRole('button', { name: '关闭' }));
	const pending = screen.getByRole('button', { name: '关闭' });
	expect((pending as HTMLButtonElement).disabled).toBe(true);
	expect(pending.getAttribute('aria-busy')).toBeNull();
	expect(screen.queryByText('正在关闭…')).toBeNull();
	await fireEvent.click(pending);
	expect(onClose).toHaveBeenCalledOnce();
	expect(onClose).toHaveBeenCalledWith(folder);
	complete();
	await waitFor(() => expect((pending as HTMLButtonElement).disabled).toBe(false));
	expect(goto).not.toHaveBeenCalled();
});

test('保存未完成时给出轻提示并允许重试', async () => {
	const onClose = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'));
	onClose.mockResolvedValueOnce(undefined);
	mountFolder(onClose);
	await fireEvent.click(screen.getByRole('button', { name: '关闭' }));
	await waitFor(() =>
		expect(toast).toHaveBeenCalledWith('侧栏设置未能保存，已恢复此项目，可重新关闭。')
	);
	expect(toast.error).not.toHaveBeenCalled();
	expect(screen.getByText('自我介绍')).toBeTruthy();
	const retry = screen.getByRole('button', { name: '关闭' });
	expect((retry as HTMLButtonElement).disabled).toBe(false);
	await fireEvent.click(retry);
	expect(onClose).toHaveBeenCalledTimes(2);
	expect(goto).not.toHaveBeenCalled();
});
