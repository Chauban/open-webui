// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import Page from './+page.svelte';
import { teachingApi } from '$lib/apis/education/teaching';
import { goto } from '$app/navigation';

const { list, visibility } = vi.hoisted(() => ({ list: vi.fn(), visibility: vi.fn() }));
vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		url: new URL('http://localhost/teacher/assignments')
	})
}));
vi.mock('$lib/stores', async (original) => ({
	...(await original<typeof import('$lib/stores')>()),
	user: (await import('svelte/store')).readable({ id: 'teacher-1' })
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/apis/education', () => ({
	getTeacherAssignments: list,
	getTeacherClassrooms: vi.fn(async () => []),
	setAssignmentVisibility: visibility
}));
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: vi.fn(async () => []) }));
vi.mock('$lib/utils/transitions', () => ({ flyAndScale: () => ({ duration: 0 }) }));
const context = new Map([['i18n', readable({ t: (key: string) => key, language: 'en' })]]);
const row = (id: string, hidden: boolean) => ({
	assignment: { id, title: id, hidden, due_at: 2000000000, config_revision: 1 },
	classroom: { id: 'class', name: 'Writing' },
	submission_count: 1,
	student_count: 2,
	pending_review_count: 1
});
beforeEach(() => {
	localStorage.clear();
	vi.mocked(teachingApi).mockReset().mockResolvedValue([]);
	vi.mocked(goto).mockClear();
	localStorage.token = 'test-token';
	vi.stubGlobal(
		'ResizeObserver',
		class {
			observe() {}
			unobserve() {}
			disconnect() {}
		}
	);
	list.mockResolvedValue([row('Visible essay', false), row('Hidden essay', true)]);
	visibility.mockReset();
	visibility.mockImplementation(async (_, id, hidden) => row(id, hidden).assignment);
});
afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
});

test.each([{}, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }])(
	'assignment links reach the router without triggering row navigation (%j)',
	async (modifiers) => {
		render(Page, { context });
		const link = await screen.findByRole('link', { name: 'Visible essay' });
		const row = link.closest('tr')!;
		const pendingLink = within(row).getByRole('link', { name: '1' });
		const routerClick = vi.fn((event: MouseEvent) => {
			expect(event.defaultPrevented).toBe(false);
			event.preventDefault();
		});
		document.addEventListener('click', routerClick);
		try {
			await fireEvent.click(link, modifiers);
			await fireEvent.click(pendingLink, modifiers);
			expect(routerClick).toHaveBeenCalledTimes(2);
			expect(goto).not.toHaveBeenCalled();
			expect(pendingLink.getAttribute('href')).toContain('/submissions?status=pending');
		} finally {
			document.removeEventListener('click', routerClick);
		}
	}
);

test('row space navigates once while its menu leaves navigation alone', async () => {
	render(Page, { context });
	const link = await screen.findByRole('link', { name: 'Visible essay' });
	const row = link.closest('tr')!;
	await fireEvent.click(row.cells[0]);
	expect(goto).toHaveBeenCalledTimes(1);
	expect(goto).toHaveBeenCalledWith('/teacher/assignments/Visible essay');
	vi.mocked(goto).mockClear();
	await fireEvent.click(within(row).getByRole('button', { name: 'More' }));
	expect(goto).not.toHaveBeenCalled();
});

test('hides and restores immediately without a change description', async () => {
	render(Page, { context });
	const visibleGroup = await screen.findByRole('region', { name: 'Assignments Shown to Students' });
	const hiddenGroup = screen.getByRole('region', { name: 'Hidden Assignments' });
	await fireEvent.click(within(visibleGroup).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Hide Assignment' }));
	await within(hiddenGroup).findByText('Visible essay');
	expect(visibility).toHaveBeenCalledWith(expect.anything(), 'Visible essay', true);
	expect(screen.queryByRole('dialog')).toBeNull();
	const row = within(hiddenGroup).getByText('Visible essay').closest('tr')!;
	await fireEvent.click(within(row).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Show Assignment' }));
	expect(await screen.findByRole('region', { name: 'Assignments Shown to Students' })).toBeTruthy();
	expect(visibility).toHaveBeenLastCalledWith(expect.anything(), 'Visible essay', false);
	expect(screen.queryByLabelText('修改说明（必填）')).toBeNull();
});

test('failed visibility changes leave the assignment in its original group', async () => {
	visibility.mockRejectedValue(new Error('Unable to save'));
	render(Page, { context });
	const group = await screen.findByRole('region', { name: 'Assignments Shown to Students' });
	await fireEvent.click(within(group).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Hide Assignment' }));
	await waitFor(() => expect(visibility).toHaveBeenCalled());
	expect(within(group).getByText('Visible essay')).toBeTruthy();
	expect(
		within(screen.getByRole('region', { name: 'Hidden Assignments' })).queryByText('Visible essay')
	).toBeNull();
});

test('shows recoverable local and server drafts once, with continue links; published entries disappear', async () => {
	const server = {
		id: 'draft-one',
		assignment_id: null,
		revision: 1,
		published: null,
		payload: { assignment: { title: '服务端旧标题', classroom_ids: [] }, ai: {} }
	};
	vi.mocked(teachingApi).mockResolvedValue([
		server,
		{ ...server, id: 'published', published: { assignment_ids: ['a'] } }
	]);
	localStorage.setItem(
		'assignment-drafts:teacher-1:draft-one',
		JSON.stringify({
			id: 'draft-one',
			assignmentId: null,
			preparation: server,
			payload: { ...server.payload, assignment: { title: '本地最新标题', classroom_ids: [] } },
			updatedAt: 1
		})
	);
	localStorage.setItem(
		'assignment-drafts:another-user:private',
		JSON.stringify({ id: 'private', payload: { assignment: { title: '他人的草稿' }, ai: {} } })
	);
	render(Page, { context });
	await screen.findByText('本地最新标题');
	expect(screen.queryByText('服务端旧标题')).toBeNull();
	expect(screen.queryByText('他人的草稿')).toBeNull();
	expect(screen.getAllByRole('link', { name: '继续编辑' })).toHaveLength(1);
	expect(screen.getByRole('link', { name: '继续编辑' }).getAttribute('href')).toBe(
		'/teacher/assignments/new?preparation=draft-one'
	);
});

test('deleting a server draft passes its revision and removes its list entry', async () => {
	const server = {
		id: 'draft-delete',
		assignment_id: null,
		revision: 3,
		published: null,
		payload: { assignment: { title: '可删除的草稿', classroom_ids: [] }, ai: {} }
	};
	vi.mocked(teachingApi).mockImplementation(async (_path, method) =>
		method === 'DELETE' ? { deleted: true } : [server]
	);
	render(Page, { context });
	await screen.findByText('可删除的草稿');
	await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
	const dialog = screen.getByRole('dialog', { name: '删除这份草稿？' });
	expect(dialog.textContent).toContain('草稿删除后无法恢复，试教记录和已保存方案会保留。');
	expect(vi.mocked(teachingApi).mock.calls.some(([, method]) => method === 'DELETE')).toBe(false);
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
	await waitFor(() => expect(screen.queryByText('可删除的草稿')).toBeNull());
	expect(teachingApi).toHaveBeenCalledWith(
		'/teacher/teaching-preparations/draft-delete?expected_revision=3',
		'DELETE'
	);
	expect(screen.queryByText('可删除的草稿')).toBeNull();
});

test.each(['cancel', 'failure', 'success'])(
	'draft deletion keeps the local backup until confirmed server success (%s)',
	async (outcome) => {
		const server = {
			id: 'trial-draft',
			assignment_id: null,
			revision: 2,
			published: null,
			payload: { assignment: { title: '试教草稿', classroom_ids: [] }, ai: {} },
			trials: [{ id: 'trial-one', sequence: 1, created_at: 1 }]
		};
		const key = 'assignment-drafts:teacher-1:trial-draft';
		const backup = JSON.stringify({
			id: server.id,
			assignmentId: null,
			preparation: server,
			payload: server.payload,
			updatedAt: 1
		});
		localStorage.setItem(key, backup);
		vi.mocked(teachingApi).mockImplementation(async (_path, method) => {
			if (method !== 'DELETE') return [server];
			if (outcome === 'failure') throw { status: 409, detail: 'Preparation changed' };
			return { deleted: true };
		});
		render(Page, { context });
		await screen.findByRole('link', { name: 'Visible essay' });
		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
		await fireEvent.click(
			within(screen.getByRole('dialog')).getByRole('button', {
				name: outcome === 'cancel' ? 'Cancel' : 'Delete'
			})
		);
		if (outcome !== 'cancel')
			await waitFor(() =>
				expect(vi.mocked(teachingApi).mock.calls.some(([, method]) => method === 'DELETE')).toBe(
					true
				)
			);
		const deletions = vi.mocked(teachingApi).mock.calls.filter(([, method]) => method === 'DELETE');
		expect(deletions).toHaveLength(outcome === 'cancel' ? 0 : 1);
		if (outcome === 'success') {
			expect(localStorage.getItem(key)).toBeNull();
			expect(screen.queryByText('试教草稿')).toBeNull();
		} else {
			expect(localStorage.getItem(key)).toBe(backup);
			expect(screen.getByText('试教草稿')).toBeTruthy();
		}
	}
);

test.each([true, false])(
	'deletes a local draft after checking for an unacknowledged save (%s)',
	async (saved) => {
		const server = {
			id: 'local-draft',
			assignment_id: null,
			revision: 1,
			published: null,
			payload: { assignment: { title: '本地草稿', classroom_ids: [] }, ai: {} }
		};
		const key = 'assignment-drafts:teacher-1:local-draft';
		localStorage.setItem(
			key,
			JSON.stringify({ id: server.id, assignmentId: null, payload: server.payload, updatedAt: 1 })
		);
		vi.mocked(teachingApi).mockImplementation(async (path, method) => {
			if (path === '/teacher/teaching-preparations') return [];
			if (method === 'DELETE') return { deleted: true };
			if (saved) return server;
			throw { status: 404 };
		});
		render(Page, { context });
		await screen.findByRole('link', { name: 'Visible essay' });
		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
		await fireEvent.click(
			within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' })
		);
		await waitFor(() =>
			expect(teachingApi).toHaveBeenCalledWith('/teacher/teaching-preparations/local-draft')
		);
		expect(vi.mocked(teachingApi).mock.calls.filter(([, method]) => method === 'DELETE')).toEqual(
			saved ? [['/teacher/teaching-preparations/local-draft?expected_revision=1', 'DELETE']] : []
		);
		await waitFor(() => expect(localStorage.getItem(key)).toBeNull());
		expect(screen.queryByText('本地草稿')).toBeNull();
	}
);
